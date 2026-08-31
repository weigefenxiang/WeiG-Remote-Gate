(() => {
  const PROBE_INTERVAL = 60 * 1000;
  const PROBE_TIMEOUT = 8000;
  const PROBE_RETRY_DELAY = 3000;
  const PROBE_KEY = 'weig-remote-gate:source-probe-at:';
  let running = false;

  function validIPv4(value) {
    const parts = String(value || '').trim().split('.');
    return parts.length === 4 && parts.every((part) => {
      if (!/^\d{1,3}$/.test(part)) return false;
      const n = Number(part);
      return n >= 0 && n <= 255;
    });
  }

  function validIPv6(value) {
    const text = String(value || '').trim();
    return text.includes(':') && /^[0-9A-Fa-f:.]+$/.test(text) && text.length <= 64;
  }

  function validAddress(family, value) {
    return family === 'ipv4' ? validIPv4(value) : family === 'ipv6' ? validIPv6(value) : false;
  }

  async function record(family, address, csrf) {
    const response = await fetch('/api/v1/client-source/probe', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf
      },
      body: JSON.stringify({family, address})
    });
    if (!response.ok) throw new Error(`source probe HTTP ${response.status}`);
    window.dispatchEvent(new CustomEvent('remote-gate-source-probe', {detail: {family}}));
  }

  function jsonpProbe(family, csrf, allowRetry = true) {
    const host = family === 'ipv6' ? 'https://api6.ipify.org' : 'https://api.ipify.org';
    const callback = `__weigSource_${family}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const script = document.createElement('script');
    let timer = 0;
    let settled = false;

    const cleanup = () => {
      clearTimeout(timer);
      script.remove();
      try { delete window[callback]; } catch (_) { window[callback] = undefined; }
    };

    const finish = (success) => {
      if (settled) return;
      settled = true;
      cleanup();
      if (success) {
        sessionStorage.setItem(PROBE_KEY + family, String(Date.now()));
        window.location.reload();
      } else if (allowRetry) {
        window.setTimeout(() => jsonpProbe(family, csrf, false), PROBE_RETRY_DELAY);
      }
    };

    window[callback] = async (payload) => {
      const address = String(payload?.ip || '').trim();
      if (!validAddress(family, address)) {
        finish(false);
        return;
      }
      try {
        await record(family, address, csrf);
        finish(true);
      } catch (_) {
        finish(false);
      }
    };

    script.async = true;
    script.referrerPolicy = 'no-referrer';
    script.src = `${host}?format=jsonp&callback=${encodeURIComponent(callback)}&_=${Date.now()}`;
    script.onerror = () => finish(false);
    timer = setTimeout(() => finish(false), PROBE_TIMEOUT);
    document.head.append(script);
  }

  function shouldProbe(family) {
    const last = Number(sessionStorage.getItem(PROBE_KEY + family) || 0);
    return Date.now() - last >= PROBE_INTERVAL;
  }

  async function probeMissingFamilies() {
    if (running || !document.getElementById('workspace')) return;
    running = true;
    try {
      const response = await fetch('/api/v1/dashboard', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      if (!response.ok) return;
      const data = await response.json();
      if (!data?.csrf) return;

      for (const family of ['ipv4', 'ipv6']) {
        if (data?.client_sources?.[family]?.address || !shouldProbe(family)) continue;
        jsonpProbe(family, data.csrf);
      }
    } catch (_) {
      // The control page remains fully usable when either external probe fails.
    } finally {
      running = false;
    }
  }

  function bind() {
    probeMissingFamilies();
    window.setInterval(probeMissingFamilies, PROBE_INTERVAL);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();

  window.RemoteGateClientSources = {probeMissingFamilies, validIPv4, validIPv6};
})();
