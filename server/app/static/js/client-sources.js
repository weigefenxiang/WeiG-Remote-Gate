(() => {
  const PROBE_INTERVAL = 60 * 1000;
  const PROBE_TIMEOUT = 8000;
  let running = false;

  const endpoint = {
    ipv4: 'https://api.ipify.org?format=json',
    ipv6: 'https://api6.ipify.org?format=json'
  };

  async function fetchIp(family) {
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
      return address;
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
    if (!response.ok) throw new Error(`candidate HTTP ${response.status}`);
    return response.json();
  }

  async function probeMissingFamilies() {
    if (running || !document.getElementById('workspace')) return;
    running = true;
    let changed = false;
    try {
      const response = await fetch('/api/v1/dashboard', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      if (!response.ok) return;
      const data = await response.json();
      const csrf = String(data?.csrf || '');
      if (!csrf) return;

      const families = ['ipv4', 'ipv6'].filter((family) => !data?.client_sources?.[family]?.address);
      const results = await Promise.allSettled(families.map(async (family) => {
        const address = await fetchIp(family);
        await saveCandidate(family, address, csrf);
        return family;
      }));
      changed = results.some((item) => item.status === 'fulfilled');
    } catch (_) {
      // Missing family remains unavailable. Never promote a browser value by itself.
    } finally {
      running = false;
    }
    if (changed) window.location.reload();
  }

  function bind() {
    probeMissingFamilies();
    window.setInterval(probeMissingFamilies, PROBE_INTERVAL);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();

  window.RemoteGateClientSources = {probeMissingFamilies};
})();
