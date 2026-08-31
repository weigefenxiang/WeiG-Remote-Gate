(() => {
  let context = null;
  let transaction = null;
  let transactionPoll = 0;
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

  function notify(message, kind = 'info', options = {}) {
    if (window.RemoteGateFeedback?.notify) return window.RemoteGateFeedback.notify(message, kind, options);
    context?.toast?.(message, kind === 'error' ? 'error' : 'info');
    return null;
  }
  function pendingCommand(currentData = data()) { return currentData?.gate?.queue?.pending || null; }
  function lockAction(currentData = data()) { return transaction?.action || pendingCommand(currentData)?.action || ''; }
  function lockMessage(currentData = data()) {
    const action = lockAction(currentData);
    if (action === 'close') return zh() ? '正在关闭访问，请等待当前操作完成。' : 'Closing access. Please wait for the current operation to finish.';
    return zh() ? '正在验证 WireGuard，请等待当前授权完成。' : 'Verifying WireGuard. Please wait for the current authorization to finish.';
  }
  function startTransactionPoll() {
    if (transactionPoll) return;
    transactionPoll = window.setInterval(() => window.RemoteGateApp?.refresh?.(), 1000);
  }
  function stopTransactionPoll() {
    if (!transactionPoll) return;
    window.clearInterval(transactionPoll);
    transactionPoll = 0;
  }
  function clearTransaction() {
    transaction = null;
    stopTransactionPoll();
  }
  function transactionMatches(last) {
    if (!transaction || !last) return false;
    if (transaction.batchId && last.batch_id === transaction.batchId) return true;
    if (transaction.commandId && last.id === transaction.commandId) return true;
    return !transaction.commandId && !transaction.batchId && last.action === transaction.action;
  }
  function syncTransaction(currentData) {
    const queue = currentData?.gate?.queue || {};
    const pending = queue.pending;
    const last = queue.last;
    if (pending && !transaction) {
      transaction = {
        action: String(pending.action || 'activate'),
        commandId: String(pending.id || ''),
        batchId: String(pending.batch_id || ''),
        startedAt: Date.now(),
        serverOwned: true
      };
      startTransactionPoll();
    }
    if (!transaction) return false;
    startTransactionPoll();
    if (pending) return true;

    if (transactionMatches(last) && ['done', 'failed'].includes(String(last.state || ''))) {
      if (last.state === 'failed') {
        notify(String(last.detail || (zh() ? '授权失败' : 'Authorization failed')), 'error', {title: zh() ? '操作失败' : 'Action failed', duration: 5200});
      } else {
        const closing = transaction.action === 'close';
        notify(closing ? (zh() ? '远程访问已关闭。' : 'Remote access is closed.') : (zh() ? 'WireGuard 授权已生效。' : 'WireGuard authorization is active.'), 'success', {title: closing ? (zh() ? '已关闭' : 'Closed') : (zh() ? '授权成功' : 'Authorized')});
      }
      clearTransaction();
      return false;
    }
    if (Date.now() - transaction.startedAt > 65000) {
      notify(zh() ? '操作状态确认超时，界面已恢复；后台状态仍会继续刷新。' : 'Operation status confirmation timed out. Controls are available again while background status refresh continues.', 'warning', {duration: 5200});
      clearTransaction();
      return false;
    }
    return true;
  }
  function transactionLocked(currentData = data()) { return Boolean(transaction || pendingCommand(currentData)); }

  function canActivate() {
    if (!context || transactionLocked()) return false;
    const state = context.state;
    const endpointReady = state.family === 'dual' || Boolean(endpointSelect()?.value);
    return Boolean(!state.busy && familyAvailable(state.family) && endpointReady && $('wg-select')?.value);
  }
  function ensureDualButton() {
    const root = $('family-segment');
    if (!root || root.querySelector('[data-family="dual"]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.family = 'dual';
    button.setAttribute('aria-pressed', 'false');
    button.textContent = 'Dual';
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
    const compactLabel = {ipv4: 'V4', ipv6: 'V6', dual: 'Dual'};
    familyRoot.querySelectorAll('[data-family]').forEach((button) => {
      const family = button.dataset.family;
      if (!['ipv4','ipv6','dual'].includes(family)) return;
      button.hidden = false;
      button.textContent = compactLabel[family];
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
    const locked = syncTransaction(currentData);
    const pending = currentData?.gate?.queue?.pending, next = currentData?.gate?.queue?.next, last = currentData?.gate?.queue?.last;
    const fw = currentData?.agent?.firewall || {}, active = activeFamilyState(fw, state.family) || Boolean(fw.active), pendingAction = pending?.action, orb = $('gate-orb');
    let mode='closed', title=t('gate.closed'), subtitle=t('gate.closedSub'), badge=t('gate.closedBadge');
    if (pendingAction === 'activate' || (locked && lockAction(currentData) === 'activate')) {
      mode='authorizing'; title=t('gate.authorizing');
      const queued = Array.isArray(next) ? next.length : 0;
      subtitle = queued > 0 ? (zh() ? `正在验证 ${String(pending?.family||'').toUpperCase()}，随后继续下一协议族…` : `Verifying ${String(pending?.family||'').toUpperCase()}, then continuing with the next family…`) : t('gate.waitingAgent');
      badge=t('gate.pendingBadge');
    } else if (pendingAction === 'close' || (locked && lockAction(currentData) === 'close')) { mode='authorizing'; title=t('gate.closing'); subtitle=t('gate.waitingAgent'); badge=t('gate.pendingBadge'); }
    else if (active) {
      mode='open'; title=t('gate.open');
      const fam=fw?.families||{}, values=[fam?.ipv4?.expires_in,fam?.ipv6?.expires_in].map(Number).filter((x)=>x>0), ttl=values.length?Math.min(...values):Number(fw.expires_in||0);
      subtitle=t('gate.expiresIn',{value:remaining(ttl)}); badge=t('gate.authorizedBadge');
    } else if (last?.state === 'failed') { mode='error'; title=t('gate.error'); subtitle=last.detail||t('gate.agentFailed'); badge=t('gate.errorBadge'); }
    const activatable=canActivate();
    if (orb) {
      orb.dataset.state=mode; orb.dataset.hint=t('gate.activate');
      orb.disabled = locked ? false : (mode!=='closed'||!activatable);
      orb.classList.toggle('transaction-locked', locked);
      orb.setAttribute('aria-disabled', locked || orb.disabled ? 'true':'false');
      orb.setAttribute('aria-label', locked ? lockMessage(currentData) : (activatable?t('gate.activate'):familyReason(state.family)));
      orb.title=locked ? lockMessage(currentData) : (activatable?t('gate.activate'):familyReason(state.family));
    }
    if ($('gate-state')) $('gate-state').textContent=title; if ($('gate-substate')) $('gate-substate').textContent=subtitle; if ($('gate-state-badge')) $('gate-state-badge').textContent=badge; if ($('gate-lock')) $('gate-lock').textContent=active?'◇':'◆';
    const form=document.querySelector('.gate-form'); form?.classList.toggle('transaction-locked',locked);
    $('activate-button')?.classList.toggle('hidden',active && !locked);
    $('close-button')?.classList.toggle('hidden',!active || locked && lockAction(currentData)!=='close');
    if ($('activate-button')) { $('activate-button').disabled=locked?false:!activatable; $('activate-button').classList.toggle('transaction-locked',locked); $('activate-button').setAttribute('aria-disabled',locked||!activatable?'true':'false'); }
    if ($('close-button')) { $('close-button').disabled=locked?false:state.busy; $('close-button').classList.toggle('transaction-locked',locked); $('close-button').setAttribute('aria-disabled',locked||state.busy?'true':'false'); }
  }

  async function submit(path, body, action) {
    if (!context) return;
    if (transactionLocked()) { notify(lockMessage(), 'info', {title: zh() ? '操作进行中' : 'Operation in progress'}); return; }
    transaction = {action, commandId: '', batchId: '', startedAt: Date.now(), serverOwned: false};
    startTransactionPoll();
    context.state.busy = true;
    render(data());
    try {
      const response = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': context.state.csrf},
        body: JSON.stringify(body || {})
      });
      const payload = response.status === 204 ? {} : await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(payload?.error || `HTTP ${response.status}`));
      transaction.commandId = String(payload?.command_id || '');
      transaction.batchId = String(payload?.batch_id || '');
      notify(action === 'close' ? (zh() ? '关闭请求已提交，正在等待 OpenWrt 确认。' : 'Close request submitted; waiting for OpenWrt confirmation.') : (zh() ? '授权请求已提交，正在验证 WireGuard。' : 'Authorization submitted; verifying WireGuard.'), 'info', {title: zh() ? '处理中' : 'In progress'});
      window.RemoteGateApp?.refresh?.();
    } catch (error) {
      notify(String(error?.message || error || 'request failed'), 'error', {title: zh() ? '请求失败' : 'Request failed', duration: 5200});
      clearTransaction();
    } finally {
      context.state.busy = false;
      render(data());
    }
  }
  function activate() {
    if (!context) return;
    if (transactionLocked()) { notify(lockMessage(), 'info', {title: zh() ? '操作进行中' : 'Operation in progress'}); return; }
    if (!canActivate()) return;
    const state=context.state;
    if (state.family === 'dual') {
      const v4=endpointsFor('ipv4')[0], v6=endpointsFor('ipv6')[0]; if (!v4 || !v6) return;
      submit('/api/v1/gate/activate',{families:['ipv4','ipv6'],endpoint_ids:{ipv4:v4.id,ipv6:v6.id},scope:state.scope||'wg',ttl:state.ttl},'activate'); return;
    }
    submit('/api/v1/gate/activate',{endpoint_id:endpointSelect().value,family:state.family,scope:state.scope||'wg',ttl:state.ttl},'activate');
  }
  function closeAccess() { submit('/api/v1/gate/close',{},'close'); }

  function guardedTarget(target) {
    return target?.closest?.('.gate-form button, .gate-form select, .gate-form input, #gate-orb');
  }
  function transactionGuard(event) {
    if (!transactionLocked() || !guardedTarget(event.target)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    notify(lockMessage(), 'info', {title: zh() ? '操作进行中' : 'Operation in progress'});
  }

  function bind(nextContext) {
    context=nextContext; const state=context.state; if (!state.scope) state.scope='wg'; if (typeof state.familyManual!=='boolean') state.familyManual=false; ensureDualButton();
    const gateCard=document.querySelector('.gate-card');
    gateCard?.addEventListener('pointerdown',transactionGuard,true);
    gateCard?.addEventListener('click',transactionGuard,true);
    gateCard?.addEventListener('change',transactionGuard,true);
    $('ttl-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-ttl]'); if(!button||transactionLocked())return; state.ttl=Number(button.dataset.ttl); $('ttl-segment').querySelectorAll('button').forEach((item)=>{item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',item===button?'true':'false');});});
    $('family-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-family]'); if(!button||transactionLocked()||button.disabled||!['ipv4','ipv6','dual'].includes(button.dataset.family))return; state.familyManual=true;state.family=button.dataset.family;context.onFamilyChange?.(state.family);render();});
    $('scope-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-scope]');if(!button||transactionLocked()||!['wg','wg_ping'].includes(button.dataset.scope))return;state.scope=button.dataset.scope;syncScope();});
    endpointSelect()?.addEventListener('change',()=>{if(!transactionLocked())render();}); $('wg-select')?.addEventListener('change',()=>{if(transactionLocked())return;context.onWireGuardChange?.();syncFamily();render();}); $('activate-button')?.addEventListener('click',activate); $('gate-orb')?.addEventListener('click',activate); $('close-button')?.addEventListener('click',closeAccess); window.addEventListener('remote-gate-language',()=>render());
  }
  window.RemoteGateGateControls={bind,render,canActivate,activate,familyAvailable,familySelectable,transactionLocked};
})();
