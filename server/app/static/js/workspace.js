(() => {
  const KEY = 'remote-gate:workspace:v4';
  const LEGACY_KEYS = ['remote-gate:workspace:v3', 'remote-gate:workspace:v2', 'remote-gate:workspace:v1'];
  const workspace = document.getElementById('workspace');
  const arrangeButton = document.getElementById('arrange-button');
  const resetButton = document.getElementById('reset-layout-button');
  if (!workspace || !arrangeButton) return;

  const wide = window.matchMedia('(min-width: 1200px)');
  const t = (key) => window.RemoteGateI18n?.t(key) || key;
  const mainZone = workspace.querySelector('[data-workspace-zone="main"]');
  const railZone = workspace.querySelector('[data-workspace-zone="rail"]');

  const flowZone = document.createElement('div');
  flowZone.className = 'workspace-zone workspace-flow';
  flowZone.dataset.workspaceZone = 'flow';
  flowZone.setAttribute('aria-label', 'Responsive card flow');
  workspace.append(flowZone);

  const desktopZones = () => [mainZone, railZone].filter(Boolean);
  const zoneByName = (name) => workspace.querySelector(`[data-workspace-zone="${name}"]`);
  const cards = () => Array.from(workspace.querySelectorAll('[data-card-id]'));
  const FLOW_ORDER = ['gate', 'client', 'wireguard', 'wan', 'activity', 'system'];
  const DEFAULTS = {
    main: ['gate', 'wireguard', 'wan'],
    rail: ['client', 'system', 'activity']
  };
  const DEFAULT_ZONE = Object.fromEntries(
    Object.entries(DEFAULTS).flatMap(([zone, ids]) => ids.map((id) => [id, zone]))
  );

  let arranging = false;
  let draggedCard = null;
  let desktopState = null;

  function parseState(raw) {
    try {
      const value = JSON.parse(raw || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (_) {
      return {};
    }
  }

  function loadState() {
    const current = parseState(localStorage.getItem(KEY));
    if (Object.keys(current).length) return current;
    for (const key of LEGACY_KEYS) {
      const legacy = parseState(localStorage.getItem(key));
      if (Object.keys(legacy).length) return legacy;
    }
    return {};
  }

  function zoneCards(zone) {
    if (!zone) return [];
    return Array.from(zone.children).filter((node) => node.dataset?.cardId);
  }

  function cardMap() {
    return new Map(cards().map((card) => [card.dataset.cardId, card]));
  }

  function defaultDesktopState() {
    return {
      zones: Object.fromEntries(Object.entries(DEFAULT_ZONE)),
      order: {
        main: [...DEFAULTS.main],
        rail: [...DEFAULTS.rail]
      },
      sizes: Object.fromEntries(cards().map((card) => [card.dataset.cardId, card.dataset.defaultSize || 'normal']))
    };
  }

  function normalizeDesktopState(raw) {
    const base = defaultDesktopState();
    if (!raw || typeof raw !== 'object') return base;

    for (const card of cards()) {
      const id = card.dataset.cardId;
      const zone = raw.zones?.[id];
      if (zone === 'main' || zone === 'rail') base.zones[id] = zone;
      const size = raw.sizes?.[id];
      if (['compact', 'normal', 'wide'].includes(size)) base.sizes[id] = size;
    }

    for (const zoneName of ['main', 'rail']) {
      const rawOrder = raw.order?.[zoneName];
      if (!Array.isArray(rawOrder)) continue;
      const allowed = rawOrder.filter((id) => base.zones[id] === zoneName && cards().some((card) => card.dataset.cardId === id));
      const missing = cards()
        .map((card) => card.dataset.cardId)
        .filter((id) => base.zones[id] === zoneName && !allowed.includes(id));
      base.order[zoneName] = [...allowed, ...missing];
    }
    return base;
  }

  function snapshotDesktop() {
    if (!wide.matches) return desktopState;
    return {
      zones: Object.fromEntries(cards().map((card) => [
        card.dataset.cardId,
        card.closest('[data-workspace-zone]')?.dataset.workspaceZone === 'rail' ? 'rail' : 'main'
      ])),
      order: Object.fromEntries(desktopZones().map((zone) => [
        zone.dataset.workspaceZone,
        zoneCards(zone).map((card) => card.dataset.cardId)
      ])),
      sizes: Object.fromEntries(cards().map((card) => [card.dataset.cardId, card.dataset.size || 'normal']))
    };
  }

  function persistDesktop() {
    if (!wide.matches) return;
    desktopState = normalizeDesktopState(snapshotDesktop());
    localStorage.setItem(KEY, JSON.stringify(desktopState));
    workspace.dispatchEvent(new CustomEvent('workspacechange'));
  }

  function addTools(card) {
    if (card.querySelector('.workspace-card-tools')) return;
    const tools = document.createElement('div');
    tools.className = 'workspace-card-tools';

    const handle = document.createElement('span');
    handle.className = 'card-tool drag-handle';
    handle.textContent = '⋮⋮';
    handle.title = t('workspace.drag');
    tools.append(handle);

    for (const [delta, glyph, key] of [[-1, '←', 'workspace.moveEarlier'], [1, '→', 'workspace.moveLater']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'card-tool';
      button.dataset.move = String(delta);
      button.textContent = glyph;
      button.title = t(key);
      tools.append(button);
    }

    const area = document.createElement('button');
    area.type = 'button';
    area.className = 'card-tool';
    area.dataset.moveZone = '1';
    area.textContent = '↔';
    area.title = 'Move between workspace areas';
    tools.append(area);

    const size = document.createElement('button');
    size.type = 'button';
    size.className = 'card-tool size-tool';
    size.dataset.sizeCycle = '1';
    tools.append(size);

    card.prepend(tools);
  }

  function sizeText(card) {
    return t(`workspace.${card.dataset.size || 'normal'}`);
  }

  function updateTools() {
    cards().forEach((card) => {
      const tool = card.querySelector('[data-size-cycle]');
      if (tool) {
        tool.textContent = sizeText(card);
        tool.title = t('workspace.size');
      }
    });
  }

  function restoreDesktop() {
    const map = cardMap();
    desktopState = normalizeDesktopState(desktopState || loadState());

    cards().forEach((card) => {
      const id = card.dataset.cardId;
      const zone = zoneByName(desktopState.zones[id] || DEFAULT_ZONE[id]);
      if (zone === mainZone || zone === railZone) zone.append(card);
      card.dataset.size = desktopState.sizes[id] || card.dataset.defaultSize || 'normal';
    });

    for (const zoneName of ['main', 'rail']) {
      const zone = zoneByName(zoneName);
      const order = desktopState.order[zoneName] || [];
      order.forEach((id) => {
        if (map.has(id) && map.get(id).parentElement === zone) zone.append(map.get(id));
      });
    }
    updateTools();
  }

  function placeFlow() {
    const map = cardMap();
    FLOW_ORDER.forEach((id) => {
      const card = map.get(id);
      if (card) flowZone.append(card);
    });
    cards().forEach((card) => {
      if (card.parentElement !== flowZone) flowZone.append(card);
      card.draggable = false;
    });
    workspace.dispatchEvent(new CustomEvent('workspacechange'));
  }

  cards().forEach((card) => {
    card.dataset.size = card.dataset.defaultSize || 'normal';
    addTools(card);
  });
  desktopState = normalizeDesktopState(loadState());

  function setArrange(value) {
    arranging = Boolean(value && wide.matches);
    workspace.classList.toggle('arranging', arranging);
    arrangeButton.classList.toggle('active', arranging);
    arrangeButton.textContent = arranging ? t('header.done') : t('header.arrange');
    arrangeButton.disabled = !wide.matches;
    cards().forEach((card) => { card.draggable = arranging; });
  }

  function applyMode() {
    setArrange(false);
    if (wide.matches) restoreDesktop();
    else placeFlow();
    arrangeButton.disabled = !wide.matches;
    resetButton?.toggleAttribute('disabled', !wide.matches);
    requestAnimationFrame(() => workspace.dispatchEvent(new CustomEvent('workspacechange')));
  }

  function move(card, delta) {
    if (!wide.matches) return;
    const zone = card.closest('[data-workspace-zone]');
    if (zone !== mainZone && zone !== railZone) return;
    const list = zoneCards(zone);
    const current = list.indexOf(card);
    const next = current + delta;
    if (current < 0 || next < 0 || next >= list.length) return;
    if (delta < 0) zone.insertBefore(card, list[next]);
    else zone.insertBefore(list[next], card);
    persistDesktop();
  }

  function moveZone(card) {
    if (!wide.matches) return;
    const current = card.closest('[data-workspace-zone]');
    const target = current === railZone ? mainZone : railZone;
    target?.append(card);
    persistDesktop();
  }

  function cycleSize(card) {
    if (!wide.matches) return;
    const values = ['compact', 'normal', 'wide'];
    const index = Math.max(0, values.indexOf(card.dataset.size || 'normal'));
    card.dataset.size = values[(index + 1) % values.length];
    updateTools();
    persistDesktop();
  }

  function clearDropTargets() {
    cards().forEach((card) => card.classList.remove('drop-target'));
    desktopZones().forEach((zone) => zone.classList.remove('zone-drop-target'));
  }

  arrangeButton.addEventListener('click', () => setArrange(!arranging));

  resetButton?.addEventListener('click', () => {
    localStorage.removeItem(KEY);
    LEGACY_KEYS.forEach((key) => localStorage.removeItem(key));
    desktopState = defaultDesktopState();
    if (wide.matches) {
      restoreDesktop();
      persistDesktop();
    } else {
      placeFlow();
    }
  });

  workspace.addEventListener('click', (event) => {
    if (!arranging || !wide.matches) return;
    const card = event.target.closest('[data-card-id]');
    if (!card) return;
    const moveButton = event.target.closest('[data-move]');
    if (moveButton) move(card, Number(moveButton.dataset.move));
    if (event.target.closest('[data-move-zone]')) moveZone(card);
    if (event.target.closest('[data-size-cycle]')) cycleSize(card);
  });

  workspace.addEventListener('dragstart', (event) => {
    if (!arranging || !wide.matches) return event.preventDefault();
    draggedCard = event.target.closest('[data-card-id]');
    draggedCard?.classList.add('dragging');
  });

  workspace.addEventListener('dragover', (event) => {
    if (!draggedCard || !arranging || !wide.matches) return;
    const zone = event.target.closest('[data-workspace-zone]');
    if (zone !== mainZone && zone !== railZone) return;
    event.preventDefault();
    clearDropTargets();

    const target = event.target.closest('[data-card-id]');
    if (!target || target === draggedCard) {
      zone.classList.add('zone-drop-target');
      if (!target) zone.append(draggedCard);
      return;
    }

    target.classList.add('drop-target');
    const rect = target.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    zone.insertBefore(draggedCard, before ? target : target.nextSibling);
  });

  workspace.addEventListener('dragend', () => {
    clearDropTargets();
    if (!draggedCard) return;
    draggedCard.classList.remove('dragging');
    draggedCard = null;
    persistDesktop();
  });

  wide.addEventListener?.('change', applyMode);
  window.addEventListener('remote-gate-language', () => {
    setArrange(arranging);
    updateTools();
  });

  applyMode();
})();
