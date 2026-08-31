(() => {
  const PROBE_INTERVAL = 60 * 1000;
  const PROBE_TIMEOUT = 8000;
  const PROBE_RETRY_DELAY = 3000;
  const PROBE_KEY = 'weig-remote-gate:source-observer-at:';
  let running = false;

  async function challenge(family) {
    const response = await fetch(`/api/v1/client-source/challenge?family=${encodeURIComponent(family)}`, {
      credentials: 'same-origin',
      cache: 'no-store'
    });
    if (!response.ok) throw new Error(`source observer challenge HTTP ${response.status}`);
    const payload = await response.json();
    if (payload?.family !== family || typeof payload?.url !== 'string' || !payload.url.startsWith('https://')) {
      throw new Error('invalid source observer challenge');
    }
    return payload.url;
  }

  function observerProbe(family, allowRetry = true) {
    const callback = `__weigObserver_${family}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
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
        window.setTimeout(() => observerProbe(family, false), PROBE_RETRY_DELAY);
      }
    };

    window[callback] = (payload) => finish(payload?.ok === true);

    challenge(family).then((url) => {
      const separator = url.includes('?') ? '&' : '?';
      script.async = true;
      script.referrerPolicy = 'no-referrer';
      script.src = `${url}${separator}callback=${encodeURIComponent(callback)}&_=${Date.now()}`;
      script.onerror = () => finish(false);
      timer = window.setTimeout(() => finish(false), PROBE_TIMEOUT);
      document.head.append(script);
    }).catch(() => finish(false));
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

      for (const family of ['ipv4', 'ipv6']) {
        if (data?.client_sources?.[family]?.address || !shouldProbe(family)) continue;
        observerProbe(family);
      }
    } catch (_) {
      // A missing family remains unavailable rather than trusting browser-reported IP data.
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

  window.RemoteGateClientSources = {probeMissingFamilies};
})();
