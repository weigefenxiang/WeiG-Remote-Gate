(() => {
  const favicon = document.createElement('link');
  favicon.rel = 'icon';
  favicon.type = 'image/png';
  favicon.href = '/static/Wei.G.ico';
  document.head.append(favicon);

  const key = 'weig-remote-gate:theme';
  const saved = localStorage.getItem(key);
  const choice = saved === 'light' || saved === 'dark' ? saved : 'auto';
  const resolved = choice === 'auto'
    ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : choice;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeChoice = choice;

  const PROBE_KEY = 'weig-remote-gate:carrier-ipv4-probe-at';
  const PROBE_INTERVAL = 60 * 1000;
  const PROBE_TIMEOUT = 8000;

  function validIPv4(value) {
    const parts = String(value || '').trim().split('.');
    return parts.length === 4 && parts.every((part) => {
      if (!/^\d{1,3}$/.test(part)) return false;
      const n = Number(part);
      return n >= 0 && n <= 255;
    });
  }

  async function recordIPv4(ipv4, csrf) {
    const response = await fetch('/api/v1/client-source/probe', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf
      },
      body: JSON.stringify({ipv4})
    });
    if (!response.ok) throw new Error(`probe record HTTP ${response.status}`);
  }

  function ipv4OnlyProbe(csrf) {
    const callback = `__weigCarrierIPv4_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const script = document.createElement('script');
    let timer = 0;

    const cleanup = () => {
      clearTimeout(timer);
      script.remove();
      try { delete window[callback]; } catch (_) { window[callback] = undefined; }
    };

    window[callback] = async (payload) => {
      const ipv4 = String(payload?.ip || '').trim();
      if (!validIPv4(ipv4)) {
        cleanup();
        return;
      }
      try {
        await recordIPv4(ipv4, csrf);
        cleanup();
        location.reload();
      } catch (_) {
        cleanup();
      }
    };

    script.async = true;
    script.referrerPolicy = 'no-referrer';
    script.src = `https://api.ipify.org?format=jsonp&callback=${encodeURIComponent(callback)}&_=${Date.now()}`;
    script.onerror = cleanup;
    timer = setTimeout(cleanup, PROBE_TIMEOUT);
    document.head.append(script);
  }

  async function maybeProbeCarrierIPv4() {
    if (!document.getElementById('workspace')) return;
    const last = Number(sessionStorage.getItem(PROBE_KEY) || 0);
    if (Date.now() - last < PROBE_INTERVAL) return;

    try {
      const response = await fetch('/api/v1/dashboard', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      if (!response.ok) return;
      const data = await response.json();
      if (data?.client_sources?.ipv4?.address) return;
      if (!data?.csrf) return;
      sessionStorage.setItem(PROBE_KEY, String(Date.now()));
      ipv4OnlyProbe(data.csrf);
    } catch (_) {
      // Probe failure is non-fatal; the normal dashboard remains usable.
    }
  }

  document.addEventListener('DOMContentLoaded', maybeProbeCarrierIPv4, {once: true});
})();
