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

  function ensureGatePolishStyles() {
    if (document.getElementById('gate-orb-polish-styles')) return;
    const style = document.createElement('style');
    style.id = 'gate-orb-polish-styles';
    style.textContent = `
      .gate-orb-wrap {
        display: flex !important;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: .65rem;
        min-width: 0;
      }
      .gate-core .gate-orb-short-state {
        margin-top: 5px;
        max-width: 80px;
        overflow: hidden;
        font-size: 14px;
        line-height: 1;
        letter-spacing: .04em;
        text-align: center;
        white-space: nowrap;
        text-overflow: ellipsis;
      }
      .gate-status-copy {
        width: 100%;
        min-width: 0;
        text-align: center;
      }
      .gate-status-copy #gate-state {
        display: block;
        margin: 0;
        color: var(--ink);
        font-size: 13px;
        line-height: 1.25;
        overflow-wrap: anywhere;
      }
      .gate-status-copy #gate-substate {
        display: block;
        margin-top: .28rem;
        color: var(--ink-subtle);
        font-size: 10px;
        line-height: 1.4;
        overflow-wrap: anywhere;
      }
      #mapped-public-endpoint {
        width: 100%;
        min-width: 0;
        padding: .62rem .65rem;
        border: 1px solid var(--hairline);
        border-radius: 12px;
        background: color-mix(in srgb, var(--surface-raised) 72%, transparent);
        box-shadow: var(--highlight-control);
        text-align: center;
      }
      #mapped-public-endpoint[hidden] { display: none !important; }
      #mapped-public-endpoint [data-mapped-endpoint-label] {
        display: block;
        color: var(--ink-muted);
        font-size: 10px;
        font-weight: 700;
        line-height: 1.3;
      }
      .mapped-endpoint-copy {
        appearance: none;
        -webkit-appearance: none;
        width: 100%;
        min-width: 0;
        margin: .3rem 0 .2rem;
        padding: .5rem .55rem;
        border: 1px solid color-mix(in srgb, var(--primary) 24%, var(--hairline));
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: .5rem;
        color: var(--ink);
        background: color-mix(in srgb, var(--surface-1) 78%, transparent);
        cursor: pointer;
      }
      .mapped-endpoint-copy [data-mapped-endpoint-value] {
        min-width: 0;
        font-family: var(--font-mono);
        font-size: clamp(13px, 1.7vw, 16px);
        font-weight: 780;
        line-height: 1.15;
        overflow-wrap: anywhere;
      }
      .mapped-endpoint-copy [data-mapped-copy-hint] {
        flex: 0 0 auto;
        color: var(--ink-muted);
        font-size: 9px;
        font-weight: 750;
        white-space: nowrap;
      }
      #mapped-public-endpoint [data-mapped-endpoint-note] {
        display: block;
        color: var(--ink-subtle);
        font-size: 9px;
        line-height: 1.35;
      }
      @media (hover:hover) and (pointer:fine) {
        .mapped-endpoint-copy:hover {
          border-color: var(--border-hover);
          background: color-mix(in srgb, var(--surface-raised) 86%, transparent);
          transform: translateY(-1px);
        }
      }
      @media (max-width: 767px) {
        .gate-layout {
          grid-template-columns: 1fr !important;
          gap: 14px !important;
        }
        .gate-orb-wrap {
          grid-column: 1 / -1;
          min-height: 0 !important;
          padding: .15rem 0 .35rem;
        }
        .gate-status-copy,
        #mapped-public-endpoint {
          width: min(100%, 34rem);
        }
        .gate-status-copy #gate-state { font-size: 15px; }
        .gate-status-copy #gate-substate { font-size: 11px; }
        .mapped-endpoint-copy [data-mapped-endpoint-value] {
          font-size: clamp(17px, 5.2vw, 23px);
          overflow-wrap: normal;
          word-break: normal;
        }
      }
      @media (max-width: 379px) {
        .mapped-endpoint-copy {
          flex-direction: column;
          gap: .25rem;
        }
        .mapped-endpoint-copy [data-mapped-endpoint-value] {
          font-size: clamp(15px, 5vw, 19px);
        }
      }
    `;
    document.head.append(style);
  }

  function orbStateLabel(state) {
    if (state === 'open') return 'OPEN';
    if (state === 'authorizing') return 'WAIT';
    if (state === 'error') return 'ERROR';
    return 'CLOSED';
  }

  function syncOrbShortState() {
    const orb = document.getElementById('gate-orb');
    const label = document.getElementById('gate-orb-state');
    if (!orb || !label) return;
    label.textContent = orbStateLabel(String(orb.dataset.state || 'closed'));
  }

  function polishGateStatusLayout() {
    const wrap = document.querySelector('.gate-orb-wrap');
    const orb = document.getElementById('gate-orb');
    const core = orb?.querySelector('.gate-core');
    const state = document.getElementById('gate-state');
    const substate = document.getElementById('gate-substate');
    if (!wrap || !orb || !core || !state || !substate) return;

    let shortState = document.getElementById('gate-orb-state');
    if (!shortState) {
      shortState = document.createElement('strong');
      shortState.id = 'gate-orb-state';
      shortState.className = 'gate-orb-short-state';
      core.append(shortState);
    }

    let copy = document.getElementById('gate-status-copy');
    if (!copy) {
      copy = document.createElement('div');
      copy.id = 'gate-status-copy';
      copy.className = 'gate-status-copy';
      copy.setAttribute('aria-live', 'polite');
      orb.insertAdjacentElement('afterend', copy);
    }
    if (state.parentElement !== copy) copy.append(state);
    if (substate.parentElement !== copy) copy.append(substate);

    syncOrbShortState();
    if (orb.dataset.shortStateObserver !== '1') {
      const observer = new MutationObserver(syncOrbShortState);
      observer.observe(orb, {attributes: true, attributeFilter: ['data-state']});
      orb.dataset.shortStateObserver = '1';
    }
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
    const zh = document.documentElement.dataset.lang === 'zh';
    if (copied) {
      window.RemoteGateFeedback?.notify?.(
        zh ? `已复制 ${text}` : `Copied ${text}`,
        'success',
        {title: zh ? 'Endpoint 已复制' : 'Endpoint copied', duration: 2200}
      );
    } else {
      window.RemoteGateFeedback?.notify?.(
        zh ? '复制失败，请长按 Endpoint 手动复制。' : 'Copy failed. Long-press the endpoint to copy it manually.',
        'error',
        {title: zh ? '复制失败' : 'Copy failed'}
      );
    }
  }

  function renderMappedEndpoint(data) {
    const endpoint = mappedEndpointFromDashboard(data);
    const wrap = document.querySelector('.gate-orb-wrap');
    if (!wrap) return;
    let row = document.getElementById('mapped-public-endpoint');
    if (!row) {
      row = document.createElement('div');
      row.id = 'mapped-public-endpoint';
      row.hidden = true;

      const label = document.createElement('span');
      label.dataset.mappedEndpointLabel = '1';

      const value = document.createElement('button');
      value.type = 'button';
      value.className = 'mapped-endpoint-copy';
      value.dataset.mappedEndpointCopy = '1';
      const valueText = document.createElement('span');
      valueText.dataset.mappedEndpointValue = '1';
      const copyHint = document.createElement('small');
      copyHint.dataset.mappedCopyHint = '1';
      value.append(valueText, copyHint);
      value.addEventListener('click', () => copyMappedEndpoint(valueText.textContent));

      const note = document.createElement('span');
      note.dataset.mappedEndpointNote = '1';
      row.append(label, value, note);
      wrap.append(row);
    }

    if (!endpoint) {
      row.hidden = true;
      return;
    }

    const zh = document.documentElement.dataset.lang === 'zh';
    row.hidden = false;
    row.querySelector('[data-mapped-endpoint-label]').textContent = zh ? '当前 WireGuard 公网 Endpoint' : 'Current WireGuard Public Endpoint';
    const value = row.querySelector('[data-mapped-endpoint-value]');
    value.textContent = endpoint;
    const copyButton = row.querySelector('[data-mapped-endpoint-copy]');
    copyButton.title = zh ? `点击复制 ${endpoint}` : `Click to copy ${endpoint}`;
    copyButton.setAttribute('aria-label', copyButton.title);
    row.querySelector('[data-mapped-copy-hint]').textContent = zh ? '点击复制' : 'Copy';
    row.querySelector('[data-mapped-endpoint-note]').textContent = zh ? '由 OpenWrt 在 Activate 时实时确认' : 'Resolved live by OpenWrt on Activate';
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
    ensureGatePolishStyles();
    polishGateStatusLayout();
    rewriteMappedOptions();
    observeMappedPicker();
  }

  window.addEventListener('remote-gate-language', () => {
    queueMicrotask(rewriteMappedOptions);
    const row = document.getElementById('mapped-public-endpoint');
    const endpoint = row?.querySelector('[data-mapped-endpoint-value]')?.textContent;
    if (endpoint && !row.hidden) {
      const zh = document.documentElement.dataset.lang === 'zh';
      row.querySelector('[data-mapped-endpoint-label]').textContent = zh ? '当前 WireGuard 公网 Endpoint' : 'Current WireGuard Public Endpoint';
      row.querySelector('[data-mapped-copy-hint]').textContent = zh ? '点击复制' : 'Copy';
      row.querySelector('[data-mapped-endpoint-note]').textContent = zh ? '由 OpenWrt 在 Activate 时实时确认' : 'Resolved live by OpenWrt on Activate';
      const copyButton = row.querySelector('[data-mapped-endpoint-copy]');
      copyButton.title = zh ? `点击复制 ${endpoint}` : `Click to copy ${endpoint}`;
      copyButton.setAttribute('aria-label', copyButton.title);
    }
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, {once: true});
  else ready();
})();