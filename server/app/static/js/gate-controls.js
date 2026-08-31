(() => {
  let context = null;

  const $ = (id) => document.getElementById(id);
  const endpointSelect = () => $('endpoint-select') || $('wan-select');

  function data() {
    return context?.getData?.() || {};
  }

  function endpointsFor(family) {
    const selectedWg = $('wg-select')?.value || '';
    const list = Array.isArray(data()?.endpoints) ? data().endpoints : [];
    return list.filter((item) =>
      item &&
      item.family === family &&
      ['direct', 'mapped', 'private', 'egress_probe'].includes(item.reachability) &&
      (!selectedWg || item.wireguard === selectedWg)
    );
  }

  function sourceFor(family) {
    return data()?.client_sources?.[family]?.address || '';
  }

  function familySelectable(family) {
    if (!['ipv4', 'ipv6'].includes(family)) return false;
    if (family === 'ipv6' && !data()?.inventory?.capabilities?.gate_ipv6) return false;
    return endpointsFor(family).length > 0;
  }

  function familyAvailable(family) {
    return familySelectable(family) && Boolean(sourceFor(family));
  }

  function chooseFamily() {
    const state = context.state;
    if (state.familyManual && familyAvailable(state.family)) return state.family;
    if (familySelectable('ipv4')) return 'ipv4';
    if (familySelectable('ipv6')) return 'ipv6';
    return 'ipv4';
  }

  function familyReason(family) {
    const t = context.t;
    const source = sourceFor(family);
    if (!source) return t('gate.familySourceMissing', {family: family.toUpperCase()});
    if (family === 'ipv6' && !data()?.inventory?.capabilities?.gate_ipv6) {
      return t('gate.ipv6Unavailable');
    }
    const endpoints = endpointsFor(family);
    if (!endpoints.length) return t('gate.familyEndpointMissing', {family: family.toUpperCase()});
    const request = context.state.requestFamily === 'ipv6' ? 'IPv6' : context.state.requestFamily === 'ipv4' ? 'IPv4' : '—';
    return t('gate.familyReady', {
      family: family.toUpperCase(),
      source,
      count: endpoints.length,
      request
    });
  }

  function canActivate() {
    if (!context) return false;
    const state = context.state;
    const pending = data()?.gate?.queue?.pending;
    return Boolean(
      !state.busy &&
      !pending &&
      familyAvailable(state.family) &&
      endpointSelect()?.value &&
      $('wg-select')?.value
    );
  }

  function syncFamily() {
    if (!context) return;
    const state = context.state;
    const familyRoot = $('family-segment');
    if (!familyRoot) return;

    const previous = state.family;
    state.family = chooseFamily();

    familyRoot.querySelectorAll('[data-family]').forEach((button) => {
      const family = button.dataset.family;
      if (family === 'dual') {
        button.disabled = true;
        button.hidden = true;
        button.classList.remove('active');
        return;
      }
      button.hidden = false;
      button.disabled = !familySelectable(family);
      button.classList.toggle('active', family === state.family);
      button.setAttribute('aria-pressed', family === state.family ? 'true' : 'false');
      button.title = familyReason(family);
    });

    const note = $('family-note');
    if (note) note.textContent = familyReason(state.family);
    if (previous !== state.family) context.onFamilyChange?.(state.family);
  }

  function syncScope() {
    if (!context) return;
    const root = $('scope-segment');
    if (!root) return;
    if (!['wg', 'wg_ping'].includes(context.state.scope)) context.state.scope = 'wg';
    root.querySelectorAll('[data-scope]').forEach((button) => {
      const active = button.dataset.scope === context.state.scope;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function render(currentData = data()) {
    if (!context) return;
    const state = context.state;
    const t = context.t;
    const remaining = context.remaining;

    syncFamily();
    syncScope();

    const pending = currentData?.gate?.queue?.pending;
    const last = currentData?.gate?.queue?.last;
    const fw = currentData?.agent?.firewall || {};
    const active = Boolean(fw.active);
    const pendingAction = pending?.action;
    const orb = $('gate-orb');

    let mode = 'closed';
    let title = t('gate.closed');
    let subtitle = t('gate.closedSub');
    let badge = t('gate.closedBadge');

    if (pendingAction === 'activate') {
      mode = 'authorizing';
      title = t('gate.authorizing');
      subtitle = t('gate.waitingAgent');
      badge = t('gate.pendingBadge');
    } else if (pendingAction === 'close') {
      mode = 'authorizing';
      title = t('gate.closing');
      subtitle = t('gate.waitingAgent');
      badge = t('gate.pendingBadge');
    } else if (active) {
      mode = 'open';
      title = t('gate.open');
      subtitle = t('gate.expiresIn', {value: remaining(fw.expires_in)});
      badge = t('gate.authorizedBadge');
    } else if (last?.state === 'failed') {
      mode = 'error';
      title = t('gate.error');
      subtitle = last.detail || t('gate.agentFailed');
      badge = t('gate.errorBadge');
    }

    const activatable = canActivate();

    if (orb) {
      orb.dataset.state = mode;
      orb.dataset.hint = t('gate.activate');
      orb.disabled = mode !== 'closed' || !activatable;
      orb.setAttribute('aria-disabled', orb.disabled ? 'true' : 'false');
      orb.setAttribute('aria-label', activatable ? t('gate.activate') : familyReason(state.family));
      orb.title = activatable ? t('gate.activate') : familyReason(state.family);
    }

    if ($('gate-state')) $('gate-state').textContent = title;
    if ($('gate-substate')) $('gate-substate').textContent = subtitle;
    if ($('gate-state-badge')) $('gate-state-badge').textContent = badge;
    if ($('gate-lock')) $('gate-lock').textContent = active ? '◇' : '◆';

    $('activate-button')?.classList.toggle('hidden', active);
    $('close-button')?.classList.toggle('hidden', !active);
    if ($('activate-button')) $('activate-button').disabled = !activatable;
    if ($('close-button')) $('close-button').disabled = state.busy || Boolean(pending);
  }

  function activate() {
    if (!context || !canActivate()) return;
    const state = context.state;
    context.post('/api/v1/gate/activate', {
      endpoint_id: endpointSelect().value,
      family: state.family,
      scope: state.scope || 'wg',
      ttl: state.ttl
    });
  }

  function bind(nextContext) {
    context = nextContext;
    const state = context.state;
    if (!state.scope) state.scope = 'wg';
    if (typeof state.familyManual !== 'boolean') state.familyManual = false;

    $('ttl-segment')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-ttl]');
      if (!button) return;
      state.ttl = Number(button.dataset.ttl);
      $('ttl-segment').querySelectorAll('button').forEach((item) => {
        item.classList.toggle('active', item === button);
        item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
      });
    });

    $('family-segment')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-family]');
      if (!button || button.disabled || !['ipv4', 'ipv6'].includes(button.dataset.family)) return;
      state.familyManual = true;
      state.family = button.dataset.family;
      context.onFamilyChange?.(state.family);
      render();
    });

    $('scope-segment')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-scope]');
      if (!button || !['wg', 'wg_ping'].includes(button.dataset.scope)) return;
      state.scope = button.dataset.scope;
      syncScope();
    });

    endpointSelect()?.addEventListener('change', () => render());
    $('wg-select')?.addEventListener('change', () => {
      context.onWireGuardChange?.();
      syncFamily();
      render();
    });

    $('activate-button')?.addEventListener('click', activate);
    $('gate-orb')?.addEventListener('click', activate);
    $('close-button')?.addEventListener('click', () => context.post('/api/v1/gate/close'));

    window.addEventListener('remote-gate-language', () => render());
  }

  window.RemoteGateGateControls = {bind, render, canActivate, activate, familyAvailable, familySelectable};
})();
