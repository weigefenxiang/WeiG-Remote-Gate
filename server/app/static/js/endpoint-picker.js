(() => {
  const $ = (id) => document.getElementById(id);
  const zh = () => document.documentElement.dataset.lang === 'zh';
  const configs = new Map();
  const triggers = new Map();
  const observers = new Map();
  let layer = null;
  let list = null;
  let title = null;
  let eyebrow = null;
  let activeSelectId = 'endpoint-select';
  let lastFocus = null;

  function splitLabel(text) {
    const parts = String(text || '').split(' · ').map((part) => part.trim()).filter(Boolean);
    return {
      wan: parts[0] || (zh() ? '访问路径' : 'Access path'),
      family: parts[1] || '',
      provider: parts.length > 3 ? parts.slice(2, -1).join(' · ') : (parts[2] || ''),
      address: parts.length > 1 ? parts[parts.length - 1] : String(text || '')
    };
  }

  function pathRows(option) {
    const raw = String(option?.dataset?.pathRows || '');
    if (!raw) return [];
    try {
      const rows = JSON.parse(raw);
      if (!Array.isArray(rows) || !rows.length || rows.length > 2) return [];
      return rows.map((row) => ({
        family: String(row?.family || ''),
        wan: String(row?.wan || '—'),
        role: String(row?.role || ''),
        value: String(row?.value || '—')
      })).filter((row) => row.family && row.wan);
    } catch (_) {
      return [];
    }
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[char]);
  }

  function defaultConfig(selectId) {
    if (selectId === 'egress-select') {
      return {
        eyebrow: 'INTERNET EXIT',
        title: () => zh() ? '选择上网出口' : 'Choose Internet exit',
        empty: () => zh() ? '当前没有可用 Internet 出口。' : 'No Internet exit is currently available.'
      };
    }
    return {
      eyebrow: 'ACCESS ENDPOINT',
      title: () => zh() ? '选择访问路径' : 'Choose access endpoint',
      empty: () => zh() ? '当前没有可用访问路径。' : 'No access endpoint is currently available.'
    };
  }

  function configFor(selectId) { return {...defaultConfig(selectId), ...(configs.get(selectId) || {})}; }
  function triggerId(selectId) { return selectId === 'endpoint-select' ? 'endpoint-picker-trigger' : `${selectId}-picker-trigger`; }
  function selectedOption(selectId) { return $(selectId)?.selectedOptions?.[0] || null; }
  function emptyTriggerLabel(selectId) { return selectId === 'egress-select' ? (zh() ? '选择 Internet 出口' : 'Choose Internet exit') : (zh() ? '请选择 WAN Endpoint' : 'Choose WAN endpoint'); }

  function normalizeField(select) {
    const label = select.closest('label');
    if (!label) return;
    const wrapper = document.createElement('div');
    wrapper.className = label.className;
    while (label.firstChild) wrapper.append(label.firstChild);
    label.replaceWith(wrapper);
  }

  function ensureTrigger(selectId) {
    const select = $(selectId);
    if (!select) return null;
    let trigger = $(triggerId(selectId));
    if (trigger) { triggers.set(selectId, trigger); return trigger; }

    normalizeField(select);
    select.classList.add('endpoint-native-select');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');

    trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.id = triggerId(selectId);
    trigger.className = 'endpoint-picker-trigger';
    trigger.dataset.pickerSelect = selectId;
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-controls', 'endpoint-picker-layer');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.style.gridTemplateColumns = 'minmax(0, 1fr)';
    trigger.style.gap = '0';
    trigger.innerHTML = `
      <span class="endpoint-trigger-copy">
        <strong class="fit-single-line" data-fit-profile="identity" data-endpoint-wan>—</strong>
        <span data-endpoint-kind></span>
        <span class="endpoint-trigger-address fit-single-line" data-fit-profile="compact" data-endpoint-address></span>
      </span>`;
    select.insertAdjacentElement('afterend', trigger);
    triggers.set(selectId, trigger);
    return trigger;
  }

  function ensureLayer() {
    if (layer) return layer;
    layer = document.createElement('div');
    layer.className = 'endpoint-picker-layer';
    layer.id = 'endpoint-picker-layer';
    layer.hidden = true;
    layer.innerHTML = `
      <button class="endpoint-picker-backdrop" type="button" aria-label="Close picker"></button>
      <section class="endpoint-picker-sheet depth-card" role="dialog" aria-modal="true" aria-labelledby="endpoint-picker-title" tabindex="-1">
        <div class="endpoint-picker-handle" aria-hidden="true"></div>
        <div class="endpoint-picker-head">
          <div>
            <span class="eyebrow" data-picker-eyebrow>ACCESS ENDPOINT</span>
            <h2 id="endpoint-picker-title"></h2>
          </div>
          <button class="icon-button endpoint-picker-close" type="button" aria-label="Close">×</button>
        </div>
        <div class="endpoint-option-list" id="endpoint-option-list" role="listbox"></div>
      </section>`;
    document.body.append(layer);
    list = layer.querySelector('#endpoint-option-list');
    title = layer.querySelector('#endpoint-picker-title');
    eyebrow = layer.querySelector('[data-picker-eyebrow]');
    layer.querySelector('.endpoint-picker-backdrop')?.addEventListener('click', close);
    layer.querySelector('.endpoint-picker-close')?.addEventListener('click', close);
    layer.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { event.preventDefault(); close(); return; }
      if (event.key !== 'Tab') return;
      const focusable = [...layer.querySelectorAll('button:not([disabled])')];
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    return layer;
  }

  function activeTrigger() { return triggers.get(activeSelectId) || $(triggerId(activeSelectId)); }

  function positionLayer() {
    if (!layer || layer.hidden) return;
    const trigger = activeTrigger();
    const sheet = layer.querySelector('.endpoint-picker-sheet');
    const backdrop = layer.querySelector('.endpoint-picker-backdrop');
    if (!trigger || !sheet || !backdrop) return;
    if (window.innerWidth < 768) {
      sheet.style.removeProperty('position'); sheet.style.removeProperty('left'); sheet.style.removeProperty('top'); sheet.style.removeProperty('width');
      backdrop.style.removeProperty('background'); backdrop.style.removeProperty('backdrop-filter'); layer.dataset.mode = 'sheet'; return;
    }
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(520, Math.max(390, rect.width), window.innerWidth - 32);
    sheet.style.position = 'absolute'; sheet.style.width = `${width}px`;
    const measuredHeight = Math.min(sheet.getBoundingClientRect().height || sheet.scrollHeight, window.innerHeight - 32);
    const left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
    let top = rect.bottom + 9;
    if (top + measuredHeight > window.innerHeight - 16) top = Math.max(16, rect.top - measuredHeight - 9);
    sheet.style.left = `${Math.round(left)}px`; sheet.style.top = `${Math.round(top)}px`;
    backdrop.style.background = 'transparent'; backdrop.style.backdropFilter = 'none'; layer.dataset.mode = 'popover';
  }

  function badgeText(parsed, index, option) {
    if (option?.value === '__lan__') return zh() ? '本地' : 'LAN only';
    if (option?.dataset?.pathPrimary === '1') return zh() ? '推荐' : 'Primary';
    if (index === 0 && /Direct|Mapped/.test(parsed.provider)) return zh() ? '推荐' : 'Primary';
    if (/Try|egress|Observed/i.test(parsed.provider)) return zh() ? '可用' : 'Available';
    return parsed.provider || (zh() ? '可用' : 'Available');
  }

  function pathBlocksHtml(rows) {
    return rows.map((row) => `
      <span class="path-family-block">
        <span class="path-family-head">
          <span class="path-family-label">${escapeHtml(row.family)}</span>
          <strong class="path-family-wan fit-single-line" data-fit-profile="identity">${escapeHtml(row.wan)}</strong>
          ${row.role ? `<span class="path-family-role">${escapeHtml(row.role)}</span>` : ''}
        </span>
        <span class="path-family-value fit-single-line" data-fit-profile="compact">${escapeHtml(row.value)}</span>
      </span>`).join('');
  }

  function renderOptions() {
    ensureLayer();
    const select = $(activeSelectId);
    if (!select || !list) return;
    const config = configFor(activeSelectId);
    list.replaceChildren();

    [...select.options].forEach((option, index) => {
      if (!option.value) return;
      const parsed = splitLabel(option.textContent);
      const rows = pathRows(option);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'endpoint-option-card';
      button.dataset.value = option.value;
      button.setAttribute('role', 'option');
      const selected = option.value === select.value;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
      if (/Try/i.test(rows.map((row) => row.role).join(' ')) || (/Try/i.test(parsed.provider) && option.value !== '__lan__')) button.classList.add('experimental');

      if (rows.length) {
        button.classList.add('path-card-option');
        button.innerHTML = `
          <span class="endpoint-option-main path-card-stack">
            <span class="path-card-meta"><span class="endpoint-option-badge">${escapeHtml(badgeText(parsed, index, option))}</span></span>
            ${pathBlocksHtml(rows)}
          </span>
          <span class="endpoint-option-check" aria-hidden="true">${selected ? '●' : '○'}</span>`;
      } else {
        button.innerHTML = `
          <span class="endpoint-option-main">
            <span class="endpoint-option-topline">
              <strong>${escapeHtml(parsed.wan)}</strong>
              <span class="endpoint-option-badge">${escapeHtml(badgeText(parsed, index, option))}</span>
            </span>
            <span class="endpoint-option-kind">${escapeHtml([parsed.family, parsed.provider].filter(Boolean).join(' · '))}</span>
            <span class="endpoint-option-address fit-single-line" data-fit-profile="compact">${escapeHtml(parsed.address)}</span>
          </span>
          <span class="endpoint-option-check" aria-hidden="true">${selected ? '●' : '○'}</span>`;
      }
      button.addEventListener('click', () => choose(option.value));
      list.append(button);
    });

    if (!list.children.length) {
      const empty = document.createElement('div');
      empty.className = 'endpoint-picker-empty';
      empty.textContent = typeof config.empty === 'function' ? config.empty() : String(config.empty || '');
      list.append(empty);
    }
    window.RemoteGateFit?.observe?.(list);
  }

  function triggerSummary(option) {
    const rows = pathRows(option);
    if (!rows.length) return null;
    if (rows.length === 1) {
      const row = rows[0];
      return {wan:row.wan, kind:[row.family,row.role].filter(Boolean).join(' · '), address:row.value};
    }
    return {
      wan:rows.map((row) => `${row.family} ${row.wan}`).join(' · '),
      kind:rows.map((row) => [row.family,row.role].filter(Boolean).join(' ')).join(' · '),
      address:rows.map((row) => row.value).join(' · ')
    };
  }

  function syncTrigger(selectId) {
    const select = $(selectId);
    const trigger = ensureTrigger(selectId);
    if (!select || !trigger) return;
    const option = selectedOption(selectId);
    const parsed = splitLabel(option?.textContent || '');
    const structured = triggerSummary(option);
    const summary = structured || parsed;
    trigger.disabled = Boolean(select.disabled);
    trigger.setAttribute('aria-disabled', trigger.disabled ? 'true' : 'false');
    trigger.querySelector('[data-endpoint-wan]')?.replaceChildren(document.createTextNode(option?.value ? summary.wan : emptyTriggerLabel(selectId)));
    trigger.querySelector('[data-endpoint-kind]')?.replaceChildren(document.createTextNode(option?.value ? (structured ? summary.kind : [parsed.family,parsed.provider].filter(Boolean).join(' · ')) : ''));
    const address = trigger.querySelector('[data-endpoint-address]');
    address?.replaceChildren(document.createTextNode(option?.value ? summary.address : ''));
    window.RemoteGateFit?.fit?.(trigger.querySelector('[data-endpoint-wan]'));
    window.RemoteGateFit?.fit?.(address);
  }

  function sync(selectId = '') {
    if (selectId) syncTrigger(selectId); else configs.forEach((_, id) => syncTrigger(id));
    if (layer && !layer.hidden) { renderOptions(); requestAnimationFrame(positionLayer); }
  }

  function open(selectId = 'endpoint-select') {
    const select = $(selectId), trigger = ensureTrigger(selectId);
    if (!select || select.disabled || !trigger) return;
    ensureLayer(); activeSelectId = selectId; lastFocus = document.activeElement;
    const config = configFor(selectId);
    if (eyebrow) eyebrow.textContent = String(config.eyebrow || '');
    if (title) title.textContent = typeof config.title === 'function' ? config.title() : String(config.title || '');
    renderOptions(); layer.hidden = false; document.documentElement.classList.add('endpoint-picker-open'); trigger.setAttribute('aria-expanded', 'true');
    requestAnimationFrame(() => { positionLayer(); layer.classList.add('open'); (list.querySelector('.selected') || list.querySelector('button'))?.focus(); });
  }

  function close() {
    const trigger = activeTrigger();
    if (!layer || layer.hidden) return;
    layer.classList.remove('open'); document.documentElement.classList.remove('endpoint-picker-open'); trigger?.setAttribute('aria-expanded', 'false');
    window.setTimeout(() => { if (layer) layer.hidden = true; }, 190);
    if (lastFocus instanceof HTMLElement) lastFocus.focus({preventScroll:true});
  }

  function choose(value) {
    const select = $(activeSelectId);
    if (!select || ![...select.options].some((option) => option.value === value)) return;
    select.value = value; select.dispatchEvent(new Event('change', {bubbles:true})); window.RemoteGateFeedback?.detent?.(0.72); sync(activeSelectId); close();
  }

  function hideWireGuardSelector() {
    const select = $('wg-select');
    if (!select) return;
    const field = select.closest('.field');
    if (field) { field.hidden = true; field.setAttribute('aria-hidden','true'); }
    select.tabIndex = -1;
  }

  function bindSelect(selectId, config = {}) {
    const select = $(selectId);
    if (!select) return null;
    configs.set(selectId, {...(configs.get(selectId) || {}), ...config});
    const trigger = ensureTrigger(selectId);
    if (!trigger) return null;
    if (!trigger.dataset.pickerBound) {
      trigger.dataset.pickerBound = '1';
      trigger.addEventListener('click', () => open(selectId));
      select.addEventListener('change', () => sync(selectId));
      const observer = new MutationObserver(() => sync(selectId));
      observer.observe(select, {childList:true, subtree:true, attributes:true});
      observers.set(selectId, observer);
    }
    sync(selectId);
    return trigger;
  }

  function bind() {
    hideWireGuardSelector();
    bindSelect('endpoint-select');
    if ($('egress-select')) bindSelect('egress-select');
    window.addEventListener('remote-gate-language', () => sync());
    window.addEventListener('resize', positionLayer, {passive:true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once:true}); else bind();
  window.RemoteGateEndpointPicker = {open, close, sync, bindSelect};
})();