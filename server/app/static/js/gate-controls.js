(() => {
  let context = null;
  let transaction = null;
  let transactionPoll = 0;
  const $ = (id) => document.getElementById(id);
  const endpointSelect = () => $('endpoint-select') || $('wan-select');
  const egressSelect = () => $('egress-select');
  const zh = () => document.documentElement.dataset.lang === 'zh';

  function data() { return context?.getData?.() || {}; }
  function inventoryWans() { return Array.isArray(data()?.inventory?.wans) ? data().inventory.wans : []; }

  function endpointsFor(family) {
    const selectedWg = $('wg-select')?.value || '';
    const list = Array.isArray(data()?.endpoints) ? data().endpoints : [];
    return list.filter((item) =>
      item &&
      item.family === family &&
      ['direct','mapped','egress_probe'].includes(item.reachability) &&
      (!selectedWg || item.wireguard === selectedWg)
    );
  }

  function endpointScore(item) {
    if (!item) return 999;
    if (item.family === 'ipv4' && item.reachability === 'direct') return 0;
    if (item.family === 'ipv6' && item.reachability === 'direct') return 10;
    if (item.family === 'ipv4' && item.reachability === 'mapped') return 20;
    if (item.family === 'ipv4' && item.reachability === 'egress_probe') return 30;
    return Number(item.priority || 999);
  }

  function endpointCompare(a, b) {
    return endpointScore(a) - endpointScore(b)
      || String(a?.wan || '').localeCompare(String(b?.wan || ''))
      || String(a?.id || '').localeCompare(String(b?.id || ''));
  }

  function preferredIpv4Endpoint() { return [...endpointsFor('ipv4')].sort(endpointCompare)[0] || null; }

  function preferredIpv6Endpoint() {
    const endpoints = [...endpointsFor('ipv6')];
    if (!endpoints.length) return null;
    const preferredV4Wan = preferredIpv4Endpoint()?.wan || '';
    return endpoints.sort((a, b) => {
      const aSame = preferredV4Wan && a?.wan === preferredV4Wan ? 0 : 1;
      const bSame = preferredV4Wan && b?.wan === preferredV4Wan ? 0 : 1;
      return aSame - bSame || endpointCompare(a, b);
    })[0] || null;
  }

  function accessRole(item) {
    if (item?.access_method === 'mapped' || item?.reachability === 'mapped') return 'Mapped';
    if (item?.access_method === 'relay' || item?.reachability === 'relay') return 'Relay';
    if (item?.provider === 'egress_probe' || item?.reachability === 'egress_probe') return 'NAT egress · Try';
    return 'Direct';
  }

  function endpointAddress(item) {
    const address = String(item?.external_address || '');
    if (!address) return '—';
    return item?.family === 'ipv6' ? `[${address}]:${item.external_port}` : `${address}:${item.external_port}`;
  }

  function pathRow(family, wan, role, value) {
    return {family: family === 'ipv6' ? 'IPv6' : 'IPv4', wan: String(wan || '—'), role: String(role || ''), value: String(value || '—')};
  }

  function setPathRows(option, rows, primary = false) {
    if (!option) return;
    option.dataset.pathRows = JSON.stringify(rows || []);
    option.dataset.pathPrimary = primary ? '1' : '0';
  }

  function dualTier(pair) {
    const direct4 = pair?.ipv4?.reachability === 'direct';
    const mapped4 = pair?.ipv4?.reachability === 'mapped';
    const direct6 = pair?.ipv6?.reachability === 'direct';
    if (pair?.sameWan && direct4 && direct6) return 0;
    if (pair?.sameWan && mapped4 && direct6) return 1;
    if (!pair?.sameWan && (direct4 || mapped4) && direct6) return 2;
    if (pair?.sameWan) return 3;
    return 4;
  }

  function dualEndpointPairs() {
    const v4 = endpointsFor('ipv4');
    const v6 = endpointsFor('ipv6');
    const pairs = [];
    const seen = new Set();
    const pushPair = (ipv4, ipv6) => {
      if (!ipv4 || !ipv6 || ipv4.wireguard !== ipv6.wireguard) return;
      const id = `dual:${ipv4.id}:${ipv6.id}`;
      if (seen.has(id)) return;
      seen.add(id);
      const sameWan = ipv4.wan === ipv6.wan && ipv4.device === ipv6.device;
      const pair = {
        id,
        wan: sameWan ? ipv4.wan : '',
        wan4: ipv4.wan,
        wan6: ipv6.wan,
        device: sameWan ? ipv4.device : '',
        device4: ipv4.device,
        device6: ipv6.device,
        wireguard: ipv4.wireguard,
        sameWan,
        ipv4,
        ipv6,
        score: endpointScore(ipv4) + endpointScore(ipv6)
      };
      pair.tier = dualTier(pair);
      pairs.push(pair);
    };
    v4.forEach((ipv4) => v6.forEach((ipv6) => pushPair(ipv4, ipv6)));
    return pairs.sort((a, b) =>
      a.tier - b.tier
      || a.score - b.score
      || String(a.wan4).localeCompare(String(b.wan4))
      || String(a.wan6).localeCompare(String(b.wan6))
      || String(a.id).localeCompare(String(b.id))
    );
  }

  function preferredSelection(family) {
    if (family === 'ipv4') return preferredIpv4Endpoint()?.id || '';
    if (family === 'ipv6') return preferredIpv6Endpoint()?.id || '';
    if (family === 'dual') return dualEndpointPairs()[0]?.id || '';
    return '';
  }

  function endpointWansForSelection(family, value) {
    if (!value) return {ipv4:'', ipv6:''};
    if (family === 'dual') {
      const pair = dualEndpointPairs().find((item) => item.id === value);
      return {ipv4:String(pair?.wan4 || ''), ipv6:String(pair?.wan6 || '')};
    }
    const wan = endpointsFor(family).find((item) => item.id === value)?.wan || '';
    return family === 'ipv6' ? {ipv4:'', ipv6:String(wan)} : {ipv4:String(wan), ipv6:''};
  }

  function endpointWanForSelection(family, value) {
    const wans = endpointWansForSelection(family, value);
    if (family === 'dual') return wans.ipv4 && wans.ipv4 === wans.ipv6 ? wans.ipv4 : '';
    return family === 'ipv6' ? wans.ipv6 : wans.ipv4;
  }

  function selectedAccessWans() {
    const family = context?.state?.family;
    if (!['ipv4','ipv6','dual'].includes(family)) return {ipv4:'', ipv6:''};
    return endpointWansForSelection(family, String(endpointSelect()?.value || ''));
  }

  function endpointSelectionIsManual(family = context?.state?.family) {
    return Boolean(context?.state?.endpointManualSelections?.[family]);
  }

  function publishEndpointSelection(family = context?.state?.family) {
    if (!['ipv4','ipv6','dual'].includes(family)) return;
    const select = endpointSelect();
    const value = String(select?.value || '');
    const confirmed = Boolean(value);
    const source = endpointSelectionIsManual(family) ? 'manual' : 'auto';
    if (select) {
      select.dataset.selectionFamily = family;
      select.dataset.selectionConfirmed = confirmed ? '1' : '0';
      select.dataset.selectionSource = confirmed ? source : '';
    }
    window.dispatchEvent(new CustomEvent('remote-gate-endpoint-selection', {detail: {family, value, confirmed, source}}));
  }

  function decorateSingleEndpointOptions(family) {
    if (!['ipv4','ipv6'].includes(family)) return;
    const select = endpointSelect();
    if (!select) return;
    const byId = new Map(endpointsFor(family).map((item) => [item.id, item]));
    const preferred = preferredSelection(family);
    [...select.options].forEach((option) => {
      const item = byId.get(option.value);
      if (!item) return;
      setPathRows(option, [pathRow(family, item.wan, accessRole(item), endpointAddress(item))], option.value === preferred);
    });
  }

  function egressSelectionIsManual(family = context?.state?.family) {
    return Boolean(context?.state?.egressManualSelections?.[family]);
  }

  function recentTerminalFailure(last) {
    if (!last || !['failed','expired'].includes(String(last.state || ''))) return false;
    const terminalAt = Number(last.acked_at || last.expires_at || last.created_at || 0);
    if (!terminalAt) return false;
    return Math.max(0, Math.floor(Date.now() / 1000) - terminalAt) <= 120;
  }

  function rememberEndpointSelection(family = context?.state?.family) {
    if (!context || !['ipv4','ipv6','dual'].includes(family) || !endpointSelectionIsManual(family)) return;
    const select = endpointSelect();
    const value = String(select?.value || '');
    if (!value) { publishEndpointSelection(family); return; }
    if (!context.state.endpointSelections || typeof context.state.endpointSelections !== 'object') context.state.endpointSelections = {};
    const wans = endpointWansForSelection(family, value);
    context.state.endpointSelections[family] = {
      value,
      wan: wans.ipv4 && wans.ipv4 === wans.ipv6 ? wans.ipv4 : endpointWanForSelection(family, value),
      wan4: wans.ipv4,
      wan6: wans.ipv6
    };
    publishEndpointSelection(family);
  }

  function restoreEndpointSelection(family = context?.state?.family) {
    if (!context || !['ipv4','ipv6'].includes(family)) return;
    const select = endpointSelect();
    if (!select) return;
    decorateSingleEndpointOptions(family);
    select.disabled = false;
    const saved = context.state.endpointSelections?.[family];
    const options = [...select.options].filter((option) => option.value);
    if (endpointSelectionIsManual(family) && saved) {
      const exact = options.find((option) => option.value === saved.value);
      if (exact) {
        select.value = exact.value;
        publishEndpointSelection(family);
        window.RemoteGateEndpointPicker?.sync?.('endpoint-select');
        return;
      }
      const fallback = saved.wan ? options.find((option) => endpointWanForSelection(family, option.value) === saved.wan) : null;
      if (fallback) {
        select.value = fallback.value;
        context.state.endpointSelections[family] = {value:fallback.value, wan:saved.wan, wan4:family === 'ipv4' ? saved.wan : '', wan6:family === 'ipv6' ? saved.wan : ''};
        publishEndpointSelection(family);
        window.RemoteGateEndpointPicker?.sync?.('endpoint-select');
        return;
      }
      context.state.endpointManualSelections[family] = false;
      delete context.state.endpointSelections[family];
    }
    const preferred = preferredSelection(family);
    select.value = options.some((option) => option.value === preferred) ? preferred : '';
    publishEndpointSelection(family);
    window.RemoteGateEndpointPicker?.sync?.('endpoint-select');
  }

  function syncDualEndpointSelect() {
    if (!context || context.state.family !== 'dual') return;
    const select = endpointSelect();
    if (!select) return;
    const saved = context.state.endpointSelections?.dual;
    const manual = endpointSelectionIsManual('dual');
    const prior = manual ? String(saved?.value || '') : '';
    const priorWan4 = manual ? String(saved?.wan4 || saved?.wan || '') : '';
    const priorWan6 = manual ? String(saved?.wan6 || saved?.wan || '') : '';
    const pairs = dualEndpointPairs();
    select.replaceChildren();
    select.disabled = false;
    if (!pairs.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = context.t('common.unavailable');
      select.append(option);
      publishEndpointSelection('dual');
      window.RemoteGateEndpointPicker?.sync?.('endpoint-select');
      return;
    }
    pairs.forEach((pair, index) => {
      const option = document.createElement('option');
      option.value = pair.id;
      option.dataset.ipv4EndpointId = pair.ipv4.id;
      option.dataset.ipv6EndpointId = pair.ipv6.id;
      option.dataset.ipv4Wan = pair.wan4;
      option.dataset.ipv6Wan = pair.wan6;
      option.dataset.splitWan = pair.sameWan ? '0' : '1';
      setPathRows(option, [
        pathRow('ipv4', pair.wan4, accessRole(pair.ipv4), endpointAddress(pair.ipv4)),
        pathRow('ipv6', pair.wan6, accessRole(pair.ipv6), endpointAddress(pair.ipv6))
      ], index === 0);
      option.textContent = `${pair.wan4}/${pair.wan6} · IPv4 + IPv6 · ${accessRole(pair.ipv4)} + ${accessRole(pair.ipv6)} · ${endpointAddress(pair.ipv4)} + ${endpointAddress(pair.ipv6)}`;
      select.append(option);
    });
    const exact = [...select.options].find((option) => option.value === prior);
    if (exact) select.value = exact.value;
    else if (manual && (priorWan4 || priorWan6)) {
      const pair = pairs.find((item) => item.wan4 === priorWan4 && item.wan6 === priorWan6);
      if (pair) {
        select.value = pair.id;
        context.state.endpointSelections.dual = {value:pair.id, wan:pair.sameWan ? pair.wan : '', wan4:pair.wan4, wan6:pair.wan6};
      } else {
        context.state.endpointManualSelections.dual = false;
        delete context.state.endpointSelections.dual;
        select.value = pairs[0].id;
      }
    } else select.value = pairs[0].id;
    publishEndpointSelection('dual');
    window.RemoteGateEndpointPicker?.sync?.('endpoint-select');
  }

  function wanSupportsEgress(wan, family) {
    if (!wan?.up) return false;
    if (family === 'ipv4') return Boolean(wan.default_route_v4);
    if (family === 'ipv6') {
      if (!wan.default_route_v6) return false;
      return (Array.isArray(wan.ipv6) ? wan.ipv6 : []).some((entry) => entry?.kind === 'global' && entry?.address);
    }
    return false;
  }

  function egressAddress(wan, family) {
    if (family === 'ipv6') {
      const global6 = (Array.isArray(wan?.ipv6) ? wan.ipv6 : []).find((entry) => entry?.kind === 'global' && entry?.address);
      return String(global6?.address || '—');
    }
    const endpoints = Array.isArray(data()?.endpoints) ? data().endpoints : [];
    const direct4 = (Array.isArray(wan?.ipv4) ? wan.ipv4 : []).find((entry) => entry?.kind === 'public' && entry?.address);
    const observed4 = endpoints.find((item) => item?.wan === wan?.name && item?.family === 'ipv4' && item?.provider === 'egress_probe');
    const local4 = (Array.isArray(wan?.ipv4) ? wan.ipv4 : [])[0];
    return String(direct4?.address || observed4?.external_address || local4?.address || '—');
  }

  function egressScore(wan, family) {
    if (family === 'ipv6') return 0;
    const endpoints = Array.isArray(data()?.endpoints) ? data().endpoints : [];
    if ((Array.isArray(wan?.ipv4) ? wan.ipv4 : []).some((entry) => entry?.kind === 'public')) return 0;
    if (endpoints.some((item) => item?.wan === wan?.name && item?.family === 'ipv4' && item?.provider === 'egress_probe')) return 10;
    return 20;
  }

  function egressCandidates(mode = 'ipv4') {
    if (!['ipv4','ipv6'].includes(mode)) return [];
    return inventoryWans()
      .filter((wan) => wanSupportsEgress(wan, mode))
      .map((wan) => ({wan, family:mode, address:egressAddress(wan, mode), score:egressScore(wan, mode)}))
      .sort((a, b) => a.score - b.score || String(a.wan.name).localeCompare(String(b.wan.name)));
  }

  function egressPlanValue(plan) {
    if (!plan || plan.mode === 'none') return '__lan__';
    if (plan.mode === 'ipv4') return `ipv4:${plan.ipv4}`;
    if (plan.mode === 'ipv6') return `ipv6:${plan.ipv6}`;
    return `dual:${plan.ipv4}|${plan.ipv6}`;
  }

  function egressPlans() {
    const v4 = egressCandidates('ipv4');
    const v6 = egressCandidates('ipv6');
    const single4 = v4.map((item) => ({mode:'ipv4', ipv4:item.wan.name, ipv6:'', score:item.score, rows:[pathRow('ipv4', item.wan.name, '', item.address)]}));
    const single6 = v6.map((item) => ({mode:'ipv6', ipv4:'', ipv6:item.wan.name, score:item.score, rows:[pathRow('ipv6', item.wan.name, '', item.address)]}));
    const dual = [];
    v4.forEach((item4) => v6.forEach((item6) => dual.push({
      mode:'dual',
      ipv4:item4.wan.name,
      ipv6:item6.wan.name,
      score:item4.score + item6.score + (item4.wan.name === item6.wan.name ? 0 : 5),
      rows:[pathRow('ipv4', item4.wan.name, '', item4.address), pathRow('ipv6', item6.wan.name, '', item6.address)]
    })));
    dual.sort((a,b) => a.score - b.score || String(a.ipv4).localeCompare(String(b.ipv4)) || String(a.ipv6).localeCompare(String(b.ipv6)));
    return [...single4, ...single6, ...dual.slice(0, 64)].map((plan) => ({...plan, value:egressPlanValue(plan)}));
  }

  function preferredEgressMode() {
    const family = context?.state?.family;
    return family === 'ipv6' ? 'ipv6' : family === 'dual' ? 'dual' : 'ipv4';
  }

  function defaultEgressValue(plans = egressPlans()) {
    const mode = preferredEgressMode();
    const access = selectedAccessWans();
    const exact = plans.find((plan) =>
      plan.mode === mode &&
      (mode !== 'ipv4' || plan.ipv4 === access.ipv4) &&
      (mode !== 'ipv6' || plan.ipv6 === access.ipv6) &&
      (mode !== 'dual' || (plan.ipv4 === access.ipv4 && plan.ipv6 === access.ipv6))
    );
    return exact?.value || plans.find((plan) => plan.mode === mode)?.value || '__lan__';
  }

  function ensureEgressControl() {
    let select = egressSelect();
    if (select) return select;
    const endpoint = endpointSelect();
    const endpointField = endpoint?.closest?.('.field');
    if (!endpoint || !endpointField) return null;
    const field = document.createElement('div');
    field.className = 'field compact-field full-row';
    const label = document.createElement('span');
    label.dataset.egressLabel = '1';
    label.textContent = zh() ? 'Internet 出口' : 'Internet Exit';
    select = document.createElement('select');
    select.id = 'egress-select';
    select.setAttribute('aria-label', label.textContent);
    field.append(label, select);
    endpointField.insertAdjacentElement('afterend', field);
    window.RemoteGateEndpointPicker?.bindSelect?.('egress-select', {
      eyebrow:'INTERNET EXIT',
      title:() => zh() ? '选择上网出口' : 'Choose Internet exit',
      empty:() => zh() ? '当前没有可用 Internet 出口。' : 'No Internet exit is currently available.'
    });
    return select;
  }

  function syncEgressSelect() {
    if (!context) return;
    const select = ensureEgressControl();
    if (!select) return;
    const state = context.state;
    const family = state.family;
    if (!state.egressManualSelections || typeof state.egressManualSelections !== 'object') state.egressManualSelections = {};
    const label = document.querySelector('[data-egress-label]');
    if (label) label.textContent = zh() ? 'Internet 出口' : 'Internet Exit';
    const remembered = String(state.egressSelections?.[family] || '');
    const plans = egressPlans();
    const modeOrder = [preferredEgressMode(), 'ipv4', 'ipv6', 'dual'].filter((mode, index, values) => values.indexOf(mode) === index);
    const ranked = [...plans].sort((a,b) => modeOrder.indexOf(a.mode) - modeOrder.indexOf(b.mode) || a.score - b.score || a.value.localeCompare(b.value));
    select.replaceChildren();

    const local = document.createElement('option');
    local.value = '__lan__';
    local.dataset.egressMode = 'none';
    local.dataset.ipv4Wan = '';
    local.dataset.ipv6Wan = '';
    local.textContent = zh() ? 'LAN only · 仅访问家庭网络 · 不代理 Internet' : 'LAN only · Private access · No Internet exit';
    select.append(local);

    ranked.forEach((plan) => {
      const option = document.createElement('option');
      option.value = plan.value;
      option.dataset.egressMode = plan.mode;
      option.dataset.ipv4Wan = plan.ipv4;
      option.dataset.ipv6Wan = plan.ipv6;
      setPathRows(option, plan.rows, plan.value === defaultEgressValue(plans));
      if (plan.mode === 'dual') {
        option.textContent = `${plan.ipv4}/${plan.ipv6} · IPv4 + IPv6 · Internet Exit · ${plan.rows[0].value} + ${plan.rows[1].value}`;
      } else {
        const row = plan.rows[0];
        option.textContent = `${row.wan} · ${row.family} Exit · Internet Exit · ${row.value}`;
      }
      select.append(option);
    });

    const hasOption = (value) => Boolean(value && [...select.options].some((option) => option.value === value));
    const defaultValue = defaultEgressValue(plans);
    if (egressSelectionIsManual(family) && hasOption(remembered)) select.value = remembered;
    else {
      if (egressSelectionIsManual(family) && !hasOption(remembered)) state.egressManualSelections[family] = false;
      select.value = hasOption(defaultValue) ? defaultValue : '__lan__';
    }
    state.egressWan = select.value;
    select.disabled = false;
    window.RemoteGateEndpointPicker?.bindSelect?.('egress-select', {
      eyebrow:'INTERNET EXIT',
      title:() => zh() ? '选择上网出口' : 'Choose Internet exit',
      empty:() => zh() ? '当前没有可用 Internet 出口。' : 'No Internet exit is currently available.'
    });
    window.RemoteGateEndpointPicker?.sync?.('egress-select');
  }

  function selectedEgressPlan() {
    const option = egressSelect()?.selectedOptions?.[0];
    const mode = String(option?.dataset?.egressMode || 'none');
    if (mode === 'none') return {mode:'none', ipv4:'', ipv6:''};
    return {
      mode: ['ipv4','ipv6','dual'].includes(mode) ? mode : 'none',
      ipv4:String(option?.dataset?.ipv4Wan || ''),
      ipv6:String(option?.dataset?.ipv6Wan || '')
    };
  }

  function selectedEgressWan() {
    const plan = selectedEgressPlan();
    if (plan.mode === 'ipv4') return plan.ipv4;
    if (plan.mode === 'ipv6') return plan.ipv6;
    if (plan.mode === 'dual' && plan.ipv4 && plan.ipv4 === plan.ipv6) return plan.ipv4;
    return '';
  }

  function reportedEgress(currentData = data()) {
    const value = currentData?.agent?.egress;
    return value && typeof value === 'object' ? value : {active:false,state:'inactive',mode:'',wan:'',wan_v4:'',wan_v6:'',detail:'',expires_in:0};
  }

  function egressMatchesSelection(egress, plan) {
    if (!egress || !plan || plan.mode === 'none') return false;
    if (plan.mode === 'ipv4') return Boolean(plan.ipv4 && String(egress.wan_v4 || egress.wan || '') === plan.ipv4 && String(egress.mode || '') === 'ipv4');
    if (plan.mode === 'ipv6') return Boolean(plan.ipv6 && String(egress.wan_v6 || egress.wan || '') === plan.ipv6 && String(egress.mode || '') === 'ipv6');
    return Boolean(
      plan.ipv4 && plan.ipv6 && String(egress.mode || '') === 'dual' &&
      String(egress.wan_v4 || egress.wan || '') === plan.ipv4 &&
      String(egress.wan_v6 || egress.wan || '') === plan.ipv6
    );
  }

  function egressPlanLabel(plan) {
    if (!plan || plan.mode === 'none') return '';
    if (plan.mode === 'ipv4') return `IPv4 ${plan.ipv4}`;
    if (plan.mode === 'ipv6') return `IPv6 ${plan.ipv6}`;
    return `IPv4 ${plan.ipv4} · IPv6 ${plan.ipv6}`;
  }

  function sourceFor(family) { return data()?.client_sources?.[family]?.address || ''; }
  function gateCapability(family) {
    const caps = data()?.inventory?.capabilities || {};
    if (family === 'ipv6') return Boolean(caps.gate_ipv6);
    if (family === 'ipv4') return caps.gate_ipv4 !== false;
    return false;
  }
  function singleSelectable(family) { return ['ipv4','ipv6'].includes(family); }
  function familySelectable(family) {
    if (family === 'ipv4') return gateCapability('ipv4');
    if (family === 'ipv6') return gateCapability('ipv6');
    if (family === 'dual') return gateCapability('ipv4') && gateCapability('ipv6');
    return false;
  }
  function singleReady(family) { return singleSelectable(family) && gateCapability(family) && endpointsFor(family).length > 0; }
  function singleAvailable(family) { return singleReady(family) && Boolean(sourceFor(family)); }
  function familyAvailable(family) {
    if (family === 'dual') return Boolean(gateCapability('ipv4') && gateCapability('ipv6') && sourceFor('ipv4') && sourceFor('ipv6') && dualEndpointPairs().length);
    return singleAvailable(family);
  }
  function chooseFamily() {
    const state = context.state;
    if (state.familyManual && familySelectable(state.family)) return state.family;
    if (singleAvailable('ipv4')) return 'ipv4';
    if (state.requestFamily === 'ipv6' && singleReady('ipv6')) return 'ipv6';
    if (state.requestFamily === 'ipv4' && singleReady('ipv4')) return 'ipv4';
    if (singleAvailable('ipv6')) return 'ipv6';
    if (singleReady('ipv4')) return 'ipv4';
    if (singleReady('ipv6')) return 'ipv6';
    if (familySelectable('ipv4')) return 'ipv4';
    if (familySelectable('ipv6')) return 'ipv6';
    return 'ipv4';
  }
  function familyReason(family) {
    const t = context.t;
    if (family === 'dual') {
      if (!gateCapability('ipv4')) return zh() ? '此 OpenWrt 的 IPv4 Gate 已禁用。' : 'IPv4 Gate is disabled on this OpenWrt device.';
      if (!gateCapability('ipv6')) return t('gate.ipv6Unavailable');
      if (!dualEndpointPairs().length) return zh() ? 'Dual 需要同一 WireGuard 服务同时存在可用的 IPv4 与 IPv6 Endpoint。' : 'Dual requires available IPv4 and IPv6 endpoints for the same WireGuard service.';
      if (!sourceFor('ipv4') || !sourceFor('ipv6')) return zh() ? 'IPv4 与 IPv6 Source 都就绪后可同时授权。' : 'Both IPv4 and IPv6 sources are required for dual-stack authorization.';
      const selected = selectedDualPair() || dualEndpointPairs()[0];
      const label = selected?.sameWan ? selected.wan : `IPv4 ${selected?.wan4 || '—'} + IPv6 ${selected?.wan6 || '—'}`;
      return zh() ? `双栈就绪 · IPv4 + IPv6 已识别 · ${label}` : `Dual stack ready · IPv4 + IPv6 detected · ${label}`;
    }
    if (family === 'ipv4' && !gateCapability('ipv4')) return zh() ? '此 OpenWrt 的 IPv4 Gate 已禁用。' : 'IPv4 Gate is disabled on this OpenWrt device.';
    if (family === 'ipv6' && !gateCapability('ipv6')) return t('gate.ipv6Unavailable');
    const endpoints = endpointsFor(family);
    if (!endpoints.length) return t('gate.familyEndpointMissing', {family:family.toUpperCase()});
    const source = sourceFor(family);
    if (!source) return t('gate.familySourceMissing', {family:family.toUpperCase()});
    const request = context.state.requestFamily === 'ipv6' ? 'IPv6' : context.state.requestFamily === 'ipv4' ? 'IPv4' : '—';
    return t('gate.familyReady', {family:family.toUpperCase(), source, count:endpoints.length, request});
  }

  function notify(message, kind = 'info', options = {}) {
    if (window.RemoteGateFeedback?.notify) return window.RemoteGateFeedback.notify(message, kind, options);
    context?.toast?.(message, kind === 'error' ? 'error' : 'info');
    return null;
  }
  function pendingCommand(currentData = data()) { return currentData?.gate?.queue?.pending || null; }
  function lockAction(currentData = data()) { return transaction?.action || pendingCommand(currentData)?.action || ''; }
  function lockMessage(currentData = data()) {
    if (lockAction(currentData) === 'close') return zh() ? '正在关闭远程访问，请等待操作完成。' : 'Closing remote access. Please wait for the operation to finish.';
    return zh() ? '正在激活远程访问，请等待 OpenWrt 应用授权。' : 'Activating remote access. Waiting for OpenWrt to apply the authorization.';
  }
  function startTransactionPoll() { if (!transactionPoll) transactionPoll = window.setInterval(() => window.RemoteGateApp?.refresh?.(), 1000); }
  function stopTransactionPoll() { if (transactionPoll) window.clearInterval(transactionPoll); transactionPoll = 0; }
  function clearTransaction() { transaction = null; stopTransactionPoll(); }
  function transactionMatches(last) {
    if (!transaction || !last) return false;
    if (transaction.batchId && last.batch_id === transaction.batchId) return true;
    if (transaction.commandId && last.id === transaction.commandId) return true;
    const createdAt = Number(last.created_at || 0);
    const localStartedAt = Math.floor(Number(transaction.startedAt || 0) / 1000);
    return !transaction.commandId && !transaction.batchId && last.action === transaction.action && createdAt >= localStartedAt - 2;
  }
  function syncTransaction(currentData) {
    const queue = currentData?.gate?.queue || {};
    const pending = queue.pending;
    const last = queue.last;
    if (pending && !transaction) {
      transaction = {action:String(pending.action || 'activate'), commandId:String(pending.id || ''), batchId:String(pending.batch_id || ''), startedAt:Number(pending.created_at || 0) * 1000 || Date.now(), serverOwned:true};
      startTransactionPoll();
    }
    if (!transaction) return false;
    startTransactionPoll();
    if (pending) return true;
    if (transactionMatches(last) && ['done','failed','expired'].includes(String(last.state || ''))) {
      const terminal = String(last.state || '');
      if (terminal === 'failed' || terminal === 'expired') {
        const fallback = terminal === 'expired' ? (zh() ? '激活请求已过期。' : 'The remote access request expired.') : (zh() ? '远程访问操作失败。' : 'The remote access operation failed.');
        notify(String(last.detail || fallback), 'error', {title:zh() ? '操作失败' : 'Action failed', duration:5200});
      } else {
        const closing = transaction.action === 'close';
        notify(closing ? (zh() ? '远程访问已关闭。' : 'Remote access is closed.') : (zh() ? '远程访问已开启。' : 'Remote access is active.'), 'success', {title:closing ? (zh() ? '已关闭' : 'Closed') : (zh() ? '激活成功' : 'Activated')});
      }
      clearTransaction();
      return false;
    }
    return true;
  }
  function transactionLocked(currentData = data()) { return Boolean(transaction || pendingCommand(currentData)); }

  function selectedDualPair() {
    if (context?.state?.family !== 'dual') return null;
    return dualEndpointPairs().find((pair) => pair.id === String(endpointSelect()?.value || '')) || null;
  }

  function canActivate() {
    if (!context || transactionLocked()) return false;
    const state = context.state;
    const endpointReady = state.family === 'dual' ? Boolean(selectedDualPair()) : Boolean(endpointSelect()?.value);
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
    const next = chooseFamily();
    if (previous !== next) rememberEndpointSelection(previous);
    state.family = next;
    const compactLabel = {ipv4:'IPv4', ipv6:'IPv6', dual:'Dual'};
    familyRoot.querySelectorAll('[data-family]').forEach((button) => {
      const family = button.dataset.family;
      if (!['ipv4','ipv6','dual'].includes(family)) return;
      const selectable = familySelectable(family);
      button.hidden = false;
      button.textContent = compactLabel[family];
      button.disabled = !selectable;
      button.classList.toggle('active', family === state.family);
      button.setAttribute('aria-pressed', family === state.family ? 'true' : 'false');
      button.setAttribute('aria-disabled', selectable ? 'false' : 'true');
      button.title = familyReason(family);
    });
    const note = $('family-note'); if (note) note.textContent = familyReason(state.family);
    if (previous !== state.family) {
      context.onFamilyChange?.(state.family);
      if (state.family === 'dual') syncDualEndpointSelect(); else restoreEndpointSelection(state.family);
    }
  }

  function syncScope() {
    if (!context) return;
    const root = $('scope-segment'); if (!root) return;
    if (!['wg','wg_ping'].includes(context.state.scope)) context.state.scope = 'wg';
    root.querySelectorAll('[data-scope]').forEach((button) => {
      const active = button.dataset.scope === context.state.scope;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function authorizationForSource(fw, family) {
    const item = fw?.families?.[family] || {};
    const source = sourceFor(family);
    const entries = Array.isArray(item.authorizations) ? item.authorizations : null;
    if (!entries || !source) return null;
    return entries.find((entry) => entry?.source_ip === source) || null;
  }
  function sourceAuthorized(fw, family) {
    const item = fw?.families?.[family] || {};
    const source = sourceFor(family);
    const authorized = Array.isArray(item.authorized_sources) ? item.authorized_sources : null;
    if (authorized) return Boolean(source && authorized.includes(source));
    const legacySource = String(item.source_ip || (fw?.family === family ? fw?.source_ip || '' : ''));
    return Boolean(source && (item.active || (fw?.active && fw?.family === family)) && legacySource === source);
  }
  function sourceExpiresIn(fw, family) {
    const entry = authorizationForSource(fw, family);
    return Number(entry?.expires_in || fw?.families?.[family]?.expires_in || 0);
  }
  function activeFamilyState(fw, family) {
    if (family === 'dual') return sourceAuthorized(fw, 'ipv4') && sourceAuthorized(fw, 'ipv6');
    return sourceAuthorized(fw, family);
  }

  function setLockedControls(locked, action, active, activatable) {
    const form = document.querySelector('.gate-form');
    if (form) {
      form.classList.toggle('transaction-locked', locked);
      form.inert = Boolean(locked);
      form.querySelectorAll('button, select, input').forEach((control) => {
        if (locked) {
          if (!Object.prototype.hasOwnProperty.call(control.dataset, 'transactionWasDisabled')) control.dataset.transactionWasDisabled = control.disabled ? '1' : '0';
          control.disabled = true;
        } else if (Object.prototype.hasOwnProperty.call(control.dataset, 'transactionWasDisabled')) {
          control.disabled = control.dataset.transactionWasDisabled === '1';
          delete control.dataset.transactionWasDisabled;
        }
      });
    }
    const orb = $('gate-orb'); if (orb && locked) orb.disabled = true;
    const activateButton = $('activate-button');
    const closeButton = $('close-button');
    if (activateButton) {
      const showActivate = locked ? action === 'activate' : !active;
      activateButton.classList.toggle('hidden', !showActivate);
      activateButton.disabled = locked || !activatable;
      activateButton.classList.toggle('transaction-locked', locked && action === 'activate');
      activateButton.setAttribute('aria-disabled', activateButton.disabled ? 'true' : 'false');
    }
    if (closeButton) {
      const showClose = locked ? action === 'close' : active;
      closeButton.classList.toggle('hidden', !showClose);
      closeButton.disabled = locked || Boolean(context?.state?.busy);
      closeButton.classList.toggle('transaction-locked', locked && action === 'close');
      closeButton.setAttribute('aria-disabled', closeButton.disabled ? 'true' : 'false');
    }
  }

  function render(currentData = data()) {
    if (!context) return;
    const state = context.state, t = context.t, remaining = context.remaining;
    syncFamily(); syncScope();
    if (state.family === 'dual') syncDualEndpointSelect(); else restoreEndpointSelection(state.family);
    syncEgressSelect();
    const locked = syncTransaction(currentData);
    const pending = currentData?.gate?.queue?.pending, next = currentData?.gate?.queue?.next, last = currentData?.gate?.queue?.last;
    const fw = currentData?.agent?.firewall || {}, active = activeFamilyState(fw, state.family), pendingAction = pending?.action, orb = $('gate-orb');
    const egress = reportedEgress(currentData), selectedExitPlan = selectedEgressPlan(), selectedExit = egressPlanLabel(selectedExitPlan), selectedExitMatches = egressMatchesSelection(egress, selectedExitPlan);
    let mode='closed', title=t('gate.closed'), subtitle=t('gate.closedSub'), badge=t('gate.closedBadge');
    if (pendingAction === 'activate' || (locked && lockAction(currentData) === 'activate')) {
      mode='authorizing'; title=t('gate.authorizing');
      const queued = Array.isArray(next) ? next.length : 0;
      subtitle = queued > 0 ? (zh() ? `正在授权 ${String(pending?.family||'').toUpperCase()}，随后继续下一协议族…` : `Authorizing ${String(pending?.family||'').toUpperCase()}, then continuing with the next family…`) : (zh() ? '正在等待 OpenWrt 应用临时授权…' : 'Waiting for OpenWrt to apply the temporary authorization…');
      badge=t('gate.pendingBadge');
    } else if (pendingAction === 'close' || (locked && lockAction(currentData) === 'close')) {
      mode='authorizing'; title=t('gate.closing'); subtitle=zh() ? '正在等待 OpenWrt 清除临时授权…' : 'Waiting for OpenWrt to clear temporary authorizations…'; badge=t('gate.pendingBadge');
    } else if (active) {
      mode='open'; title=t('gate.open');
      const selected = state.family === 'dual' ? [sourceExpiresIn(fw,'ipv4'), sourceExpiresIn(fw,'ipv6')] : [sourceExpiresIn(fw,state.family)];
      const values=selected.map(Number).filter((x)=>x>0), ttl=values.length?Math.min(...values):Number(fw.expires_in||0);
      subtitle=t('gate.expiresIn',{value:remaining(ttl)}); badge=t('gate.authorizedBadge');
      if (selectedExit) {
        if (selectedExitMatches && egress.state === 'failed') {
          mode='error'; title=zh() ? 'OPEN · 出口失败' : 'OPEN · EXIT FAILED'; subtitle=String(egress.detail || (zh() ? 'Internet 出口启用失败。' : 'Internet egress failed to activate.')); badge='EXIT FAILED';
        } else if (selectedExitMatches && egress.active && egress.state === 'active') {
          const egressTtl=Number(egress.expires_in||0);
          subtitle=zh() ? `Internet 出口 ${selectedExit} · ${String(egress.mode||'').toUpperCase()} · 剩余 ${remaining(egressTtl)}` : `Internet Exit ${selectedExit} · ${String(egress.mode||'').toUpperCase()} · ${remaining(egressTtl)} remaining`;
          badge='EXIT ACTIVE';
        } else {
          title=zh() ? 'OPEN · 出口未生效' : 'OPEN · EXIT OFF'; subtitle=zh() ? 'Gate 已授权，但所选 Internet 出口当前未处于 Active。' : 'Gate access is open, but the selected Internet exit is not active.'; badge='EXIT OFF';
        }
      }
    } else if (recentTerminalFailure(last)) {
      mode='error'; title=t('gate.error'); subtitle=last.detail || (last.state === 'expired' ? (zh() ? '请求已过期。' : 'The request expired.') : t('gate.agentFailed')); badge=t('gate.errorBadge');
    }
    const activatable=canActivate(), action=lockAction(currentData);
    if (orb) {
      const orbLabel = active ? t('gate.close') : t('gate.activate');
      const orbEnabled = !locked && (active ? !state.busy : (mode === 'closed' && activatable));
      orb.dataset.state=mode; orb.dataset.hint=orbLabel; orb.disabled=!orbEnabled;
      orb.classList.toggle('transaction-locked', locked);
      orb.setAttribute('aria-disabled', orb.disabled ? 'true':'false');
      orb.setAttribute('aria-label', locked ? lockMessage(currentData) : (orbEnabled ? orbLabel : familyReason(state.family)));
      orb.title=locked ? lockMessage(currentData) : (orbEnabled ? orbLabel : familyReason(state.family));
    }
    if ($('gate-state')) $('gate-state').textContent=title;
    if ($('gate-substate')) $('gate-substate').textContent=subtitle;
    if ($('gate-state-badge')) $('gate-state-badge').textContent=badge;
    if ($('gate-lock')) $('gate-lock').textContent=active?'◇':'◆';
    const trustNote=document.querySelector('.trust-note');
    if (trustNote) trustNote.textContent=zh() ? 'Cloudflare HTTP 观察和运营商 Candidate 是当前登录 Session 的来源依据；点击 Activate 后由 VPS 解析所选协议族，OpenWrt 直接应用临时授权，不要求 WireGuard 预先握手。' : 'Cloudflare HTTP observations and carrier candidates are source evidence for the signed-in session. Activate resolves the selected family server-side and OpenWrt applies the temporary authorization without requiring a pre-existing WireGuard handshake.';
    const authorizationSource=$('authorization-source');
    if (authorizationSource) {
      if (state.family === 'dual') {
        const values=['ipv4','ipv6'].filter((family)=>sourceAuthorized(fw,family)).map((family)=>sourceFor(family)).filter(Boolean);
        authorizationSource.textContent=values.length?values.join(' · '):(sourceFor('ipv4')||sourceFor('ipv6')||t('common.unavailable'));
      } else authorizationSource.textContent=sourceFor(state.family)||t('common.unavailable');
    }
    setLockedControls(locked, action, active, activatable);
    if (state.family === 'dual') queueMicrotask(syncDualEndpointSelect);
  }

  async function submit(path, body, action) {
    if (!context) return;
    if (transactionLocked()) { notify(lockMessage(), 'info', {title:zh() ? '操作进行中' : 'Operation in progress'}); return; }
    transaction={action,commandId:'',batchId:'',startedAt:Date.now(),serverOwned:false};
    startTransactionPoll(); context.state.busy=true; render(data());
    try {
      const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':context.state.csrf},body:JSON.stringify(body||{})});
      const payload=response.status===204?{}:await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(String(payload?.error||`HTTP ${response.status}`));
      transaction.commandId=String(payload?.command_id||''); transaction.batchId=String(payload?.batch_id||'');
      notify(action==='close'?(zh()?'关闭请求已提交，正在等待 OpenWrt 确认。':'Close request submitted; waiting for OpenWrt confirmation.'):(zh()?'激活请求已提交，正在等待 OpenWrt 应用授权。':'Activation submitted; waiting for OpenWrt to apply the authorization.'),'info',{title:zh()?'处理中':'In progress'});
      window.RemoteGateApp?.refresh?.();
    } catch(error) {
      notify(String(error?.message||error||'request failed'),'error',{title:zh()?'请求失败':'Request failed',duration:5200}); clearTransaction();
    } finally { context.state.busy=false; render(data()); }
  }

  function activate() {
    if (!context || transactionLocked() || !canActivate()) return;
    rememberEndpointSelection(context.state.family);
    const state=context.state;
    const egressPlan=selectedEgressPlan();
    const egress_wan=selectedEgressWan();
    const egressBody={egress_mode:egressPlan.mode,egress_wan,egress_wans:{ipv4:egressPlan.ipv4,ipv6:egressPlan.ipv6}};
    if (state.family === 'dual') {
      const pair=selectedDualPair(); if(!pair)return;
      submit('/api/v1/gate/activate',{families:['ipv4','ipv6'],endpoint_ids:{ipv4:pair.ipv4.id,ipv6:pair.ipv6.id},...egressBody,scope:state.scope||'wg',ttl:state.ttl},'activate');
      return;
    }
    submit('/api/v1/gate/activate',{endpoint_id:endpointSelect().value,family:state.family,...egressBody,scope:state.scope||'wg',ttl:state.ttl},'activate');
  }
  function closeAccess() { submit('/api/v1/gate/close',{},'close'); }
  function toggleAccess() {
    if (!context || transactionLocked()) return;
    const fw=data()?.agent?.firewall||{};
    if(activeFamilyState(fw,context.state.family)) closeAccess(); else activate();
  }
  function guardedTarget(target) { return target?.closest?.('.gate-form button, .gate-form select, .gate-form input, #gate-orb'); }
  function transactionGuard(event) {
    if(!transactionLocked()||!guardedTarget(event.target))return;
    event.preventDefault(); event.stopImmediatePropagation(); notify(lockMessage(),'info',{title:zh()?'操作进行中':'Operation in progress'});
  }

  function bind(nextContext) {
    context=nextContext;
    const state=context.state;
    if(!state.scope)state.scope='wg';
    if(!state.egressWan)state.egressWan='__lan__';
    if(!state.endpointSelections||typeof state.endpointSelections!=='object')state.endpointSelections={};
    if(!state.endpointManualSelections||typeof state.endpointManualSelections!=='object')state.endpointManualSelections={};
    if(!state.egressManualSelections||typeof state.egressManualSelections!=='object')state.egressManualSelections={};
    if(typeof state.familyManual!=='boolean')state.familyManual=false;
    ensureDualButton(); ensureEgressControl(); syncEgressSelect();
    const gateCard=document.querySelector('.gate-card');
    gateCard?.addEventListener('pointerdown',transactionGuard,true); gateCard?.addEventListener('click',transactionGuard,true); gateCard?.addEventListener('change',transactionGuard,true);
    $('ttl-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-ttl]');if(!button||transactionLocked())return;state.ttl=Number(button.dataset.ttl);$('ttl-segment').querySelectorAll('button').forEach((item)=>{item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',item===button?'true':'false');});});
    $('family-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-family]');if(!button||button.disabled||transactionLocked()||!familySelectable(button.dataset.family))return;rememberEndpointSelection(state.family);state.familyManual=true;state.family=button.dataset.family;context.onFamilyChange?.(state.family);if(state.family==='dual')syncDualEndpointSelect();else restoreEndpointSelection(state.family);syncEgressSelect();render();});
    $('scope-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-scope]');if(!button||transactionLocked()||!['wg','wg_ping'].includes(button.dataset.scope))return;state.scope=button.dataset.scope;syncScope();});
    endpointSelect()?.addEventListener('change',()=>{if(transactionLocked())return;const select=endpointSelect();state.endpointManualSelections[state.family]=Boolean(select?.value);if(!select?.value)delete state.endpointSelections[state.family];rememberEndpointSelection(state.family);publishEndpointSelection(state.family);syncEgressSelect();render();});
    egressSelect()?.addEventListener('change',()=>{if(transactionLocked())return;state.egressWan=egressSelect().value||'__lan__';state.egressManualSelections[state.family]=true;render();});
    $('wg-select')?.addEventListener('change',()=>{if(transactionLocked())return;context.onWireGuardChange?.();syncFamily();render();});
    $('activate-button')?.addEventListener('click',activate); $('gate-orb')?.addEventListener('click',toggleAccess); $('close-button')?.addEventListener('click',closeAccess);
    window.addEventListener('remote-gate-language',()=>{syncEgressSelect();render();});
  }

  window.RemoteGateGateControls={
    bind,render,canActivate,activate,toggleAccess,familyAvailable,familySelectable,transactionLocked,dualEndpointPairs,
    egressCandidates,egressPlans,selectedEgressWan,selectedEgressPlan,reportedEgress,egressMatchesSelection,
    endpointSelectionIsManual,rememberEndpointSelection,restoreEndpointSelection,preferredIpv4Endpoint,preferredIpv6Endpoint,preferredSelection,selectedAccessWans
  };
})();