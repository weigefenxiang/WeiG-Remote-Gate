(() => {
  const $ = (id) => document.getElementById(id);
  const t = (key, params) => window.RemoteGateI18n?.t(key, params) || key;
  const state = {
    data: null,
    csrf: '',
    ttl: 300,
    busy: false,
    dashboardAvailable: false,
    family: '',
    scope: 'wg',
    requestFamily: 'unknown',
    egressSelections: {},
    get egressWan() {
      return this.egressSelections[this.family] || '__lan__';
    },
    set egressWan(value) {
      if (['ipv4', 'ipv6', 'dual'].includes(this.family)) this.egressSelections[this.family] = String(value || '__lan__');
    }
  };

  function toast(message, kind = 'info') {
    const el = $('toast');
    if (!el) return;
    el.textContent = message;
    el.dataset.kind = kind;
    el.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove('show'), 2800);
  }

  function fmtBytes(value) {
    const n = Number(value || 0);
    if (!n) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = n;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function age(epoch) {
    const ts = Number(epoch || 0);
    if (!ts) return t('common.never');
    const seconds = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (seconds < 10) return t('common.justNow');
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  }

  function remaining(seconds) {
    const n = Math.max(0, Number(seconds || 0));
    if (!n) return '—';
    const m = Math.floor(n / 60);
    const s = Math.floor(n % 60);
    return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
  }

  function ipFamily(value) {
    const ip = String(value || '').trim();
    if (!ip) return 'unknown';
    return ip.includes(':') ? 'ipv6' : (ip.includes('.') ? 'ipv4' : 'unknown');
  }

  function wireguards(data) {
    return Array.isArray(data?.agent?.wireguard) ? data.agent.wireguard : [];
  }

  function sourceRecord(data, family) {
    const record = data?.client_sources?.[family];
    return record && record.address ? record : null;
  }

  function syncSelect(select, items, valueFn, labelFn) {
    if (!select) return;
    const prior = select.value;
    select.replaceChildren();
    if (!items.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = t('common.unavailable');
      select.append(option);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    items.forEach((item) => {
      const option = document.createElement('option');
      option.value = valueFn(item);
      option.textContent = labelFn(item);
      select.append(option);
    });
    if (items.some((item) => valueFn(item) === prior)) select.value = prior;
  }

  function syncWireGuardSelect(data) {
    syncSelect($('wg-select'), wireguards(data), (item) => item.name, (item) => `${item.name} · UDP ${item.listen_port}`);
  }

  function sourceDiagnostic(family) {
    return window.RemoteGateClientSources?.diagnostics?.()?.[family] || {status: 'idle', detail: '', address: ''};
  }

  function sourceMeta(record, family) {
    const zh = document.documentElement.dataset.lang === 'zh';
    const diagnostic = sourceDiagnostic(family);
    if (record) {
      const label = record.confidence === 'candidate'
        ? (zh ? '运营商 Candidate' : 'Carrier candidate')
        : (zh ? 'Cloudflare HTTP 观察' : 'Cloudflare HTTP observed');
      const suffix = ['echo_error', 'candidate_error', 'dashboard_error'].includes(diagnostic.status)
        ? ` · ${zh ? 'Probe 失败' : 'Probe failed'}: ${diagnostic.detail}`
        : '';
      return `${label} · ${age(record.observed_at)}${suffix}`;
    }
    const messages = {
      probing: zh ? '正在探测…' : 'Detecting…',
      echo_ok: zh ? `IP Echo 成功 · ${diagnostic.address}` : `IP echo OK · ${diagnostic.address}`,
      saved: zh ? `Candidate 已保存 · ${diagnostic.address}` : `Candidate saved · ${diagnostic.address}`,
      echo_error: zh ? `IP Echo 失败 · ${diagnostic.detail}` : `IP echo failed · ${diagnostic.detail}`,
      candidate_error: zh ? `Candidate 失败 · ${diagnostic.detail}` : `Candidate failed · ${diagnostic.detail}`,
      dashboard_error: zh ? `探测初始化失败 · ${diagnostic.detail}` : `Probe setup failed · ${diagnostic.detail}`
    };
    return messages[diagnostic.status] || t('common.notObserved');
  }

  function renderClient(data) {
    state.requestFamily = data?.request_family || ipFamily(data?.client_ip);
    const v4 = sourceRecord(data, 'ipv4');
    const v6 = sourceRecord(data, 'ipv6');
    const zh = document.documentElement.dataset.lang === 'zh';

    if ($('client-ipv4')) $('client-ipv4').textContent = v4?.address || t('common.notObserved');
    if ($('client-ipv6')) $('client-ipv6').textContent = v6?.address || t('common.notObserved');
    if ($('client-ipv4-meta')) {
      $('client-ipv4-meta').textContent = sourceMeta(v4, 'ipv4');
      $('client-ipv4-meta').title = sourceDiagnostic('ipv4').detail || '';
    }
    if ($('client-ipv6-meta')) {
      $('client-ipv6-meta').textContent = sourceMeta(v6, 'ipv6');
      $('client-ipv6-meta').title = sourceDiagnostic('ipv6').detail || '';
    }

    const trustNote = document.querySelector('.trust-note');
    if (trustNote) {
      trustNote.textContent = zh
        ? 'Cloudflare HTTP 观察和运营商 Candidate 用于识别当前 Session 的客户端来源；点击 Activate 后由 VPS 解析所选协议族，OpenWrt 直接应用临时授权，不要求 WireGuard 预先握手。'
        : 'Cloudflare HTTP observations and carrier candidates identify the current session source. Activate resolves the selected family on the VPS and OpenWrt applies the temporary authorization without requiring a pre-existing WireGuard handshake.';
    }

    const requestLabel = state.requestFamily === 'ipv4' ? 'IPv4' : state.requestFamily === 'ipv6' ? 'IPv6' : '—';
    if ($('request-family')) $('request-family').textContent = requestLabel;
    if ($('system-request-family')) $('system-request-family').textContent = requestLabel;

    const fw = data?.agent?.firewall || {};
    const selectedSource = sourceRecord(data, state.family)?.address || '';
    const activeSource = fw.active ? String(fw.source_ip || '') : '';
    if ($('authorization-source')) $('authorization-source').textContent = activeSource || selectedSource || t('common.unavailable');
    window.RemoteGateFit?.observe();
  }

  function renderFirewall(data) {
    const fw = data?.agent?.firewall || {};
    const active = Boolean(fw.active);
    const pingOpen = active && fw.scope === 'wg_ping';
    if ($('icmp-state')) $('icmp-state').textContent = pingOpen ? 'ALLOW' : 'DROP';
    if ($('udp-state')) $('udp-state').textContent = active ? `ALLOW · UDP ${fw.wg_port || 'WG'}` : 'DROP';
    if ($('fw-source')) $('fw-source').textContent = active ? (fw.source_ip || '—') : '—';
    if ($('fw-expires')) $('fw-expires').textContent = active ? remaining(fw.expires_in) : '—';
  }

  function selectedWireGuard(data) {
    const selected = $('wg-select')?.value || '';
    const list = wireguards(data);
    return list.find((item) => item.name === selected) || list[0] || null;
  }

  function renderWireGuard(data) {
    const wg = selectedWireGuard(data);
    if (!wg) {
      if ($('wg-name')) $('wg-name').textContent = t('common.unavailable');
      if ($('wg-port')) $('wg-port').textContent = '—';
      if ($('wg-handshake')) $('wg-handshake').textContent = t('common.never');
      if ($('wg-traffic')) $('wg-traffic').textContent = '—';
      if ($('wg-status')) $('wg-status').textContent = t('common.unavailable');
      if ($('wg-dot')) $('wg-dot').className = 'status-dot neutral';
      return;
    }

    const handshake = Number(wg.latest_handshake || 0);
    const recent = handshake > 0 && (Date.now() / 1000 - handshake) < 180;
    const gateActive = Boolean(data?.agent?.firewall?.active);
    if ($('wg-name')) $('wg-name').textContent = wg.name;
    if ($('wg-port')) $('wg-port').textContent = `UDP ${wg.listen_port}`;
    if ($('wg-handshake')) $('wg-handshake').textContent = age(handshake);
    if ($('wg-traffic')) $('wg-traffic').textContent = `${fmtBytes(wg.rx)} ↓ · ${fmtBytes(wg.tx)} ↑`;
    if ($('wg-status')) $('wg-status').textContent = recent
      ? t('wg.connected')
      : gateActive
        ? t('wg.listening')
        : `${t('wg.protected')} · ${t('wg.noHandshake')}`;
    if ($('wg-dot')) $('wg-dot').className = `status-dot ${recent ? 'success' : 'neutral'}`;
  }

  function addressEntryLabel(entry, family) {
    const kind = String(entry?.kind || '');
    if (family === 'ipv4') return kind === 'public' ? t('wan.direct') : t('wan.private');
    return kind === 'global' ? t('wan.direct') : t('wan.nonGlobal');
  }

  function renderAddressLine(container, entry, family) {
    const address = String(entry?.address || '');
    const row = document.createElement('div');
    row.className = 'wan-address-row';

    const label = document.createElement('span');
    label.className = 'wan-address-family';
    label.textContent = family === 'ipv6' ? 'IPv6' : 'IPv4';

    const value = document.createElement('button');
    value.type = 'button';
    value.className = 'wan-address-copy fit-single-line';
    value.textContent = address;
    value.title = address;
    value.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(address);
        toast(t('toast.ipCopied'));
      } catch (_) {
        toast(t('toast.clipboardUnavailable'), 'error');
      }
    });

    const badge = document.createElement('span');
    badge.className = `endpoint-kind ${entry?.kind || ''}`;
    badge.textContent = addressEntryLabel(entry, family);

    row.append(label, value, badge);
    container.append(row);
  }

  function renderEgressLine(container, endpoint) {
    const address = String(endpoint?.external_address || '');
    if (!address) return;
    const row = document.createElement('div');
    row.className = 'wan-address-row';

    const label = document.createElement('span');
    label.className = 'wan-address-family';
    label.textContent = 'NAT IPv4';

    const value = document.createElement('button');
    value.type = 'button';
    value.className = 'wan-address-copy fit-single-line';
    value.textContent = address;
    value.title = address;
    value.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(address);
        toast(t('toast.ipCopied'));
      } catch (_) {
        toast(t('toast.clipboardUnavailable'), 'error');
      }
    });

    const badge = document.createElement('span');
    badge.className = 'endpoint-kind private';
    badge.textContent = document.documentElement.dataset.lang === 'zh' ? '出口 · 尝试' : 'Egress · Try';
    row.append(label, value, badge);
    container.append(row);
  }

  function renderWans(data) {
    const list = $('wan-list');
    if (!list) return;
    list.replaceChildren();
    const wans = Array.isArray(data?.inventory?.wans) ? data.inventory.wans : [];

    if (!wans.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = t('wan.noInterfaces');
      list.append(empty);
      return;
    }

    const endpointMap = new Map();
    (Array.isArray(data?.endpoints) ? data.endpoints : []).forEach((endpoint) => {
      if (!endpointMap.has(endpoint.wan)) endpointMap.set(endpoint.wan, []);
      endpointMap.get(endpoint.wan).push(endpoint);
    });

    const sorted = [...wans].sort((a, b) => {
      const score = (wan) => {
        const eps = endpointMap.get(wan.name) || [];
        if (eps.some((x) => x.family === 'ipv4' && x.reachability === 'direct')) return 0;
        if (eps.some((x) => x.family === 'ipv6' && x.reachability === 'direct')) return 1;
        if (eps.some((x) => x.reachability === 'mapped')) return 2;
        if (eps.some((x) => x.reachability === 'egress_probe')) return 3;
        if (eps.some((x) => x.reachability === 'private')) return 8;
        return 9;
      };
      return score(a) - score(b) || String(a.name).localeCompare(String(b.name));
    });

    sorted.forEach((wan) => {
      const card = document.createElement('div');
      card.className = 'wan-row';

      const top = document.createElement('div');
      top.className = 'wan-row-top';
      const identity = document.createElement('div');
      const eyebrow = document.createElement('span');
      eyebrow.className = 'eyebrow';
      eyebrow.textContent = t('wan.path');
      const title = document.createElement('h3');
      title.textContent = wan.name;
      identity.append(eyebrow, title);
      const badge = document.createElement('span');
      badge.className = `state-badge ${wan.up ? '' : 'muted-badge'}`;
      badge.textContent = wan.up ? t('wan.active') : t('wan.inactive');
      top.append(identity, badge);
      card.append(top);

      const addresses = document.createElement('div');
      addresses.className = 'wan-addresses';
      (Array.isArray(wan.ipv4) ? wan.ipv4 : []).forEach((entry) => renderAddressLine(addresses, entry, 'ipv4'));
      (Array.isArray(wan.ipv6) ? wan.ipv6 : []).forEach((entry) => renderAddressLine(addresses, entry, 'ipv6'));
      const seenEgress = new Set();
      (endpointMap.get(wan.name) || [])
        .filter((endpoint) => endpoint?.provider === 'egress_probe')
        .forEach((endpoint) => {
          if (seenEgress.has(endpoint.external_address)) return;
          seenEgress.add(endpoint.external_address);
          renderEgressLine(addresses, endpoint);
        });
      if (!addresses.children.length) {
        const empty = document.createElement('span');
        empty.className = 'muted small';
        empty.textContent = t('common.notObserved');
        addresses.append(empty);
      }
      card.append(addresses);

      const meta = document.createElement('div');
      meta.className = 'wan-meta';
      const device = document.createElement('span');
      device.textContent = wan.device || t('wan.unknownDevice');
      const routes = document.createElement('span');
      const flags = [];
      if (wan.default_route_v4) flags.push('IPv4 default');
      if (wan.default_route_v6) flags.push('IPv6 default');
      routes.textContent = flags.join(' · ') || t('wan.noDefaultRoute');
      meta.append(device, routes);
      card.append(meta);
      list.append(card);
    });

    if ($('wan-refresh')) $('wan-refresh').textContent = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  }

  function renderSystem(data) {
    const fresh = Boolean(data?.agent?.fresh);
    const current = Boolean(state.dashboardAvailable && fresh);
    const caps = data?.inventory?.capabilities || {};
    const transport = data?.agent?.transport || {};
    const firewall = data?.agent?.firewall || {};

    if ($('agent-state')) $('agent-state').textContent = current ? t('common.online') : t('common.waiting');
    if ($('system-dot')) $('system-dot').className = `status-dot ${current ? 'success' : 'neutral'}`;
    if ($('system-state')) $('system-state').textContent = current ? t('header.openwrtOnline') : t('header.controlPlaneOnline');
    if ($('system-ipv4-gate')) $('system-ipv4-gate').textContent = caps.gate_ipv4 === false ? t('common.disabled') : t('common.ready');
    if ($('system-ipv6-gate')) $('system-ipv6-gate').textContent = caps.gate_ipv6 ? t('common.ready') : t('common.disabled');
    if ($('system-firewall')) $('system-firewall').textContent = firewall.backend || t('common.unknown');
    if ($('system-transport')) {
      const family = transport.active_family === 'ipv6' ? 'IPv6' : transport.active_family === 'ipv4' ? 'IPv4' : '—';
      const device = transport.active_device || '';
      $('system-transport').textContent = device ? `${family} · ${device}${transport.healthy ? ' · OK' : ''}` : family;
    }
  }

  function render(data) {
    state.data = data;
    state.csrf = data.csrf || '';
    state.requestFamily = data.request_family || ipFamily(data.client_ip);
    if (!state.family) state.family = state.requestFamily === 'ipv6' ? 'ipv6' : 'ipv4';

    syncWireGuardSelect(data);
    renderClient(data);
    renderWireGuard(data);
    renderFirewall(data);
    renderWans(data);
    renderSystem(data);
    window.RemoteGateActivity?.render($('activity-list'), data?.activity, t);
    window.RemoteGateGateControls?.render(data);
    window.RemoteGateFit?.observe();
  }

  async function refresh() {
    try {
      const response = await fetch('/api/v1/dashboard', {cache: 'no-store', credentials: 'same-origin'});
      if (response.status === 401) {
        location.reload();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      state.dashboardAvailable = true;
      render(payload);
    } catch (_) {
      state.dashboardAvailable = false;
      if (state.data) window.RemoteGateGateControls?.render(state.data);
      if ($('system-state')) $('system-state').textContent = t('header.statusUnavailable');
      if ($('system-dot')) $('system-dot').className = 'status-dot danger';
    }
  }

  function friendlyError(code) {
    const map = {
      client_source_not_observed: 'toast.sourceNotObserved',
      ipv6_gate_unavailable: 'toast.ipv6Unavailable',
      endpoint_not_reachable: 'toast.endpointUnavailable',
      endpoint_required: 'toast.endpointUnavailable',
      agent_upgrade_required: 'toast.agentUpgradeRequired',
      endpoint_family_mismatch: 'toast.familyMismatch',
      source_family_mismatch: 'toast.familyMismatch',
      invalid_scope: 'toast.invalidScope'
    };
    return map[code] ? t(map[code]) : code;
  }

  async function post(path, body = {}) {
    if (state.busy) return;
    state.busy = true;
    window.RemoteGateGateControls?.render(state.data || {});

    try {
      const response = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf},
        body: JSON.stringify(body)
      });
      const payload = response.status === 204 ? {} : await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(friendlyError(payload.error || `HTTP ${response.status}`));
      toast(path.includes('close') ? t('toast.closeQueued') : t('toast.authQueued'));
      await refresh();
    } catch (error) {
      toast(String(error.message || error), 'error');
    } finally {
      state.busy = false;
      window.RemoteGateGateControls?.render(state.data || {});
    }
  }

  async function logout() {
    const response = await fetch('/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'X-CSRF-Token': state.csrf},
      redirect: 'follow'
    });
    location.href = response.url || '/';
  }

  window.RemoteGateGateControls?.bind({
    state,
    t,
    toast,
    post,
    remaining,
    getData: () => state.data,
    onFamilyChange: () => {
      if (!state.data) return;
      renderClient(state.data);
    },
    onWireGuardChange: () => {
      if (!state.data) return;
      renderWireGuard(state.data);
    }
  });

  document.querySelectorAll('[data-action="logout"]').forEach((button) => button.addEventListener('click', logout));
  window.addEventListener('remote-gate-language', () => {
    window.RemoteGateI18n?.apply();
    if (state.data) render(state.data);
  });
  window.addEventListener('remote-gate-client-source-diagnostics', () => {
    if (state.data) renderClient(state.data);
  });
  window.addEventListener('remote-gate-client-source-updated', () => refresh());
  $('workspace')?.addEventListener('workspacechange', () => requestAnimationFrame(() => window.RemoteGateFit?.observe()));

  window.RemoteGateApp = {refresh};
  refresh();
  setInterval(refresh, 5000);
})();
