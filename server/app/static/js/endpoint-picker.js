(() => {
  const $ = (id) => document.getElementById(id);
  const zh = () => document.documentElement.dataset.lang === 'zh';
  let layer = null;
  let list = null;
  let title = null;
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

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[char]);
  }

  function selectedOption() {
    const select = $('endpoint-select');
    return select?.selectedOptions?.[0] || null;
  }

  function normalizeField(select) {
    const label = select.closest('label');
    if (!label) return;
    const wrapper = document.createElement('div');
    wrapper.className = label.className;
    while (label.firstChild) wrapper.append(label.firstChild);
    label.replaceWith(wrapper);
  }

  function ensureTrigger() {
    const select = $('endpoint-select');
    if (!select) return null;
    let trigger = $('endpoint-picker-trigger');
    if (trigger) return trigger;

    normalizeField(select);
    select.classList.add('endpoint-native-select');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');

    trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.id = 'endpoint-picker-trigger';
    trigger.className = 'endpoint-picker-trigger';
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-controls', 'endpoint-picker-layer');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.style.gridTemplateColumns = 'minmax(0, 1fr)';
    trigger.style.gap = '0';
    trigger.innerHTML = `
      <span class="endpoint-trigger-copy">
        <strong data-endpoint-wan>—</strong>
        <span data-endpoint-kind></span>
        <span class="endpoint-trigger-address fit-single-line" data-fit-max="12" data-fit-min="7.5" data-endpoint-address></span>
      </span>`;
    select.insertAdjacentElement('afterend', trigger);
    return trigger;
  }

  function ensureLayer() {
    if (layer) return layer;
    layer = document.createElement('div');
    layer.className = 'endpoint-picker-layer';
    layer.id = 'endpoint-picker-layer';
    layer.hidden = true;
    layer.innerHTML = `
      <button class="endpoint-picker-backdrop" type="button" aria-label="Close endpoint picker"></button>
      <section class="endpoint-picker-sheet depth-card" role="dialog" aria-modal="true" aria-labelledby="endpoint-picker-title" tabindex="-1">
        <div class="endpoint-picker-handle" aria-hidden="true"></div>
        <div class="endpoint-picker-head">
          <div>
            <span class="eyebrow">ACCESS ENDPOINT</span>
            <h2 id="endpoint-picker-title"></h2>
          </div>
          <button class="icon-button endpoint-picker-close" type="button" aria-label="Close">×</button>
        </div>
        <div class="endpoint-option-list" id="endpoint-option-list" role="listbox"></div>
      </section>`;
    document.body.append(layer);
    list = layer.querySelector('#endpoint-option-list');
    title = layer.querySelector('#endpoint-picker-title');
    layer.querySelector('.endpoint-picker-backdrop')?.addEventListener('click', close);
    layer.querySelector('.endpoint-picker-close')?.addEventListener('click', close);
    layer.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = [...layer.querySelectorAll('button:not([disabled])')];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    return layer;
  }

  function positionLayer() {
    if (!layer || layer.hidden) return;
    const trigger = $('endpoint-picker-trigger');
    const sheet = layer.querySelector('.endpoint-picker-sheet');
    const backdrop = layer.querySelector('.endpoint-picker-backdrop');
    if (!trigger || !sheet || !backdrop) return;

    if (window.innerWidth < 768) {
      sheet.style.removeProperty('position');
      sheet.style.removeProperty('left');
      sheet.style.removeProperty('top');
      sheet.style.removeProperty('width');
      backdrop.style.removeProperty('background');
      backdrop.style.removeProperty('backdrop-filter');
      layer.dataset.mode = 'sheet';
      return;
    }

    const rect = trigger.getBoundingClientRect();
    const width = Math.min(520, Math.max(390, rect.width), window.innerWidth - 32);
    sheet.style.position = 'absolute';
    sheet.style.width = `${width}px`;
    const measuredHeight = Math.min(sheet.getBoundingClientRect().height || sheet.scrollHeight, window.innerHeight - 32);
    let left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
    let top = rect.bottom + 9;
    if (top + measuredHeight > window.innerHeight - 16) {
      top = Math.max(16, rect.top - measuredHeight - 9);
    }
    sheet.style.left = `${Math.round(left)}px`;
    sheet.style.top = `${Math.round(top)}px`;
    backdrop.style.background = 'transparent';
    backdrop.style.backdropFilter = 'none';
    layer.dataset.mode = 'popover';
  }

  function badgeText(parsed, index) {
    if (index === 0 && /Direct|NATMap/.test(parsed.provider)) return zh() ? '推荐' : 'Primary';
    if (/Try|Private|CGNAT|egress/i.test(parsed.provider)) return zh() ? '尝试' : 'Try';
    return parsed.provider || (zh() ? '可用' : 'Available');
  }

  function renderOptions() {
    ensureLayer();
    const select = $('endpoint-select');
    if (!select || !list) return;
    list.replaceChildren();

    [...select.options].forEach((option, index) => {
      if (!option.value) return;
      const parsed = splitLabel(option.textContent);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'endpoint-option-card';
      button.dataset.value = option.value;
      button.setAttribute('role', 'option');
      const selected = option.value === select.value;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
      const experimental = /Try|Private|CGNAT|egress/i.test(parsed.provider);
      if (experimental) button.classList.add('experimental');
      button.innerHTML = `
        <span class="endpoint-option-main">
          <span class="endpoint-option-topline">
            <strong>${escapeHtml(parsed.wan)}</strong>
            <span class="endpoint-option-badge">${escapeHtml(badgeText(parsed, index))}</span>
          </span>
          <span class="endpoint-option-kind">${escapeHtml([parsed.family, parsed.provider].filter(Boolean).join(' · '))}</span>
          <span class="endpoint-option-address fit-single-line" data-fit-max="13" data-fit-min="7.5">${escapeHtml(parsed.address)}</span>
        </span>
        <span class="endpoint-option-check" aria-hidden="true">${selected ? '●' : '○'}</span>`;
      button.addEventListener('click', () => choose(option.value));
      list.append(button);
    });

    if (!list.children.length) {
      const empty = document.createElement('div');
      empty.className = 'endpoint-picker-empty';
      empty.textContent = zh() ? '当前没有可用访问路径。' : 'No access endpoint is currently available.';
      list.append(empty);
    }
    window.RemoteGateFit?.observe?.(list);
  }

  function syncTrigger() {
    const select = $('endpoint-select');
    const trigger = ensureTrigger();
    if (!select || !trigger) return;
    const option = selectedOption();
    const parsed = splitLabel(option?.textContent || '');
    trigger.disabled = select.disabled || !option?.value;
    trigger.setAttribute('aria-disabled', trigger.disabled ? 'true' : 'false');
    trigger.querySelector('[data-endpoint-wan]')?.replaceChildren(document.createTextNode(option?.value ? parsed.wan : (zh() ? '不可用' : 'Unavailable')));
    trigger.querySelector('[data-endpoint-kind]')?.replaceChildren(document.createTextNode(option?.value ? [parsed.family, parsed.provider].filter(Boolean).join(' · ') : ''));
    const address = trigger.querySelector('[data-endpoint-address]');
    address?.replaceChildren(document.createTextNode(option?.value ? parsed.address : ''));
    window.RemoteGateFit?.fit?.(address);
  }

  function sync() {
    syncTrigger();
    if (layer && !layer.hidden) {
      renderOptions();
      requestAnimationFrame(positionLayer);
    }
  }

  function open() {
    const select = $('endpoint-select');
    const trigger = ensureTrigger();
    if (!select || select.disabled || !select.value || !trigger) return;
    ensureLayer();
    lastFocus = document.activeElement;
    title.textContent = zh() ? '选择访问路径' : 'Choose access endpoint';
    renderOptions();
    layer.hidden = false;
    document.documentElement.classList.add('endpoint-picker-open');
    trigger.setAttribute('aria-expanded', 'true');
    requestAnimationFrame(() => {
      positionLayer();
      layer.classList.add('open');
      (list.querySelector('.selected') || list.querySelector('button'))?.focus();
    });
  }

  function close() {
    const trigger = $('endpoint-picker-trigger');
    if (!layer || layer.hidden) return;
    layer.classList.remove('open');
    document.documentElement.classList.remove('endpoint-picker-open');
    trigger?.setAttribute('aria-expanded', 'false');
    window.setTimeout(() => { if (layer) layer.hidden = true; }, 190);
    if (lastFocus instanceof HTMLElement) lastFocus.focus({preventScroll: true});
  }

  function choose(value) {
    const select = $('endpoint-select');
    if (!select || ![...select.options].some((option) => option.value === value)) return;
    select.value = value;
    select.dispatchEvent(new Event('change', {bubbles: true}));
    window.RemoteGateFeedback?.detent?.(0.72);
    sync();
    close();
  }

  function hideWireGuardSelector() {
    const select = $('wg-select');
    if (!select) return;
    const field = select.closest('.field');
    if (field) {
      field.hidden = true;
      field.setAttribute('aria-hidden', 'true');
    }
    select.tabIndex = -1;
  }

  function bind() {
    hideWireGuardSelector();
    const select = $('endpoint-select');
    const trigger = ensureTrigger();
    if (!select || !trigger) return;
    trigger.addEventListener('click', open);
    select.addEventListener('change', sync);
    new MutationObserver(sync).observe(select, {childList: true, subtree: true, attributes: true});
    window.addEventListener('remote-gate-language', sync);
    window.addEventListener('resize', positionLayer, {passive: true});
    sync();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();

  window.RemoteGateEndpointPicker = {open, close, sync};
})();
