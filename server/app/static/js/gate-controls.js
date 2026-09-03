(() => {
  let context = null;
  let transaction = null;
  let transactionPoll = 0;
  const egressState = {byAccessFamily:{}};
  const $ = (id) => document.getElementById(id);
  const endpointSelect = () => $('endpoint-select') || $('wan-select');
  const secondaryEndpointSelect = () => $('access-ipv6-select');
  const egressModeRoot = () => $('egress-mode-segment');
  const egressWanSelect = (family) => $(`egress-${family}-select`);
  const zh = () => document.documentElement.dataset.lang === 'zh';

  function data() { return context?.getData?.() || {}; }
  function inventoryWans() { return Array.isArray(data()?.inventory?.wans) ? data().inventory.wans : []; }
  function agentFresh(currentData = data()) { return Boolean(context?.state?.dashboardAvailable && currentData?.agent?.fresh); }
  function staleCloseRecommended(currentData = data()) { return !agentFresh(currentData) && Boolean(currentData?.agent?.may_have_active_runtime); }

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

  function endpointMethod(item) {
    const accessMethod = String(item?.access_method || '');
    if (['direct','mapped','relay'].includes(accessMethod)) return accessMethod;
    const reachability = String(item?.reachability || '');
    if (['direct','mapped','relay','egress_probe'].includes(reachability)) return reachability;
    return item?.provider === 'egress_probe' ? 'egress_probe' : '';
  }

  function accessRole(item) {
    if (item?.access_method === 'mapped' || item?.reachability === 'mapped') return 'Mapped';
    if (item?.access_method === 'relay' || item?.reachability === 'relay') return 'Relay';
    if (item?.provider === 'egress_probe' || item?.reachability === 'egress_probe') return 'Try';
    return item?.family === 'ipv6' ? 'Global Direct' : 'Public Direct';
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

  function preferredSelection(family) {
    if (family === 'ipv4') return preferredIpv4Endpoint()?.id || '';
    if (family === 'ipv6') return preferredIpv6Endpoint()?.id || '';
    return '';
  }

  function primaryAccessFamily() {
    const mode = context?.state?.family;
    return mode === 'dual' ? 'ipv4' : (['ipv4','ipv6'].includes(mode) ? mode : 'ipv4');
  }

  function accessEndpointSelect(family) {
    if (!['ipv4','ipv6'].includes(family)) return null;
    if (family === primaryAccessFamily()) return endpointSelect();
    if (context?.state?.family === 'dual' && family === 'ipv6') return secondaryEndpointSelect();
    return null;
  }

  function accessEndpointSelectId(family) {
    return accessEndpointSelect(family)?.id || '';
  }

  function endpointForSelection(family, value) {
    if (!['ipv4','ipv6'].includes(family) || !value) return null;
    return endpointsFor(family).find((item) => item.id === value) || null;
  }

  function endpointWanForSelection(family, value) {
    return String(endpointForSelection(family, value)?.wan || '');
  }

  function endpointMethodForSelection(family, value) {
    return endpointMethod(endpointForSelection(family, value));
  }

  function endpointSelectionRecord(family, value) {
    return {
      value:String(value || ''),
      wan:endpointWanForSelection(family, value),
      method:endpointMethodForSelection(family, value)
    };
  }

  function selectedAccessWans() {
    const mode = context?.state?.family;
    if (mode === 'dual') {
      return {
        ipv4:endpointWanForSelection('ipv4', String(accessEndpointSelect('ipv4')?.value || '')),
        ipv6:endpointWanForSelection('ipv6', String(accessEndpointSelect('ipv6')?.value || ''))
      };
    }
    if (mode === 'ipv6') return {ipv4:'', ipv6:endpointWanForSelection('ipv6', String(endpointSelect()?.value || ''))};
    if (mode === 'ipv4') return {ipv4:endpointWanForSelection('ipv4', String(endpointSelect()?.value || '')), ipv6:''};
    return {ipv4:'', ipv6:''};
  }

  function endpointSelectionIsManual(family) {
    return Boolean(['ipv4','ipv6'].includes(family) && context?.state?.endpointManualSelections?.[family]);
  }

  function publishEndpointSelection(family, select = accessEndpointSelect(family)) {
    if (!['ipv4','ipv6'].includes(family)) return;
    const value = String(select?.value || '');
    const confirmed = Boolean(value);
    const source = endpointSelectionIsManual(family) ? 'manual' : 'auto';
    if (select) {
      select.dataset.selectionFamily = context?.state?.family === 'dual' ? 'dual' : family;
      select.dataset.selectionScalarFamily = family;
      select.dataset.selectionConfirmed = confirmed ? '1' : '0';
      select.dataset.selectionSource = confirmed ? source : '';
    }
    window.dispatchEvent(new CustomEvent('remote-gate-endpoint-selection', {detail: {family, value, confirmed, source}}));
  }

  function populateEndpointOptions(family, select) {
    if (!['ipv4','ipv6'].includes(family) || !select) return;
    const items = [...endpointsFor(family)].sort(endpointCompare);
    const preferred = preferredSelection(family);
    select.replaceChildren();
    if (!items.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = context?.t?.('common.unavailable') || 'Unavailable';
      select.append(option);
      select.disabled = true;
      return;
    }
    items.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.id;
      setPathRows(option, [pathRow(family, item.wan, accessRole(item), endpointAddress(item))], item.id === preferred);
      option.textContent = `${item.wan} · ${family === 'ipv6' ? 'IPv6' : 'IPv4'} · ${accessRole(item)} · ${endpointAddress(item)}`;
      select.append(option);
    });
    select.disabled = false;
  }

  function recentTerminalFailure(last) {
    if (!last || !['failed','expired'].includes(String(last.state || ''))) return false;
    const terminalAt = Number(last.acked_at || last.expires_at || last.created_at || 0);
    if (!terminalAt) return false;
    return Math.max(0, Math.floor(Date.now() / 1000) - terminalAt) <= 120;
  }

  function rememberFamilyEndpointSelection(family) {
    if (!context || !['ipv4','ipv6'].includes(family) || !endpointSelectionIsManual(family)) return;
    const select = accessEndpointSelect(family);
    const value = String(select?.value || '');
    if (!value) { publishEndpointSelection(family, select); return; }
    if (!context.state.endpointSelections || typeof context.state.endpointSelections !== 'object') context.state.endpointSelections = {};
    context.state.endpointSelections[family] = endpointSelectionRecord(family, value);
    publishEndpointSelection(family, select);
  }

  function rememberEndpointSelection(mode = context?.state?.family) {
    if (mode === 'dual') {
      rememberFamilyEndpointSelection('ipv4');
      rememberFamilyEndpointSelection('ipv6');
      return;
    }
    if (['ipv4','ipv6'].includes(mode)) rememberFamilyEndpointSelection(mode);
  }

  function restoreEndpointSelection(family, select = accessEndpointSelect(family)) {
    if (!context || !['ipv4','ipv6'].includes(family) || !select) return;
    populateEndpointOptions(family, select);
    const saved = context.state.endpointSelections?.[family];
    const options = [...select.options].filter((option) => option.value);
    if (!options.length) {
      publishEndpointSelection(family, select);
      window.RemoteGateEndpointPicker?.sync?.(select.id);
      return;
    }
    if (endpointSelectionIsManual(family) && saved) {
      const exact = options.find((option) => option.value === saved.value);
      if (exact) {
        select.value = exact.value;
        context.state.endpointSelections[family] = endpointSelectionRecord(family, exact.value);
        publishEndpointSelection(family, select);
        window.RemoteGateEndpointPicker?.sync?.(select.id);
        return;
      }
      const fallback = saved.wan ? options.find((option) => {
        if (endpointWanForSelection(family, option.value) !== saved.wan) return false;
        if (!saved.method) return true;
        return endpointMethodForSelection(family, option.value) === saved.method;
      }) : null;
      if (fallback) {
        select.value = fallback.value;
        context.state.endpointSelections[family] = endpointSelectionRecord(family, fallback.value);
        publishEndpointSelection(family, select);
        window.RemoteGateEndpointPicker?.sync?.(select.id);
        return;
      }
      context.state.endpointManualSelections[family] = false;
      delete context.state.endpointSelections[family];
    }
    const preferred = preferredSelection(family);
    select.value = options.some((option) => option.value === preferred) ? preferred : options[0].value;
    publishEndpointSelection(family, select);
    window.RemoteGateEndpointPicker?.sync?.(select.id);
  }

  function ensureAccessEndpointControl() {
    const endpoint = endpointSelect();
    if (!endpoint) return null;
    window.RemoteGateEndpointPicker?.bindSelect?.('endpoint-select');
    let field = endpoint.closest('.access-endpoint-control');
    if (field) return field.querySelector('.access-family-selectors');
    field = endpoint.closest('.field');
    if (!field) return null;
    field.classList.add('access-endpoint-control');

    const selectors = document.createElement('div');
    selectors.className = 'family-selectors access-family-selectors';

    const primary = document.createElement('div');
    primary.className = 'field compact-field';
    primary.dataset.accessSlot = 'primary';
    const primaryTrigger = $('endpoint-picker-trigger');
    primary.append(endpoint);
    if (primaryTrigger) primary.append(primaryTrigger);

    const secondary = document.createElement('div');
    secondary.className = 'field compact-field';
    secondary.dataset.accessSlot = 'secondary';
    secondary.dataset.accessFamily = 'ipv6';
    const select6 = document.createElement('select');
    select6.id = 'access-ipv6-select';
    select6.setAttribute('aria-label', 'IPv6 Access Endpoint');
    secondary.append(select6);

    selectors.append(primary, secondary);
    const heading = field.querySelector(':scope > span');
    if (heading) heading.insertAdjacentElement('afterend', selectors); else field.append(selectors);

    window.RemoteGateEndpointPicker?.bindSelect?.('access-ipv6-select', {
      eyebrow:'ACCESS ENDPOINT',
      title:() => zh() ? '选择 IPv6 访问路径' : 'Choose IPv6 access endpoint',
      empty:() => zh() ? '当前没有可用 IPv6 访问路径。' : 'No IPv6 access endpoint is currently available.'
    });
    return selectors;
  }

  function syncEndpointSelect(mode = context?.state?.family) {
    if (!context || !['ipv4','ipv6','dual'].includes(mode)) return;
    const selectors = ensureAccessEndpointControl();
    const primary = selectors?.querySelector('[data-access-slot="primary"]');
    const secondary = selectors?.querySelector('[data-access-slot="secondary"]');
    const primaryFamily = mode === 'dual' ? 'ipv4' : mode;
    if (primary) {
      primary.dataset.accessFamily = primaryFamily;
      primary.hidden = false;
    }
    if (secondary) secondary.hidden = mode !== 'dual';
    const main = endpointSelect();
    if (main) main.setAttribute('aria-label', primaryFamily === 'ipv6' ? 'IPv6 Access Endpoint' : 'IPv4 Access Endpoint');
    restoreEndpointSelection(primaryFamily, main);
    if (mode === 'dual') restoreEndpointSelection('ipv6', secondaryEndpointSelect());
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

  function egressCandidates(family = 'ipv4') {
    if (!['ipv4','ipv6'].includes(family)) return [];
    return inventoryWans()
      .filter((wan) => wanSupportsEgress(wan, family))
      .map((wan) => ({wan, family, address:egressAddress(wan, family), score:egressScore(wan, family)}))
      .sort((a, b) => a.score - b.score || String(a.wan.name).localeCompare(String(b.wan.name)));
  }

  function preferredSharedEgressWan() {
    const v4 = egressCandidates('ipv4');
    const v6ByWan = new Map(egressCandidates('ipv6').map((item) => [item.wan.name, item]));
    const shared = v4
      .filter((item) => v6ByWan.has(item.wan.name))
      .map((item) => ({name:item.wan.name, score:item.score + Number(v6ByWan.get(item.wan.name)?.score || 0)}))
      .sort((a,b) => a.score - b.score || a.name.localeCompare(b.name));
    return shared[0]?.name || '';
  }

  function preferredEgressWans() {
    const shared = preferredSharedEgressWan();
    if (shared) return {ipv4:shared, ipv6:shared};
    return {
      ipv4:String(egressCandidates('ipv4')[0]?.wan?.name || ''),
      ipv6:String(egressCandidates('ipv6')[0]?.wan?.name || '')
    };
  }

  function egressModeAvailable(mode) {
    if (mode === 'none') return true;
    const has4 = egressCandidates('ipv4').length > 0;
    const has6 = egressCandidates('ipv6').length > 0;
    if (mode === 'ipv4') return has4;
    if (mode === 'ipv6') return has6;
    if (mode === 'dual') return has4 && has6;
    return false;
  }

  function preferredEgressMode() {
    const family = context?.state?.family;
    const preferred = family === 'ipv6' ? 'ipv6' : family === 'dual' ? 'dual' : 'ipv4';
    if (egressModeAvailable(preferred)) return preferred;
    if (egressModeAvailable('ipv4')) return 'ipv4';
    if (egressModeAvailable('ipv6')) return 'ipv6';
    return 'none';
  }

  function egressPreference(accessFamily = context?.state?.family) {
    const key = ['ipv4','ipv6','dual'].includes(accessFamily) ? accessFamily : 'ipv4';
    if (!egressState.byAccessFamily[key]) {
      egressState.byAccessFamily[key] = {mode:'', ipv4:'', ipv6:'', manualMode:false, manualIpv4:false, manualIpv6:false};
    }
    return egressState.byAccessFamily[key];
  }

  function normalizeEgressPreference(accessFamily = context?.state?.family) {
    const preference = egressPreference(accessFamily);
    const defaults = preferredEgressWans();
    const valid4 = new Set(egressCandidates('ipv4').map((item) => item.wan.name));
    const valid6 = new Set(egressCandidates('ipv6').map((item) => item.wan.name));

    if (!preference.manualMode || !egressModeAvailable(preference.mode)) {
      preference.mode = preferredEgressMode();
      preference.manualMode = false;
    }
    if (!preference.manualIpv4 || !valid4.has(preference.ipv4)) {
      preference.ipv4 = defaults.ipv4;
      preference.manualIpv4 = false;
    }
    if (!preference.manualIpv6 || !valid6.has(preference.ipv6)) {
      preference.ipv6 = defaults.ipv6;
      preference.manualIpv6 = false;
    }
    if (preference.mode === 'ipv4' && !preference.ipv4) preference.mode = 'none';
    if (preference.mode === 'ipv6' && !preference.ipv6) preference.mode = 'none';
    if (preference.mode === 'dual' && (!preference.ipv4 || !preference.ipv6)) preference.mode = 'none';
    return preference;
  }

  function defaultEgressPlan(mode = preferredEgressMode()) {
    const defaults = preferredEgressWans();
    if (mode === 'ipv4') return {mode, ipv4:defaults.ipv4, ipv6:''};
    if (mode === 'ipv6') return {mode, ipv4:'', ipv6:defaults.ipv6};
    if (mode === 'dual') return {mode, ipv4:defaults.ipv4, ipv6:defaults.ipv6};
    return {mode:'none', ipv4:'', ipv6:''};
  }

  function populateEgressWanSelect(family, selectedWan, recommendedWan) {
    const select = egressWanSelect(family);
    if (!select) return;
    const items = egressCandidates(family);
    select.replaceChildren();
    if (!items.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = context?.t?.('common.unavailable') || 'Unavailable';
      select.append(option);
      select.disabled = true;
      window.RemoteGateEndpointPicker?.sync?.(select.id);
      return;
    }
    items.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.wan.name;
      option.dataset.egressFamily = family;
      setPathRows(option, [pathRow(family, item.wan.name, '', item.address)], item.wan.name === recommendedWan);
      option.textContent = `${item.wan.name} · ${family === 'ipv6' ? 'IPv6' : 'IPv4'} Internet Exit · ${item.address}`;
      select.append(option);
    });
    select.disabled = false;
    select.value = items.some((item) => item.wan.name === selectedWan) ? selectedWan : items[0].wan.name;
    window.RemoteGateEndpointPicker?.sync?.(select.id);
  }

  function ensureEgressControl() {
    let field = $('egress-control');
    if (field) return field;
    const endpoint = endpointSelect();
    const endpointField = document.querySelector('.access-endpoint-control') || endpoint?.closest?.('.field');
    if (!endpoint || !endpointField) return null;

    field = document.createElement('div');
    field.id = 'egress-control';
    field.className = 'field compact-field full-row';

    const label = document.createElement('span');
    label.dataset.egressLabel = '1';
    label.textContent = zh() ? '上网出口' : 'Internet Exit';

    const mode = document.createElement('div');
    mode.id = 'egress-mode-segment';
    mode.className = 'segment';
    mode.setAttribute('role', 'group');
    mode.setAttribute('aria-label', label.textContent);
    [
      ['none', zh() ? '本地网络' : 'LAN'],
      ['ipv4', 'IPv4'],
      ['ipv6', 'IPv6'],
      ['dual', 'Dual']
    ].forEach(([value, text]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.egressMode = value;
      button.setAttribute('aria-pressed', 'false');
      button.textContent = text;
      mode.append(button);
    });

    const selectors = document.createElement('div');
    selectors.className = 'family-selectors egress-family-selectors';
    ['ipv4','ipv6'].forEach((family) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'field compact-field';
      wrapper.dataset.egressFamily = family;
      const select = document.createElement('select');
      select.id = `egress-${family}-select`;
      select.setAttribute('aria-label', family === 'ipv6' ? 'IPv6 Internet Exit' : 'IPv4 Internet Exit');
      wrapper.append(select);
      selectors.append(wrapper);
    });

    field.append(label, mode, selectors);
    endpointField.insertAdjacentElement('afterend', field);

    window.RemoteGateEndpointPicker?.bindSelect?.('egress-ipv4-select', {
      eyebrow:'INTERNET EXIT',
      title:() => zh() ? '选择 IPv4 上网出口' : 'Choose IPv4 Internet exit',
      empty:() => zh() ? '当前没有可用 IPv4 出口。' : 'No IPv4 Internet exit is currently available.'
    });
    window.RemoteGateEndpointPicker?.bindSelect?.('egress-ipv6-select', {
      eyebrow:'INTERNET EXIT',
      title:() => zh() ? '选择 IPv6 上网出口' : 'Choose IPv6 Internet exit',
      empty:() => zh() ? '当前没有可用 IPv6 出口。' : 'No IPv6 Internet exit is currently available.'
    });
    return field;
  }

  function syncEgressControl() {
    if (!context) return;
    const field = ensureEgressControl();
    if (!field) return;
    const preference = normalizeEgressPreference();
    const defaults = preferredEgressWans();
    const label = field.querySelector('[data-egress-label]');
    if (label) label.textContent = zh() ? '上网出口' : 'Internet Exit';

    egressModeRoot()?.querySelectorAll('[data-egress-mode]').forEach((button) => {
      const mode = String(button.dataset.egressMode || 'none');
      const available = egressModeAvailable(mode);
      const active = mode === preference.mode;
      button.disabled = !available;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.setAttribute('aria-disabled', available ? 'false' : 'true');
      if (mode === 'none') button.textContent = zh() ? '本地网络' : 'LAN';
    });

    populateEgressWanSelect('ipv4', preference.ipv4, defaults.ipv4);
    populateEgressWanSelect('ipv6', preference.ipv6, defaults.ipv6);

    field.querySelectorAll('[data-egress-family]').forEach((wrapper) => {
      if (!(wrapper instanceof HTMLElement) || wrapper.tagName === 'OPTION') return;
      const family = wrapper.dataset.egressFamily;
      wrapper.hidden = !(
        preference.mode === 'dual' ||
        (preference.mode === 'ipv4' && family === 'ipv4') ||
        (preference.mode === 'ipv6' && family === 'ipv6')
      );
    });
  }

  function selectedEgressPlan() {
    const preference = normalizeEgressPreference();
    if (preference.mode === 'ipv4') return {mode:'ipv4', ipv4:preference.ipv4, ipv6:''};
    if (preference.mode === 'ipv6') return {mode:'ipv6', ipv4:'', ipv6:preference.ipv6};
    if (preference.mode === 'dual') return {mode:'dual', ipv4:preference.ipv4, ipv6:preference.ipv6};
    return {mode:'none', ipv4:'', ipv6:''};
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
    if (family === 'dual') return Boolean(
      gateCapability('ipv4') && gateCapability('ipv6') &&
      sourceFor('ipv4') && sourceFor('ipv6') &&
      endpointsFor('ipv4').length && endpointsFor('ipv6').length
    );
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
    if (!agentFresh()) return zh() ? 'OpenWrt Agent 状态不可用；Activate 已禁用，等待新的有效状态。' : 'OpenWrt Agent status is unavailable; Activate is disabled until a fresh report arrives.';
    if (family === 'dual') {
      if (!gateCapability('ipv4')) return zh() ? '此 OpenWrt 的 IPv4 Gate 已禁用。' : 'IPv4 Gate is disabled on this OpenWrt device.';
      if (!gateCapability('ipv6')) return t('gate.ipv6Unavailable');
      if (!endpointsFor('ipv4').length || !endpointsFor('ipv6').length) return zh() ? 'Dual 需要所选 WireGuard 服务同时存在可用的 IPv4 与 IPv6 Endpoint。' : 'Dual requires available IPv4 and IPv6 endpoints for the selected WireGuard service.';
      if (!sourceFor('ipv4') || !sourceFor('ipv6')) return zh() ? 'IPv4 与 IPv6 Source 都就绪后可同时授权。' : 'Both IPv4 and IPv6 sources are required for dual-stack authorization.';
      return '';
    }
    if (family === 'ipv4' && !gateCapability('ipv4')) return zh() ? '此 OpenWrt 的 IPv4 Gate 已禁用。' : 'IPv4 Gate is disabled on this OpenWrt device.';
    if (family === 'ipv6' && !gateCapability('ipv6')) return t('gate.ipv6Unavailable');
    const endpoints = endpointsFor(family);
    if (!endpoints.length) return t('gate.familyEndpointMissing', {family:family.toUpperCase()});
    const source = sourceFor(family);
    if (!source) return t('gate.familySourceMissing', {family:family.toUpperCase()});
    return '';
  }

  function notify(message, kind = 'info', options = {}) {
    if (window.RemoteGateFeedback?.notify) return window.RemoteGateFeedback.notify(message, kind, options);
    context?.toast?.(message, kind === 'error' ? 'error' : 'info');
    return null;
  }
  function requestError(code) {
    const value = String(code || 'request failed');
    if (value === 'gate_close_required') {
      return zh()
        ? '已有远程访问仍在运行。请先 Close，再切换协议族、WireGuard、WAN、入口或 Access Scope。'
        : 'Remote access is already active. Close it before switching family, WireGuard, WAN, ingress, or Access Scope.';
    }
    return value;
  }
  function pendingCommand(currentData = data()) { return currentData?.gate?.queue?.pending || null; }
  function closeCanPreempt(currentData = data()) { return pendingCommand(currentData)?.action === 'activate'; }
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
  function closeSupersedesTransaction(command) {
    if (!command || command.action !== 'close' || !transaction || transaction.action !== 'activate') return false;
    if (transaction.batchId) {
      return command.preempted_batch_id === transaction.batchId || command.rollback_for_batch === transaction.batchId;
    }
    return Boolean(transaction.commandId && command.preempted_command_id === transaction.commandId);
  }
  function adoptCloseTransaction(command) {
    transaction = {action:'close', commandId:String(command.id || ''), batchId:String(command.batch_id || ''), startedAt:Number(command.created_at || 0) * 1000 || Date.now(),serverOwned:true};
  }
  function syncTransaction(currentData) {
    const queue = currentData?.gate?.queue || {};
    const pending = queue.pending;
    const last = queue.last;
    if (pending && closeSupersedesTransaction(pending)) adoptCloseTransaction(pending);
    if (!pending && last && closeSupersedesTransaction(last)) adoptCloseTransaction(last);
    if (pending && !transaction) {
      transaction = {action:String(pending.action || 'activate'), commandId:String(pending.id || ''), batchId:String(pending.batch_id || ''), startedAt:Number(pending.created_at || 0) * 1000 || Date.now(),serverOwned:true};
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

  function canActivate() {
    if (!context || transactionLocked() || !agentFresh()) return false;
    const state = context.state;
    const fw = data()?.agent?.firewall || {};
    const endpointReady = state.family === 'dual'
      ? Boolean(accessEndpointSelect('ipv4')?.value && accessEndpointSelect('ipv6')?.value)
      : Boolean(endpointSelect()?.value);
    if (hasActiveRuntime(fw)) return false;
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
    const note = $('family-note');
    if (note) {
      const reason = familyReason(state.family);
      note.textContent = reason;
      note.hidden = !reason;
    }
    if (previous !== state.family) context.onFamilyChange?.(state.family);
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
  function normalizedPort(value) {
    const port = Number(value || 0);
    return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : 0;
  }
  function endpointIngressPort(item) {
    const method = endpointMethod(item);
    const candidates = method === 'mapped'
      ? [item?.ingress_port, item?.local_port]
      : [item?.ingress_port, item?.service_port, item?.local_port, item?.external_port];
    for (const value of candidates) {
      const port = normalizedPort(value);
      if (port) return port;
    }
    return 0;
  }
  function selectedEndpointForFamily(family) {
    if (!['ipv4','ipv6'].includes(family)) return null;
    const mode = context?.state?.family;
    if (mode !== family && mode !== 'dual') return null;
    const select = accessEndpointSelect(family);
    const value = String(select?.value || '');
    return endpointsFor(family).find((item) => item.id === value) || null;
  }
  function selectedFamilyProfile(family) {
    const endpoint = selectedEndpointForFamily(family);
    if (!endpoint) return null;
    return {
      device:String(endpoint.device || ''),
      ingressPort:endpointIngressPort(endpoint),
      scope:String(context?.state?.scope || 'wg')
    };
  }
  function firewallFamilyProfile(fw, family) {
    const item = fw?.families?.[family] || {};
    const legacy = fw?.family === family ? fw : {};
    return {
      active:Boolean(item.active || legacy.active),
      device:String(item.device || legacy.device || ''),
      ingressPort:normalizedPort(item.ingress_port || item.wg_port || legacy.ingress_port || legacy.wg_port),
      scope:String(item.scope || legacy.scope || '')
    };
  }
  function activeProfileMatchesSelection(fw, family) {
    const runtime = firewallFamilyProfile(fw, family);
    const selected = selectedFamilyProfile(family);
    return Boolean(
      runtime.active && selected && runtime.device && selected.device &&
      runtime.device === selected.device && runtime.ingressPort > 0 && runtime.ingressPort === selected.ingressPort &&
      runtime.scope && runtime.scope === selected.scope
    );
  }
  function expectedRuntimeFamilies(family) {
    if (family === 'dual') return ['ipv4','ipv6'];
    return ['ipv4','ipv6'].includes(family) ? [family] : [];
  }
  function activeRuntimeFamilies(fw) {
    return ['ipv4','ipv6'].filter((family) => firewallFamilyProfile(fw, family).active);
  }
  function hasActiveRuntime(fw) { return activeRuntimeFamilies(fw).length > 0; }
  function partialDualRuntime(fw, family) {
    return family === 'dual' && activeRuntimeFamilies(fw).length === 1;
  }
  function activeFamilyState(fw, family) {
    const expected = expectedRuntimeFamilies(family);
    const active = activeRuntimeFamilies(fw);
    if (!expected.length || active.length !== expected.length || expected.some((item) => !active.includes(item))) return false;
    return expected.every((item) => sourceAuthorized(fw, item) && activeProfileMatchesSelection(fw, item));
  }
  function conflictingActiveRuntime(fw, family) {
    return hasActiveRuntime(fw) && !partialDualRuntime(fw, family) && !activeFamilyState(fw, family);
  }

  function setLockedControls(locked, action, active, activatable, currentData = data()) {
    const preemptible = locked && action === 'activate' && closeCanPreempt(currentData);
    const safeClose = !locked && staleCloseRecommended(currentData);
    const form = document.querySelector('.gate-form');
    if (form) {
      form.classList.toggle('transaction-locked', locked);
      form.inert = Boolean(locked && !preemptible);
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
      const showClose = locked ? (action === 'close' || preemptible) : (active || safeClose);
      closeButton.classList.toggle('hidden', !showClose);
      closeButton.disabled = (locked && !preemptible) || Boolean(context?.state?.busy);
      closeButton.classList.toggle('transaction-locked', locked && action === 'close');
      closeButton.setAttribute('aria-disabled', closeButton.disabled ? 'true' : 'false');
    }
  }

  function render(currentData = data()) {
    if (!context) return;
    const state = context.state, t = context.t, remaining = context.remaining;
    syncFamily(); syncScope();
    syncEndpointSelect(state.family);
    syncEgressControl();
    const locked = syncTransaction(currentData);
    const pending = currentData?.gate?.queue?.pending, next = currentData?.gate?.queue?.next, last = currentData?.gate?.queue?.last;
    const fresh = agentFresh(currentData), safeClose = staleCloseRecommended(currentData);
    const fw = fresh ? (currentData?.agent?.firewall || {}) : {};
    const active = activeFamilyState(fw, state.family), partialActive = partialDualRuntime(fw, state.family), activeConflict = conflictingActiveRuntime(fw, state.family), closeRequired = hasActiveRuntime(fw), pendingAction = pending?.action, orb = $('gate-orb');
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
    } else if (partialActive) {
      mode='open';
      title=zh() ? 'OPEN · 部分访问' : 'OPEN · PARTIAL ACCESS';
      subtitle=zh() ? 'Dual 只剩一个协议族的 Gate 授权。请先 Close 清理实际运行态，再重新 Activate。' : 'Only one family of the selected Dual Gate remains active. Close the actual runtime before activating again.';
      badge=zh() ? '部分开启' : 'PARTIAL OPEN';
    } else if (activeConflict) {
      mode='open';
      title=zh() ? 'OPEN · 其它访问路径' : 'OPEN · OTHER ACCESS PATH';
      subtitle=zh() ? '现有 Gate 授权与当前 Source 或 Access profile 不一致。请先 Close，再切换协议族、WireGuard、WAN、入口或 Access Scope。' : 'An active Gate authorization does not match the current source or Access profile. Close it before switching family, WireGuard, WAN, ingress, or Access Scope.';
      badge=zh() ? '其它路径已开启' : 'OPEN ELSEWHERE';
    } else if (!fresh) {
      mode='closed';
      title=zh() ? '状态未知' : 'STATUS UNKNOWN';
      subtitle=safeClose ? (zh() ? 'OpenWrt Agent 状态不可用；不会把旧状态视为 OPEN。上次报告仍可能存在 Gate/Internet 出口，可使用 Close 安全清理。' : 'OpenWrt Agent status is unavailable. Cached state is not treated as OPEN; the last report may still have Gate/Internet runtime, so Close remains available for safe cleanup.') : (zh() ? 'OpenWrt Agent 状态不可用；Activate 已禁用，等待新的有效状态。' : 'OpenWrt Agent status is unavailable. Activate is disabled until a fresh report arrives.');
      badge=zh() ? '未知' : 'UNKNOWN';
    } else if (recentTerminalFailure(last)) {
      mode='error'; title=t('gate.error'); subtitle=last.detail || (last.state === 'expired' ? (zh() ? '请求已过期。' : 'The request expired.') : t('gate.agentFailed')); badge=t('gate.errorBadge');
    }
    const activatable=canActivate(), action=lockAction(currentData);
    if (orb) {
      const orbLabel = closeRequired ? t('gate.close') : t('gate.activate');
      const orbEnabled = !locked && (closeRequired ? !state.busy : (mode === 'closed' && activatable));
      orb.dataset.state=mode; orb.dataset.hint=orbLabel; orb.disabled=!orbEnabled;
      orb.classList.toggle('transaction-locked', locked);
      orb.setAttribute('aria-disabled', orb.disabled ? 'true':'false');
      orb.setAttribute('aria-label', locked ? lockMessage(currentData) : (orbEnabled ? orbLabel : familyReason(state.family)));
      orb.title=locked ? lockMessage(currentData) : (orbEnabled ? orbLabel : familyReason(state.family));
    }
    if ($('gate-state')) $('gate-state').textContent=title;
    if ($('gate-substate')) $('gate-substate').textContent=subtitle;
    if ($('gate-state-badge')) $('gate-state-badge').textContent=badge;
    if ($('gate-lock')) $('gate-lock').textContent=closeRequired?'◇':'◆';
    const trustNote=document.querySelector('.trust-note');
    if (trustNote) trustNote.textContent=zh() ? 'Cloudflare HTTP 观察和运营商 Candidate 是当前登录 Session 的来源依据；点击 Activate 后由 VPS 解析所选协议族，OpenWrt 直接应用临时授权，不要求 WireGuard 预先握手。' : 'Cloudflare HTTP observations and carrier candidates are source evidence for the signed-in session. Activate resolves the selected family server-side and OpenWrt applies the temporary authorization without requiring a pre-existing WireGuard handshake.';
    const authorizationSource=$('authorization-source');
    if (authorizationSource) {
      if (state.family === 'dual') {
        const values=['ipv4','ipv6'].filter((family)=>sourceAuthorized(fw,family)).map((family)=>sourceFor(family)).filter(Boolean);
        authorizationSource.textContent=values.length?values.join(' · '):(sourceFor('ipv4')||sourceFor('ipv6')||t('common.unavailable'));
      } else authorizationSource.textContent=sourceFor(state.family)||t('common.unavailable');
    }
    setLockedControls(locked, action, closeRequired, activatable, currentData);
  }

  async function submit(path, body, action) {
    if (!context) return;
    const preemptingClose = action === 'close' && closeCanPreempt();
    if (transactionLocked() && !preemptingClose) { notify(lockMessage(), 'info', {title:zh() ? '操作进行中' : 'Operation in progress'}); return; }
    transaction={action,commandId:'',batchId:'',startedAt:Date.now(),serverOwned:false};
    startTransactionPoll(); context.state.busy=true; render(data());
    let errorCode='';
    try {
      const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':context.state.csrf},body:JSON.stringify(body||{})});
      const payload=response.status===204?{}:await response.json().catch(()=>({}));
      if(!response.ok) {
        errorCode=String(payload?.error||`HTTP ${response.status}`);
        throw new Error(requestError(errorCode));
      }
      transaction.commandId=String(payload?.command_id||''); transaction.batchId=String(payload?.batch_id||'');
      notify(action==='close'?(zh()?'关闭请求已提交，正在等待 OpenWrt 确认。':'Close request submitted; waiting for OpenWrt confirmation.'):(zh()?'激活请求已提交，正在等待 OpenWrt 应用授权。':'Activation submitted; waiting for OpenWrt to apply the authorization.'),'info',{title:zh()?'处理中':'In progress'});
      window.RemoteGateApp?.refresh?.();
    } catch(error) {
      notify(String(error?.message||error||'request failed'),'error',{title:zh()?'请求失败':'Request failed',duration:5200});
      clearTransaction();
      if(errorCode==='gate_close_required') window.RemoteGateApp?.refresh?.();
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
      const ipv4=String(accessEndpointSelect('ipv4')?.value||'');
      const ipv6=String(accessEndpointSelect('ipv6')?.value||'');
      if(!ipv4||!ipv6)return;
      submit('/api/v1/gate/activate',{families:['ipv4','ipv6'],endpoint_ids:{ipv4,ipv6},...egressBody,scope:state.scope||'wg',ttl:state.ttl},'activate');
      return;
    }
    submit('/api/v1/gate/activate',{endpoint_id:endpointSelect().value,family:state.family,...egressBody,scope:state.scope||'wg',ttl:state.ttl},'activate');
  }
  function closeAccess() { submit('/api/v1/gate/close',{},'close'); }
  function toggleAccess() {
    if (!context || transactionLocked()) return;
    const fw=data()?.agent?.firewall||{};
    if(agentFresh()&&hasActiveRuntime(fw)) closeAccess(); else activate();
  }
  function guardedTarget(target) { return target?.closest?.('.gate-form button, .gate-form select, .gate-form input, #gate-orb'); }
  function transactionGuard(event) {
    const target=guardedTarget(event.target);
    if(!transactionLocked()||!target)return;
    if(closeCanPreempt()&&target.id==='close-button')return;
    event.preventDefault(); event.stopImmediatePropagation(); notify(lockMessage(),'info',{title:zh()?'操作进行中':'Operation in progress'});
  }

  function bind(nextContext) {
    context=nextContext;
    const state=context.state;
    if(!state.scope)state.scope='wg';
    if(!state.endpointSelections||typeof state.endpointSelections!=='object')state.endpointSelections={};
    if(!state.endpointManualSelections||typeof state.endpointManualSelections!=='object')state.endpointManualSelections={};
    if(typeof state.familyManual!=='boolean')state.familyManual=false;
    ensureDualButton(); ensureAccessEndpointControl(); ensureEgressControl(); syncEgressControl();
    const gateCard=document.querySelector('.gate-card');
    gateCard?.addEventListener('pointerdown',transactionGuard,true); gateCard?.addEventListener('click',transactionGuard,true); gateCard?.addEventListener('change',transactionGuard,true);
    $('ttl-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-ttl]');if(!button||transactionLocked())return;state.ttl=Number(button.dataset.ttl);$('ttl-segment').querySelectorAll('button').forEach((item)=>{item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',item===button?'true':'false');});});
    $('family-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-family]');if(!button||button.disabled||transactionLocked()||!familySelectable(button.dataset.family))return;rememberEndpointSelection(state.family);state.familyManual=true;state.family=button.dataset.family;context.onFamilyChange?.(state.family);render();});
    $('scope-segment')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-scope]');if(!button||transactionLocked()||!['wg','wg_ping'].includes(button.dataset.scope))return;state.scope=button.dataset.scope;syncScope();});
    endpointSelect()?.addEventListener('change',()=>{if(transactionLocked())return;const family=primaryAccessFamily();const select=endpointSelect();state.endpointManualSelections[family]=Boolean(select?.value);if(!select?.value)delete state.endpointSelections[family];rememberFamilyEndpointSelection(family);publishEndpointSelection(family,select);render();});
    secondaryEndpointSelect()?.addEventListener('change',()=>{if(transactionLocked()||state.family!=='dual')return;const family='ipv6';const select=secondaryEndpointSelect();state.endpointManualSelections[family]=Boolean(select?.value);if(!select?.value)delete state.endpointSelections[family];rememberFamilyEndpointSelection(family);publishEndpointSelection(family,select);render();});
    egressModeRoot()?.addEventListener('click',(event)=>{const button=event.target.closest('[data-egress-mode]');if(!button||button.disabled||transactionLocked())return;const preference=egressPreference();preference.mode=String(button.dataset.egressMode||'none');preference.manualMode=true;syncEgressControl();render();});
    ['ipv4','ipv6'].forEach((family)=>egressWanSelect(family)?.addEventListener('change',()=>{if(transactionLocked())return;const preference=egressPreference();preference[family]=String(egressWanSelect(family)?.value||'');preference[family==='ipv4'?'manualIpv4':'manualIpv6']=true;render();}));
    $('wg-select')?.addEventListener('change',()=>{if(transactionLocked())return;context.onWireGuardChange?.();render();});
    $('activate-button')?.addEventListener('click',activate); $('gate-orb')?.addEventListener('click',toggleAccess); $('close-button')?.addEventListener('click',closeAccess);
    window.addEventListener('remote-gate-language',()=>render());
  }

  window.RemoteGateGateControls={
    bind,render,canActivate,activate,toggleAccess,familyAvailable,familySelectable,transactionLocked,
    egressCandidates,preferredSharedEgressWan,preferredEgressWans,defaultEgressPlan,selectedEgressWan,selectedEgressPlan,reportedEgress,egressMatchesSelection,
    endpointSelectionIsManual,rememberEndpointSelection,restoreEndpointSelection,syncEndpointSelect,preferredIpv4Endpoint,preferredIpv6Endpoint,preferredSelection,selectedAccessWans
  };
})();
