(() => {
  const current = document.currentScript;
  const currentUrl = new URL(current?.src || location.href, location.href);
  const assetVersion = currentUrl.searchParams.get('v') || '';
  const assetUrl = (path) => assetVersion ? `${path}?v=${encodeURIComponent(assetVersion)}` : path;
  let latestDashboard = null;

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

  // Security-critical client discovery is loaded explicitly by dashboard.html.
  // Optional UI modules inherit the immutable build SHA from this script URL.
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

  function zh() {
    return document.documentElement.dataset.lang === 'zh';
  }

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

  function orbStateLabel(state) {
    if (state === 'open') return 'OPEN';
    if (state === 'authorizing') return 'WAIT';
    if (state === 'error') return 'ERROR';
    return 'CLOSED';
  }

  function sideLabels(state) {
    if (state === 'open') return zh() ? ['WAN 入口', '临时开放'] : ['WAN INPUT', 'TEMP OPEN'];
    if (state === 'authorizing') return zh() ? ['WAN 入口', '正在同步'] : ['WAN INPUT', 'SYNCING'];
    if (state === 'error') return zh() ? ['WAN 入口', '需要检查'] : ['WAN INPUT', 'CHECK'];
    return zh() ? ['WAN 入口', '保持隐藏'] : ['WAN INPUT', 'HIDDEN'];
  }

  function syncGateStatusPresentation() {
    const orb = document.getElementById('gate-orb');
    if (!orb) return;
    const state = String(orb.dataset.state || 'closed');
    const shortState = document.getElementById('gate-orb-state');
    if (shortState) shortState.textContent = orbStateLabel(state);
    const [left, right] = sideLabels(state);
    const leftEl = document.querySelector('[data-gate-status-side="left"]');
    const rightEl = document.querySelector('[data-gate-status-side="right"]');
    if (leftEl) leftEl.textContent = left;
    if (rightEl) rightEl.textContent = right;
    document.getElementById('gate-status-copy')?.classList.toggle('is-redundant', state === 'closed');
  }

  function ensureGateStatusStructure() {
    const wrap = document.querySelector('.gate-orb-wrap');
    const orb = document.getElementById('gate-orb');
    const core = orb?.querySelector('.gate-core');
    const state = document.getElementById('gate-state');
    const substate = document.getElementById('gate-substate');
    if (!wrap || !orb || !core || !state || !substate) return;
    wrap.classList.add('gate-status-hero');

    let shortState = document.getElementById('gate-orb-state');
    if (!shortState) {
      shortState = document.createElement('strong');
      shortState.id = 'gate-orb-state';
      shortState.className = 'gate-orb-short-state';
      core.append(shortState);
    }

    let stage = document.getElementById('gate-status-stage');
    if (!stage) {
      stage = document.createElement('div');
      stage.id = 'gate-status-stage';
      stage.className = 'gate-status-stage';
      const left = document.createElement('span');
      left.className = 'gate-status-side gate-status-side--left';
      left.dataset.gateStatusSide = 'left';
      const right = document.createElement('span');
      right.className = 'gate-status-side gate-status-side--right';
      right.dataset.gateStatusSide = 'right';
      wrap.insertBefore(stage, wrap.firstChild);
      stage.append(left, orb, right);
    }

    let copy = document.getElementById('gate-status-copy');
    if (!copy) {
      copy = document.createElement('div');
      copy.id = 'gate-status-copy';
      copy.className = 'gate-status-copy';
      copy.setAttribute('aria-live', 'polite');
      stage.insertAdjacentElement('afterend', copy);
    }
    if (state.parentElement !== copy) copy.append(state);
    if (substate.parentElement !== copy) copy.append(substate);

    syncGateStatusPresentation();
    if (orb.dataset.statusPresentationObserver !== '1') {
      new MutationObserver(syncGateStatusPresentation)
        .observe(orb, {attributes: true, attributeFilter: ['data-state']});
      orb.dataset.statusPresentationObserver = '1';
    }
  }

  function selectedEndpointRecord(data) {
    const select = document.getElementById('endpoint-select') || document.getElementById('wan-select');
    if (!select || select.dataset.selectionConfirmed !== '1' || !select.value) return null;
    if (String(select.dataset.selectionFamily || '') === 'dual' || String(select.value).startsWith('dual:')) return null;
    const endpoints = Array.isArray(data?.endpoints) ? data.endpoints : [];
    return endpoints.find((item) => item && String(item.id || '') === String(select.value)) || null;
  }

  function validPort(value) {
    const port = Number(value || 0);
    return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : 0;
  }

  function directEndpoint(item) {
    if (!item || item.reachability !== 'direct' || item.access_method !== 'direct') return null;
    const address = String(item.external_address || '').trim();
    const port = validPort(item.external_port || item.service_port);
    if (!address || !port) return null;
    const endpoint = item.family === 'ipv6' ? `[${address}]:${port}` : `${address}:${port}`;
    return {endpoint, current: true, method: 'direct', family: String(item.family || '')};
  }

  function mappedEndpoint(data, selected) {
    if (!selected || selected.family !== 'ipv4' || (selected.access_method !== 'mapped' && selected.reachability !== 'mapped')) return null;
    const inventory = data?.inventory;
    const raw = Array.isArray(inventory?.mappings) ? inventory.mappings : [];
    const exact = raw
      .filter((item) =>
        item &&
        item.family === 'ipv4' &&
        item.transport === 'udp' &&
        String(item.wan || '') === String(selected.wan || '') &&
        String(item.device || '') === String(selected.device || '') &&
        String(item.service_id || '') === String(selected.service_id || '')
      )
      .sort((a, b) => Number(b.observed_at || 0) - Number(a.observed_at || 0));
    const mapping = exact[0];
    const address = String(mapping?.external_address || selected.external_address || '').trim();
    const port = validPort(mapping?.external_port || selected.external_port);
    if (!address || !port) return null;
    return {endpoint: `${address}:${port}`, current: Boolean(mapping), method: 'mapped', family: 'ipv4'};
  }

  function selectedPublicEndpoint(data) {
    const selected = selectedEndpointRecord(data);
    if (!selected) return null;
    if (selected.family === 'ipv4' && (selected.access_method === 'mapped' || selected.reachability === 'mapped')) {
      return mappedEndpoint(data, selected);
    }
    if (selected.family === 'ipv6' && (selected.access_method === 'mapped' || selected.reachability === 'mapped')) return null;
    return directEndpoint(selected);
  }

  function copyFallback(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.append(textarea);
    textarea.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
    textarea.remove();
    return copied;
  }

  async function copyMappedEndpoint(value) {
    const text = String(value || '').trim();
    if (!text) return;
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (_) {
      copied = copyFallback(text);
    }
    if (copied) {
      window.RemoteGateFeedback?.notify?.(
        zh() ? `已复制 ${text}` : `Copied ${text}`,
        'success',
        {title: zh() ? 'Endpoint 已复制' : 'Endpoint copied', duration: 2200}
      );
    } else {
      window.RemoteGateFeedback?.notify?.(
        zh() ? '复制失败，请长按 Endpoint 手动复制。' : 'Copy failed. Long-press the endpoint to copy it manually.',
        'error',
        {title: zh() ? '复制失败' : 'Copy failed'}
      );
    }
  }

  function ensureVerifiedEndpoint() {
    const wrap = document.querySelector('.gate-orb-wrap');
    if (!wrap) return null;
    let row = document.getElementById('mapped-public-endpoint');
    if (row) return row;
    row = document.createElement('div');
    row.id = 'mapped-public-endpoint';
    row.className = 'verified-endpoint';
    row.hidden = true;
    const label = document.createElement('span');
    label.className = 'verified-endpoint-label';
    label.dataset.mappedEndpointLabel = '1';
    const value = document.createElement('button');
    value.type = 'button';
    value.className = 'verified-endpoint-value';
    value.dataset.mappedEndpointCopy = '1';
    value.dataset.mappedEndpointValue = '1';
    value.addEventListener('click', () => copyMappedEndpoint(value.textContent));
    const note = document.createElement('span');
    note.className = 'verified-endpoint-note';
    note.dataset.mappedEndpointNote = '1';
    row.append(label, value, note);
    wrap.append(row);
    return row;
  }

  function renderSelectedEndpoint(data) {
    latestDashboard = data || latestDashboard;
    const row = ensureVerifiedEndpoint();
    if (!row || !latestDashboard) return;
    const selected = selectedPublicEndpoint(latestDashboard);
    if (!selected?.endpoint) {
      row.hidden = true;
      row.classList.remove('is-current');
      return;
    }
    row.hidden = false;
    row.classList.toggle('is-current', Boolean(selected.current));
    row.querySelector('[data-mapped-endpoint-label]').textContent = zh()
      ? '当前 WireGuard 公网 Endpoint'
      : 'Current WireGuard Public Endpoint';
    const value = row.querySelector('[data-mapped-endpoint-value]');
    value.textContent = selected.endpoint;
    value.title = zh() ? `复制 ${selected.endpoint}` : `Copy ${selected.endpoint}`;
    value.setAttribute('aria-label', value.title);
    let note = zh() ? 'OpenWrt 当前上报' : 'Currently reported by OpenWrt';
    if (selected.method === 'mapped') {
      note = selected.current
        ? (zh() ? 'OpenWrt 持续观测，Activate 时实时确认' : 'Continuously observed by OpenWrt and re-confirmed on Activate')
        : (zh() ? '由 OpenWrt 在 Activate 时实时确认' : 'Resolved live by OpenWrt on Activate');
    } else if (selected.family === 'ipv6') {
      note = zh() ? 'IPv6 Direct · OpenWrt 当前上报' : 'IPv6 Direct · currently reported by OpenWrt';
    } else if (selected.family === 'ipv4') {
      note = zh() ? 'IPv4 Direct · OpenWrt 当前上报' : 'IPv4 Direct · currently reported by OpenWrt';
    }
    row.querySelector('[data-mapped-endpoint-note]').textContent = note;
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    try {
      const requestUrl = new URL(typeof args[0] === 'string' ? args[0] : args[0]?.url || '', location.href);
      if (requestUrl.pathname === '/api/v1/dashboard' && response.ok) {
        response.clone().json().then((data) => {
          renderSelectedEndpoint(data);
        }).catch(() => {});
      }
    } catch (_) { /* preserve fetch semantics */ }
    return response;
  };

  function ready() {
    brandIcon();
    polishGateActions();
    ensureGateStatusStructure();
  }

  window.addEventListener('remote-gate-endpoint-selection', () => {
    if (latestDashboard) renderSelectedEndpoint(latestDashboard);
  });

  window.addEventListener('remote-gate-language', () => {
    syncGateStatusPresentation();
    if (latestDashboard) renderSelectedEndpoint(latestDashboard);
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, {once: true});
  else ready();
})();