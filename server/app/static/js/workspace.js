(() => {
  const KEY = 'remote-gate:workspace:v2';
  const LEGACY_KEY = 'remote-gate:workspace:v1';
  const workspace = document.getElementById('workspace');
  const arrangeButton = document.getElementById('arrange-button');
  const resetButton = document.getElementById('reset-layout-button');
  if (!workspace || !arrangeButton) return;

  const desktop = window.matchMedia('(min-width: 768px)');
  const t = (key) => window.RemoteGateI18n?.t(key) || key;
  let arranging = false;
  let draggedCard = null;

  const cards = () => Array.from(workspace.children).filter((node) => node.dataset?.cardId);

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

    const legacy = parseState(localStorage.getItem(LEGACY_KEY));
    if (!Object.keys(legacy).length) return {};

    if (legacy.sizes?.system === 'compact') legacy.sizes.system = 'normal';
    localStorage.setItem(KEY, JSON.stringify(legacy));
    return legacy;
  }

  function saveState() {
    const value = {
      order: cards().map((card) => card.dataset.cardId),
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

    const earlier = document.createElement('button');
    earlier.type = 'button';
    earlier.className = 'card-tool';
    earlier.dataset.move = '-1';
    earlier.textContent = '←';
    earlier.title = t('workspace.moveEarlier');
    tools.append(earlier);

    const later = document.createElement('button');
    later.type = 'button';
    later.className = 'card-tool';
    later.dataset.move = '1';
    later.textContent = '→';
    later.title = t('workspace.moveLater');
    tools.append(later);

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

  cards().forEach((card) => {
    card.dataset.size = card.dataset.defaultSize || 'normal';
    addTools(card);
  });

  const saved = loadState();
  if (Array.isArray(saved.order)) {
    const map = new Map(cards().map((card) => [card.dataset.cardId, card]));
    saved.order.forEach((id) => {
      if (map.has(id)) workspace.append(map.get(id));
    });
  }

  cards().forEach((card) => {
    const value = saved.sizes?.[card.dataset.cardId];
    if (['compact', 'normal', 'wide'].includes(value)) card.dataset.size = value;
  });
  updateTools();

  function setArrange(value) {
    arranging = Boolean(value && desktop.matches);
    workspace.classList.toggle('arranging', arranging);
    arrangeButton.classList.toggle('active', arranging);
    arrangeButton.textContent = arranging ? t('header.done') : t('header.arrange');
    cards().forEach((card) => {
      card.draggable = arranging;
    });
  }

  function move(card, delta) {
    const list = cards();
    const current = list.indexOf(card);
    const next = current + delta;
    if (current < 0 || next < 0 || next >= list.length) return;

    if (delta < 0) workspace.insertBefore(card, list[next]);
    else workspace.insertBefore(list[next], card);

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
  }

  arrangeButton.addEventListener('click', () => setArrange(!arranging));

  resetButton?.addEventListener('click', () => {
    localStorage.removeItem(KEY);
    localStorage.removeItem(LEGACY_KEY);
    const order = ['gate', 'client', 'wireguard', 'wan', 'activity', 'system'];
    const map = new Map(cards().map((card) => [card.dataset.cardId, card]));
    order.forEach((id) => {
      if (map.has(id)) workspace.append(map.get(id));
    });
    cards().forEach((card) => {
      card.dataset.size = card.dataset.defaultSize || 'normal';
    });
    updateTools();
    workspace.dispatchEvent(new CustomEvent('workspacechange'));
  });

  workspace.addEventListener('click', (event) => {
    if (!arranging) return;
    const card = event.target.closest('[data-card-id]');
    if (!card) return;

    const moveButton = event.target.closest('[data-move]');
    if (moveButton) move(card, Number(moveButton.dataset.move));
    if (event.target.closest('[data-size-cycle]')) cycleSize(card);
  });

  workspace.addEventListener('dragstart', (event) => {
    if (!arranging) return event.preventDefault();
    draggedCard = event.target.closest('[data-card-id]');
    draggedCard?.classList.add('dragging');
  });

  workspace.addEventListener('dragover', (event) => {
    if (!draggedCard || !arranging) return;
    event.preventDefault();

    const target = event.target.closest('[data-card-id]');
    if (!target || target === draggedCard) return;

    clearDropTargets();
    target.classList.add('drop-target');

    const rect = target.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    workspace.insertBefore(draggedCard, before ? target : target.nextSibling);
  });

  workspace.addEventListener('dragend', () => {
    clearDropTargets();
    if (!draggedCard) return;
    draggedCard.classList.remove('dragging');
    draggedCard = null;
    saveState();
  });

  desktop.addEventListener?.('change', (event) => {
    if (!event.matches) setArrange(false);
  });

  window.addEventListener('remote-gate-language', () => {
    setArrange(arranging);
    updateTools();
  });
})();
