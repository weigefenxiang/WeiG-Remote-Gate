(() => {
  const current = document.currentScript;
  const currentUrl = new URL(current?.src || location.href, location.href);
  const assetVersion = currentUrl.searchParams.get('v') || '';
  const assetUrl = (path) => assetVersion ? `${path}?v=${encodeURIComponent(assetVersion)}` : path;

  const favicon = document.createElement('link');
  favicon.rel = 'icon';
  favicon.type = 'image/png';
  favicon.href = '/static/Wei.G.ico';
  document.head.append(favicon);

  const interaction = document.createElement('link');
  interaction.rel = 'stylesheet';
  interaction.href = assetUrl('/static/css/interaction.css');
  document.head.append(interaction);

  const key = 'weig-remote-gate:theme';
  const saved = localStorage.getItem(key);
  const choice = saved === 'light' || saved === 'dark' ? saved : 'auto';
  const resolved = choice === 'auto'
    ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : choice;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeChoice = choice;

  // Client source discovery is loaded explicitly by dashboard.html because it
  // is security-critical. Optional UI modules inherit the exact same build SHA
  // from this bootstrap URL so one HTML document can never mix asset builds.
  const modules = [
    '/static/js/motion-feedback.js',
    '/static/js/endpoint-picker.js',
    '/static/js/duration-control.js'
  ];

  modules.forEach((src) => {
    if (document.querySelector(`script[data-remote-gate-module="${src}"]`)) return;
    const script = document.createElement('script');
    script.src = assetUrl(src);
    script.async = false;
    script.dataset.remoteGateModule = src;
    document.head.append(script);
  });

  function brandIcon() {
    const trigger = document.getElementById('utility-trigger');
    if (!trigger || trigger.querySelector('.brand-icon-image')) return;
    trigger.textContent = '';
    const image = document.createElement('img');
    image.className = 'brand-icon-image';
    image.src = '/static/Wei.G.ico';
    image.alt = '';
    image.width = 44;
    image.height = 44;
    image.decoding = 'async';
    trigger.append(image);
    trigger.classList.add('brand-icon-chassis');
  }

  function polishGateActions() {
    const activate = document.getElementById('activate-button');
    if (!activate) return;
    activate.querySelector('[aria-hidden="true"]')?.remove();
    activate.style.justifyContent = 'center';
    activate.style.textAlign = 'center';
  }

  function mappedPlaceholder() {
    return document.documentElement.dataset.lang === 'zh'
      ? 'Endpoint 在 Activate 后确认'
      : 'Endpoint resolved after Activate';
  }

  function rewriteMappedOptions() {
    const select = document.getElementById('endpoint-select') || document.getElementById('wan-select');
    if (!select) return;
    let changed = false;
    [...select.options].forEach((option) => {
      const text = String(option.textContent || '');
      const parts = text.split(' · ');
      const mappedIndex = parts.indexOf('Mapped');
      if (mappedIndex < 0) return;
      const next = [...parts.slice(0, mappedIndex + 1), mappedPlaceholder()].join(' · ');
      if (next !== text) {
        option.textContent = next;
        changed = true;
      }
    });
    if (changed) window.RemoteGateEndpointPicker?.sync?.(select.id);
  }

  function mappedEndpointFromDashboard(data) {
    if (!data?.agent?.firewall?.active) return '';
    const last = data?.gate?.queue?.last;
    if (!last || last.action !== 'activate' || last.state !== 'done') return '';
    const match = String(last.detail || '').match(/(?:^|\s)mapped-endpoint:([0-9.]+):([0-9]{1,5})(?:\s|$)/);
    if (!match) return '';
    const port = Number(match[2]);
    if (!Number.isInteger(port) || port < 1 || port > 65535) return '';
    return `${match[1]}:${port}`;
  }

  function renderMappedEndpoint(data) {
    const endpoint = mappedEndpointFromDashboard(data);
    let row = document.getElementById('mapped-public-endpoint');
    if (!endpoint) {
      row?.remove();
      return;
    }
    const substate = document.getElementById('gate-substate');
    if (!substate) return;
    if (!row) {
      row = document.createElement('div');
      row.id = 'mapped-public-endpoint';
      row.className = 'muted small';
      row.style.display = 'flex';
      row.style.flexWrap = 'wrap';
      row.style.alignItems = 'center';
      row.style.gap = '0.45rem';
      row.style.marginTop = '0.5rem';
      const label = document.createElement('span');
      label.dataset.mappedEndpointLabel = '1';
      const value = document.createElement('button');
      value.type = 'button';
      value.className = 'wan-address-copy fit-single-line';
      value.dataset.mappedEndpointValue = '1';
      value.addEventListener('click', async () => {
        const currentValue = String(value.textContent || '');
        if (!currentValue) return;
        try { await navigator.clipboard.writeText(currentValue); } catch (_) { /* no-op */ }
      });
      const note = document.createElement('span');
      note.dataset.mappedEndpointNote = '1';
      row.append(label, value, note);
      substate.insertAdjacentElement('afterend', row);
    }
    const zh = document.documentElement.dataset.lang === 'zh';
    row.querySelector('[data-mapped-endpoint-label]').textContent = zh ? 'WireGuard 公网 Endpoint' : 'WireGuard Public Endpoint';
    const value = row.querySelector('[data-mapped-endpoint-value]');
    value.textContent = endpoint;
    value.title = endpoint;
    row.querySelector('[data-mapped-endpoint-note]').textContent = zh ? 'OpenWrt 在 Activate 时确认' : 'Resolved by OpenWrt on Activate';
  }

  function observeMappedPicker() {
    let queued = false;
    const observer = new MutationObserver(() => {
      if (queued) return;
      queued = true;
      queueMicrotask(() => {
        queued = false;
        rewriteMappedOptions();
      });
    });
    observer.observe(document.documentElement, {subtree: true, childList: true});
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    try {
      const requestUrl = new URL(typeof args[0] === 'string' ? args[0] : args[0]?.url || '', location.href);
      if (requestUrl.pathname === '/api/v1/dashboard' && response.ok) {
        response.clone().json().then((data) => {
          renderMappedEndpoint(data);
          queueMicrotask(rewriteMappedOptions);
        }).catch(() => {});
      }
    } catch (_) { /* preserve fetch semantics */ }
    return response;
  };

  function ready() {
    brandIcon();
    polishGateActions();
    rewriteMappedOptions();
    observeMappedPicker();
  }

  window.addEventListener('remote-gate-language', () => queueMicrotask(rewriteMappedOptions));

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, {once: true});
  else ready();
})();
