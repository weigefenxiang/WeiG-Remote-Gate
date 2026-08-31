(() => {
  let context = null;
  const $ = (id) => document.getElementById(id);
  const endpointSelect = () => $('endpoint-select') || $('wan-select');
  const zh = () => document.documentElement.dataset.lang === 'zh';
  function data() { return context?.getData?.() || {}; }
  function endpointsFor(family) {
    const selectedWg = $('wg-select')?.value || '';
    const list = Array.isArray(data()?.endpoints) ? data().endpoints : [];
    return list.filter((item) => item && item.family === family && ['direct','mapped','private','egress_probe'].includes(item.reachability) && (!selectedWg || item.wireguard === selectedWg));
  }
  function sourceFor(family) { return data()?.client_sources?.[family]?.address || ''; }
  function singleSelectable(family) {
    if (!['ipv4','ipv6'].includes(family)) return false;
    if (family === 'ipv6' && !data()?.inventory?.capabilities?.gate_ipv6) return false;
    return endpointsFor(family).length > 0;
  }
  function familySelectable(family) { return family === 'dual' ? singleSelectable('ipv4') && singleSelectable('ipv6') : singleSelectable(family); }
  function singleAvailable(family) { return singleSelectable(family) && Boolean(sourceFor(family)); }
  function familyAvailable(family) { return family === 'dual' ? singleAvailable('ipv4') && singleAvailable('ipv6') : singleAvailable(family); }
  function chooseFamily() {
    const state = context.state;
    if (state.familyManual && familySelectable(state.family)) return state.family;
    if (singleAvailable('ipv4')) return 'ipv4';
    if (singleSelectable('ipv4')) return 'ipv4';
    if (singleAvailable('ipv6')) return 'ipv6';
    if (singleSelectable('ipv6')) return 'ipv6';
    return 'ipv4';
  }
  function familyReason(family) {
    const t = context.t;
    if (family === 'dual') {
      if (!sourceFor('ipv4') || !sourceFor('ipv6')) return zh() ? 'IPv4 与 IPv6 Source 都就绪后可同时授权。' : 'Both IPv4 and IPv6 sources are required for dual-stack authorization.';
      if (!singleSelectable('ipv4') || !singleSelectable('ipv6')) return zh() ? '当前 WireGuard 需要同时存在可用的 IPv4 与 IPv6 Endpoint。' : 'The selected WireGuard needs both IPv4 and IPv6 endpoints.';
      return zh() ? `双栈就绪 · IPv4 ${sourceFor('ipv4')} · IPv6 ${sourceFor('ipv6')} · 自动选择各自最佳 Endpoint` : `Dual stack ready · IPv4 ${sourceFor('ipv4')} · IPv6 ${sourceFor('ipv6')} · best endpoint per family`;
    }
    const source = sourceFor(family);
    if (!source) return t('gate.familySourceMissing', {family: family.toUpperCase()});
    if (family === 'ipv6' && !data()?.inventory?.capabilities?.gate_ipv6) return t('gate.ipv6Unavailable');
    const endpoints = endpointsFor(family);
    if (!endpoints.length) return t('gate.familyEndpointMissing', {family: family.toUpperCase()});
    const request = context.state.requestFamily === 'ipv6' ? 'IPv6' : context.state.requestFamily === 'ipv4' ? 'IPv4' : '—';
    return t('gate.familyReady', {family: family.toUpperCase(), source, count: endpoints.length, request});
  }
  function canActivate() {
    if (!context) return false;
    const state = context.state;
    const pending = data()?.gate?.queue?.pending;
    const endpointReady = state.family === 'dual' || Boolean(endpointSelect()?.value);
    return Boolean(!state.busy && !pending && familyAvailable(state.family) && endpointReady && $('wg-select')?.value);
  }
  function ensureDualButton() {
    const root = $('family-segment');
    if (!root || root.querySelector('[data-family="dual"]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.family = 'dual';
    button.setAttribute('aria-pressed', 'false');
    button.textContent = 'IPv4 + IPv6';
    root.append(button);
  }
  function syncFamily() {
    if (!context) return;
    ensureDualButton();
    const state = context.state;
    const familyRoot = $('family-segment');
    if (!familyRoot) return;
    const previous = state.family;
    state.family = chooseFamily();
    familyRoot.querySelectorAll('[data-family]').forEach((button) => {
      const family = button.dataset.family;
      if (!['ipv4','ipv6','dual'].includes(family)) return;
      button.hidden = false;
      button.disabled = !familySelectable(family);
      button.classList.toggle('active', family === state.family);
      button.setAttribute('aria-pressed', family === state.family ? 'true' : 'false');
      button.title = familyReason(family);
    });
    const note = $('family-note'); if (note) note.textContent = familyReason(state.family);
    if (previous !== state.family) context.onFamilyChange?.(state.family);
  }
  function syncScope() {
    if (!context) return;
    const root = $('scope-segment'); if (!root) return;
    if (!['wg','wg_ping'].includes(context.state.scope)) context.state.scope = 'wg';
    root.querySelectorAll('[data-scope]').forEach((button) => {
      const active = button.dataset.scope === context.state.scope;
      button.classList.toggle('active', active); button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }
  function activeFamilyState(fw, family) {
    const families = fw?.families || {};
    if (family === 'dual') return Boolean(families?.ipv4?.active || families?.ipv6?.active || fw?.active);
    return Boolean(families?.[family]?.active || (fw?.active && fw?.family === family));
  }
  function render(currentData = data()) {
    if (!context) return;
    const state = context.state, t = context.t, remaining = context.remaining;
    syncFamily(); syncScope();
    const pending = currentData?.gate?.queue?.pending, next = currentData?.gate?.queue?.next, last = currentData?.gate?.queue?.last;
    const fw = currentData?.agent?.firewall || {}, active = activeFamilyState(fw, state.family) || Boolean(fw.active), pendingAction = pending?.action, orb = $('gate-orb');
    let mode='closed', title=t('gate.closed'), subtitle=t('gate.closedSub'), badge=t('gate.closedBadge');
    if (pendingAction === 'activate') {
      mode='authorizing'; title=t('gate.authorizing');
      const queued = Array.isArray(next) ? next.length : 0;
      subtitle = queued > 0 ? (zh() ? `正在验证 ${String(pending.family||'').toUpperCase()}，随后继续下一协议族…` : `Verifying ${String(pending.family||'').toUpperCase()}, then continuing with the next family…`) : t('gate.waitingAgent');
      badge=t('gate.pendingBadge');
    } else if (pendingAction === 'close') { mode='authorizing'; title=t('gate.closing'); subtitle=t('gate.waitingAgent'); badge=t('gate.pendingBadge'); }
    else if (active) {
      mode='open'; title=t('gate.open');
      const fam=fw?.families||{}, values=[fam?.ipv4?.expires_in,fam?.ipv6?.expires_in].map(Number).filter((x)=>x>0), ttl=values.length?Math.min(...values):Number(fw.expires_in||0);
      subtitle=t('gate.expiresIn',{value:remaining(ttl)}); badge=t('gate.authorizedBadge');
    } else if (last?.state === 'failed') { mode='error'; title=t('gate.error'); subtitle=last.detail||t('gate.agentFailed'); badge=t('gate.errorBadge'); }
    const activatable=canActivate();
    if (orb) { orb.dataset.state=mode; orb.dataset.hint=t('gate.activate'); orb.disabled=mode!=='closed'||!activatable; orb.setAttribute('aria-disabled',orb.disabled?'true':'false'); orb.setAttribute('aria-label',activatable?t('gate.activate'):familyReason(state.family)); orb.title=activatable?t('gate.activate'):familyReason(state.family); }
    if ($('gate-state')) $('gate-state').textContent=title; if ($('gate-substate')) $('gate-substate').textContent=subtitle; if ($('gate-state-badge')) $('gate-state-badge').textContent=badge; if ($('gate-lock')) $('gate-lock').textContent=active?'◇':'◆';
    $('activate-button')?.classList.toggle('hidden',active); $('close-button')?.classList.toggle('hidden',!active); if ($('activate-button')) $('activate-button').disabled=!activatable; if ($('close-button')) $('close-button').disabled=state.busy||Boolean(pending);
  }
  function activate() {
    if (!context || !canActivate()) return;
    const state=context.state;
    if (state.family === 'dual') {
      const v4=endpointsFor('ipv4')[0], v6=endpointsFor('ipv6')[0]; if (!v4 || !v6) return;
      context.post('/api/v1/gate/activate',{families:['ipv4','ipv6'],endpoint_ids:{ipv4:v4.id,ipv6:v6.id},scope:state.scope||'wg',ttl:state.ttl}); return;
    }
    context.post('/api/v1/gate/activate',{endpoint_id:endpointSelect().value,family:state.family,scope:state.scope||'wg',ttl:state.ttl});
  }
  function bind(nextContext) {
    context=nextContext; const state=context.state; if (!state.scope) state.scope='wg'; if (typeof state.familyManual!=='boolean') state.familyManual=false; ensureDualButton();
    $('ttl-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-ttl]'); if(!button)return; state.ttl=Number(button.dataset.ttl); $('ttl-segment').querySelectorAll('button').forEach((item)=>{item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',item===button?'true':'false');});});
    $('family-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-family]'); if(!button||button.disabled||!['ipv4','ipv6','dual'].includes(button.dataset.family))return; state.familyManual=true;state.family=button.dataset.family;context.onFamilyChange?.(state.family);render();});
    $('scope-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-scope]');if(!button||!['wg','wg_ping'].includes(button.dataset.scope))return;state.scope=button.dataset.scope;syncScope();});
    endpointSelect()?.addEventListener('change',()=>render()); $('wg-select')?.addEventListener('change',()=>{context.onWireGuardChange?.();syncFamily();render();}); $('activate-button')?.addEventListener('click',activate); $('gate-orb')?.addEventListener('click',activate); $('close-button')?.addEventListener('click',()=>context.post('/api/v1/gate/close')); window.addEventListener('remote-gate-language',()=>render());
  }
  window.RemoteGateGateControls={bind,render,canActivate,activate,familyAvailable,familySelectable};
})();
