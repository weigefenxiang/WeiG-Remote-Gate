(() => {
  const KEY = 'remote-gate:workspace:v3';
  const LEGACY_KEYS = ['remote-gate:workspace:v2', 'remote-gate:workspace:v1'];
  const workspace = document.getElementById('workspace');
  const arrangeButton = document.getElementById('arrange-button');
  const resetButton = document.getElementById('reset-layout-button');
  if (!workspace || !arrangeButton) return;

  const desktop = window.matchMedia('(min-width: 768px)');
  const t = (key) => window.RemoteGateI18n?.t(key) || key;
  const zones = () => Array.from(workspace.querySelectorAll('[data-workspace-zone]'));
  const zoneByName = (name) => workspace.querySelector(`[data-workspace-zone="${name}"]`);
  const cards = () => Array.from(workspace.querySelectorAll('[data-card-id]'));
  const DEFAULTS = {
    main: ['gate', 'wireguard', 'wan'],
    rail: ['client', 'system', 'activity']
  };
  const DEFAULT_ZONE = Object.fromEntries(Object.entries(DEFAULTS).flatMap(([zone, ids]) => ids.map((id) => [id, zone])));

  let arranging = false;
  let draggedCard = null;

  function parseState(raw) {
    try {
      const value = JSON.parse(raw || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (_) {
      return {};
    }
  }

  function legacySizes() {
    for (const key of LEGACY_KEYS) {
      const value = parseState(localStorage.getItem(key));
      if (value.sizes && typeof value.sizes === 'object') return value.sizes;
    }
    return {};
  }

  function loadState() {
    return parseState(localStorage.getItem(KEY));
  }

  function zoneCards(zone) {
    return Array.from(zone.children).filter((node) => node.dataset?.cardId);
  }

  function saveState() {
    const value = {
      zones: Object.fromEntries(cards().map((card) => [card.dataset.cardId, card.closest('[data-workspace-zone]')?.dataset.workspaceZone || DEFAULT_ZONE[card.dataset.cardId]])),
      order: Object.fromEntries(zones().map((zone) => [zone.dataset.workspaceZone, zoneCards(zone).map((card) => card.dataset.cardId)])),
      sizes: Object.fromEntries(cards().map((card) => [card.dataset.cardId, card.dataset.size || 'normal']))
    };
    localStorage.setItem(KEY, JSON.stringify(value));
    workspace.dispatchEvent(new CustomEvent('workspacechange'));
  }

  function addTools(card) {
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

  function placeDefaults() {
    const map = new Map(cards().map((card) => [card.dataset.cardId, card]));
    Object.entries(DEFAULTS).forEach(([zoneName, order]) => {
      const zone = zoneByName(zoneName);
      order.forEach((id) => { if (zone && map.has(id)) zone.append(map.get(id)); });
    });
  }

  cards().forEach((card) => {
    card.dataset.size = card.dataset.defaultSize || 'normal';
    addTools(card);
  });

  const saved = loadState();
  const fallbackSizes = Object.keys(saved).length ? {} : legacySizes();
  if (saved.zones && typeof saved.zones === 'object') {
    cards().forEach((card) => {
      const zoneName = saved.zones[card.dataset.cardId];
      const zone = zoneByName(zoneName);
      if (zone) zone.append(card);
    });
  } else {
    placeDefaults();
  }

  if (saved.order && typeof saved.order === 'object') {
    Object.entries(saved.order).forEach(([zoneName, order]) => {
      const zone = zoneByName(zoneName);
      if (!zone || !Array.isArray(order)) return;
      const map = new Map(zoneCards(zone).map((card) => [card.dataset.cardId, card]));
      order.forEach((id) => { if (map.has(id)) zone.append(map.get(id)); });
    });
  }

  cards().forEach((card) => {
    const value = saved.sizes?.[card.dataset.cardId] || fallbackSizes?.[card.dataset.cardId];
    if (['compact', 'normal', 'wide'].includes(value)) card.dataset.size = value;
    if (card.dataset.cardId === 'activity' && !saved.sizes) card.dataset.size = 'normal';
  });
  updateTools();

  function setArrange(value) {
    arranging = Boolean(value && desktop.matches);
    workspace.classList.toggle('arranging', arranging);
    arrangeButton.classList.toggle('active', arranging);
    arrangeButton.textContent = arranging ? t('header.done') : t('header.arrange');
    cards().forEach((card) => { card.draggable = arranging; });
  }

  function move(card, delta) {
    const zone = card.closest('[data-workspace-zone]');
    if (!zone) return;
    const list = zoneCards(zone);
    const current = list.indexOf(card);
    const next = current + delta;
    if (current < 0 || next < 0 || next >= list.length) return;
    if (delta < 0) zone.insertBefore(card, list[next]);
    else zone.insertBefore(list[next], card);
    saveState();
  }

  function moveZone(card) {
    const current = card.closest('[data-workspace-zone]')?.dataset.workspaceZone;
    const target = zoneByName(current === 'rail' ? 'main' : 'rail');
    if (!target) return;
    target.append(card);
    saveState();
  }

  function cycleSize(card) {
    const values = ['compact', 'normal', 'wide'];
    const index = Math.max(0, values.indexOf(card.dataset.size || 'normal'));
    card.dataset.size = values[(index + 1) % values.length];
    updateTools();
    saveState();
  }

  function clearDropTargets() {
    cards().forEach((card) => card.classList.remove('drop-target'));
    zones().forEach((zone) => zone.classList.remove('zone-drop-target'));
  }

  arrangeButton.addEventListener('click', () => setArrange(!arranging));

  resetButton?.addEventListener('click', () => {
    localStorage.removeItem(KEY);
    LEGACY_KEYS.forEach((key) => localStorage.removeItem(key));
    placeDefaults();
    cards().forEach((card) => { card.dataset.size = card.dataset.defaultSize || 'normal'; });
    const activity = workspace.querySelector('[data-card-id="activity"]');
    if (activity) activity.dataset.size = 'normal';
    updateTools();
    saveState();
  });

  workspace.addEventListener('click', (event) => {
    if (!arranging) return;
    const card = event.target.closest('[data-card-id]');
    if (!card) return;
    const moveButton = event.target.closest('[data-move]');
    if (moveButton) move(card, Number(moveButton.dataset.move));
    if (event.target.closest('[data-move-zone]')) moveZone(card);
    if (event.target.closest('[data-size-cycle]')) cycleSize(card);
  });

  workspace.addEventListener('dragstart', (event) => {
    if (!arranging) return event.preventDefault();
    draggedCard = event.target.closest('[data-card-id]');
    draggedCard?.classList.add('dragging');
  });

  workspace.addEventListener('dragover', (event) => {
    if (!draggedCard || !arranging) return;
    const zone = event.target.closest('[data-workspace-zone]');
    if (!zone) return;
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
    saveState();
  });

  desktop.addEventListener?.('change', (event) => { if (!event.matches) setArrange(false); });
  window.addEventListener('remote-gate-language', () => {
    setArrange(arranging);
    updateTools();
  });
})();
