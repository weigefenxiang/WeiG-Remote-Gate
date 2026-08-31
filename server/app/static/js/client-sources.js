(() => {
  const PROBE_INTERVAL = 60 * 1000;
  const PROBE_TIMEOUT = 8000;
  const RENEW_BEFORE = 120;
  let running = false;

  const providers = {
    ipv4: [
      {url: 'https://api.ipify.org?format=json', parse: async (response) => String((await response.json())?.ip || '').trim()},
      {url: 'https://api-ipv4.ip.sb/ip', parse: async (response) => String(await response.text()).trim()}
    ],
    ipv6: [
      {url: 'https://api6.ipify.org?format=json', parse: async (response) => String((await response.json())?.ip || '').trim()},
      {url: 'https://api-ipv6.ip.sb/ip', parse: async (response) => String(await response.text()).trim()}
    ]
  };

  const diagnostics = {
    ipv4: {status: 'idle', detail: '', address: '', updatedAt: 0},
    ipv6: {status: 'idle', detail: '', address: '', updatedAt: 0}
  };

  function setDiagnostic(family, status, detail = '', address = '') {
    diagnostics[family] = {
      status,
      detail: String(detail || ''),
      address: String(address || ''),
      updatedAt: Date.now()
    };
    window.dispatchEvent(new CustomEvent('remote-gate-client-source-diagnostics', {
      detail: {family, ...diagnostics[family]}
    }));
  }

  function diagnosticSnapshot() {
    return {
      ipv4: {...diagnostics.ipv4},
      ipv6: {...diagnostics.ipv6}
    };
  }

  async function fetchProvider(family, provider, index) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), PROBE_TIMEOUT);
    try {
      const response = await fetch(provider.url, {
        cache: 'no-store',
        mode: 'cors',
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const address = await provider.parse(response);
      if (!address) throw new Error('returned no address');
      setDiagnostic(family, 'echo_ok', `${index === 0 ? 'Primary' : 'Fallback'} IP echo succeeded`, address);
      return address;
    } finally {
      clearTimeout(timer);
    }
  }

  async function fetchIp(family) {
    setDiagnostic(family, 'probing', 'IP echo request in progress');
    const errors = [];
    for (let index = 0; index < providers[family].length; index += 1) {
      try {
        return await fetchProvider(family, providers[family][index], index);
      } catch (error) {
        const detail = error?.name === 'AbortError'
          ? `timed out after ${PROBE_TIMEOUT / 1000}s`
          : String(error?.message || error || 'failed');
        errors.push(`${index === 0 ? 'primary' : 'fallback'}: ${detail}`);
      }
    }
    const detail = `IP echo unavailable (${errors.join('; ')})`;
    setDiagnostic(family, 'echo_error', detail);
    throw new Error(detail);
  }

  async function saveCandidate(family, address, csrf) {
    const response = await fetch('/api/v1/client-source/candidate', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf
      },
      body: JSON.stringify({family, address})
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const code = String(payload?.error || `HTTP ${response.status}`);
      setDiagnostic(family, 'candidate_error', `Candidate rejected: ${code}`, address);
      throw new Error(`candidate ${code}`);
    }
    setDiagnostic(family, 'saved', 'Carrier candidate saved; waiting for WireGuard verification', address);
    return payload;
  }

  function familiesToProbe(data) {
    const now = Math.floor(Date.now() / 1000);
    const result = [];
    ['ipv4', 'ipv6'].forEach((family) => {
      const source = data?.client_sources?.[family];
      if (!source?.address) {
        result.push(family);
        return;
      }
      if (source.confidence === 'candidate' && Number(source.expires_at || 0) - now < RENEW_BEFORE) {
        result.push(family);
        return;
      }
      if (source.confidence === 'observed') {
        setDiagnostic(family, 'observed', 'Cloudflare HTTP source already observed; carrier probe skipped', source.address);
      } else if (source.confidence === 'candidate') {
        setDiagnostic(family, 'saved', 'Carrier candidate remains fresh', source.address);
      }
    });
    return result;
  }

  async function probeFamilies() {
    if (running || !document.getElementById('workspace')) return;
    running = true;
    let changed = false;
    try {
      const response = await fetch('/api/v1/dashboard', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      if (!response.ok) throw new Error(`dashboard HTTP ${response.status}`);
      const data = await response.json();
      const csrf = String(data?.csrf || '');
      if (!csrf) throw new Error('dashboard returned no CSRF token');

      const families = familiesToProbe(data);
      const results = await Promise.allSettled(families.map(async (family) => {
        const address = await fetchIp(family);
        await saveCandidate(family, address, csrf);
        return family;
      }));
      changed = results.some((item) => item.status === 'fulfilled');
    } catch (error) {
      const detail = String(error?.message || error || 'source probe failed');
      ['ipv4', 'ipv6'].forEach((family) => {
        if (diagnostics[family].status === 'idle') setDiagnostic(family, 'dashboard_error', detail);
      });
    } finally {
      running = false;
    }
    if (changed) window.dispatchEvent(new CustomEvent('remote-gate-client-source-updated'));
  }

  function bind() {
    probeFamilies();
    window.setInterval(probeFamilies, PROBE_INTERVAL);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();

  window.RemoteGateClientSources = {probeFamilies, diagnostics: diagnosticSnapshot};
})();
