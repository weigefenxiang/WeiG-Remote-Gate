(() => {
  const PROBE_INTERVAL = 60 * 1000;
  const PROBE_TIMEOUT = 8000;
  const RENEW_BEFORE = 120;
  let running = false;

  const endpoint = {
    ipv4: 'https://api.ipify.org?format=json',
    ipv6: 'https://api6.ipify.org?format=json'
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

  async function fetchIp(family) {
    setDiagnostic(family, 'probing', 'IP echo request in progress');
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), PROBE_TIMEOUT);
    try {
      const response = await fetch(endpoint[family], {
        cache: 'no-store',
        mode: 'cors',
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`IP echo HTTP ${response.status}`);
      const payload = await response.json();
      const address = String(payload?.ip || '').trim();
      if (!address) throw new Error('IP echo returned no address');
      setDiagnostic(family, 'echo_ok', 'IP echo succeeded', address);
      return address;
    } catch (error) {
      const detail = error?.name === 'AbortError' ? `IP echo timed out after ${PROBE_TIMEOUT / 1000}s` : String(error?.message || error || 'IP echo failed');
      setDiagnostic(family, 'echo_error', detail);
      throw error;
    } finally {
      clearTimeout(timer);
    }
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
    return ['ipv4', 'ipv6'].filter((family) => {
      const source = data?.client_sources?.[family];
      if (!source?.address) return true;
      if (source.confidence !== 'candidate') return true;
      return Number(source.expires_at || 0) - now < RENEW_BEFORE;
    });
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
    if (changed) window.location.reload();
  }

  function bind() {
    probeFamilies();
    window.setInterval(probeFamilies, PROBE_INTERVAL);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();

  window.RemoteGateClientSources = {probeFamilies, diagnostics: diagnosticSnapshot};
})();
