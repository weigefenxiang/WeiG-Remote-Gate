(() => {
  let context = null;

  const $ = (id) => document.getElementById(id);

  function data() {
    return context?.getData?.() || {};
  }

  function canActivate() {
    if (!context) return false;
    const state = context.state;
    const pending = data()?.gate?.queue?.pending;
    return Boolean(
      !state.busy &&
      !pending &&
      state.requestFamily === 'ipv4' &&
      $('wan-select')?.value &&
      $('wg-select')?.value
    );
  }

  function syncFamily() {
    if (!context) return;
    const state = context.state;
    const t = context.t;
    const ipv4 = $('family-segment')?.querySelector('[data-family="ipv4"]');
    const ipv6 = $('family-segment')?.querySelector('[data-family="ipv6"]');
    const dual = $('family-segment')?.querySelector('[data-family="dual"]');

    if (!ipv4 || !ipv6 || !dual) return;

    ipv4.disabled = state.requestFamily !== 'ipv4';
    ipv6.disabled = true;
    dual.disabled = true;
    state.family = 'ipv4';

    $('family-segment').querySelectorAll('[data-family]').forEach((button) => {
      button.classList.toggle('active', button.dataset.family === state.family);
    });

    $('family-note').textContent = state.requestFamily === 'ipv4'
      ? t('gate.familyNoteIpv4')
      : t('gate.familyNoteIpv6');
  }

  function render(currentData = data()) {
    if (!context) return;
    const state = context.state;
    const t = context.t;
    const remaining = context.remaining;

    syncFamily();

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

    orb.dataset.state = mode;
    orb.dataset.hint = t('gate.activate');
    orb.disabled = mode !== 'closed' || !activatable;
    orb.setAttribute('aria-disabled', orb.disabled ? 'true' : 'false');
    orb.setAttribute('aria-label', activatable ? t('gate.activate') : subtitle);
    orb.title = activatable ? t('gate.activate') : subtitle;

    $('gate-state').textContent = title;
    $('gate-substate').textContent = subtitle;
    $('gate-state-badge').textContent = badge;
    $('gate-lock').textContent = active ? '◇' : '◆';

    $('activate-button').classList.toggle('hidden', active);
    $('close-button').classList.toggle('hidden', !active);
    $('activate-button').disabled = !activatable;
    $('close-button').disabled = state.busy || Boolean(pending);
  }

  function activate() {
    if (!context) return;
    const state = context.state;

    if (state.requestFamily !== 'ipv4') {
      context.toast(context.t('toast.ipv4Required'), 'error');
      return;
    }
    if (!canActivate()) return;

    context.post('/api/v1/gate/activate', {
      wan: $('wan-select').value,
      wireguard: $('wg-select').value,
      ttl: state.ttl,
      family: state.family
    });
  }

  function bind(nextContext) {
    context = nextContext;
    const state = context.state;

    $('ttl-segment')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-ttl]');
      if (!button) return;
      state.ttl = Number(button.dataset.ttl);
      $('ttl-segment').querySelectorAll('button').forEach((item) => {
        item.classList.toggle('active', item === button);
      });
    });

    $('family-segment')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-family]');
      if (!button || button.disabled) return;
      state.family = button.dataset.family;
      $('family-segment').querySelectorAll('[data-family]').forEach((item) => {
        item.classList.toggle('active', item === button);
      });
    });

    $('wan-select')?.addEventListener('change', () => render());
    $('wg-select')?.addEventListener('change', () => {
      context.onWireGuardChange?.();
      render();
    });

    $('activate-button')?.addEventListener('click', activate);
    $('gate-orb')?.addEventListener('click', activate);
    $('close-button')?.addEventListener('click', () => context.post('/api/v1/gate/close'));

    window.addEventListener('remote-gate-language', () => render());
  }

  window.RemoteGateGateControls = {bind, render, canActivate, activate};
})();
