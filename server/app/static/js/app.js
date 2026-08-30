(() => {
  const $ = (id) => document.getElementById(id);
  const t = (key, params) => window.RemoteGateI18n?.t(key, params) || key;
  const CLIENT_MEMORY_KEY = 'remote-gate:observed-client:v1';
  const state = {
    data: null,
    csrf: '',
    ttl: 300,
    busy: false,
    family: 'ipv4',
    requestFamily: 'unknown'
  };

  function toast(message, kind = 'info') {
    const el = $('toast');
    el.textContent = message;
    el.dataset.kind = kind;
    el.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove('show'), 2600);
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
    if (seconds < 10) return window.RemoteGateI18n?.language === 'zh' ? '刚刚' : 'Just now';
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

  function loadObserved() {
    try {
      const value = JSON.parse(localStorage.getItem(CLIENT_MEMORY_KEY) || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (_) {
      return {};
    }
  }

  function rememberObserved(ip) {
    const family = ipFamily(ip);
    const memory = loadObserved();
    if (family === 'ipv4' || family === 'ipv6') {
      memory[family] = {ip: String(ip), seenAt: Date.now()};
      localStorage.setItem(CLIENT_MEMORY_KEY, JSON.stringify(memory));
    }
    return memory;
  }

  function observedMeta(record, current) {
    if (!record?.ip) return t('common.notObserved');
    if (current) return t('client.currentRequest');
    const seconds = Math.max(0, Math.floor((Date.now() - Number(record.seenAt || 0)) / 1000));
    const value = seconds < 60
      ? `${seconds}s`
      : seconds < 3600
        ? `${Math.floor(seconds / 60)}m`
        : `${Math.floor(seconds / 3600)}h`;
    return `${t('client.browserObserved')} · ${value}`;
  }

  function publicWans(data) {
    const interfaces = data?.current?.interfaces || {};
    return Object.entries(interfaces)
      .filter(([, item]) => item && item.active && item.address_type === 'public')
      .map(([name, item]) => ({name, ...item}));
  }

  function wireguards(data) {
    return Array.isArray(data?.agent?.wireguard) ? data.agent.wireguard : [];
  }

  function syncSelect(select, items, labelFn) {
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
      option.value = item.name;
      option.textContent = labelFn(item);
      select.append(option);
    });

    if (items.some((item) => item.name === prior)) select.value = prior;
  }

  function renderClient(data) {
    const currentIp = String(data?.client_ip || '');
    state.requestFamily = ipFamily(currentIp);
    const memory = rememberObserved(currentIp);
    const v4 = state.requestFamily === 'ipv4' ? {ip: currentIp, seenAt: Date.now()} : memory.ipv4;
    const v6 = state.requestFamily === 'ipv6' ? {ip: currentIp, seenAt: Date.now()} : memory.ipv6;

    $('client-ipv4').textContent = v4?.ip || t('common.notObserved');
    $('client-ipv6').textContent = v6?.ip || t('common.notObserved');
    $('client-ipv4-meta').textContent = observedMeta(v4, state.requestFamily === 'ipv4');
    $('client-ipv6-meta').textContent = observedMeta(v6, state.requestFamily === 'ipv6');

    const requestLabel =
      state.requestFamily === 'ipv4' ? 'IPv4' :
      state.requestFamily === 'ipv6' ? 'IPv6' : '—';
    $('request-family').textContent = requestLabel;
    $('system-request-family').textContent = requestLabel;

    const verifiedSource = state.requestFamily === 'ipv4' ? currentIp : '';
    const activeSource = data?.agent?.firewall?.active
      ? String(data.agent.firewall.source_ip || '')
      : '';
    $('authorization-source').textContent = activeSource || verifiedSource || t('common.unavailable');

    window.RemoteGateFit?.observe();
  }

  function renderFirewall(data) {
    const fw = data?.agent?.firewall || {};
    const active = Boolean(fw.active);
    $('icmp-state').textContent = active ? 'ALLOW' : 'DROP';
    $('udp-state').textContent = active ? `ALLOW · ${fw.wg_port || 'WG'}` : 'DROP';
    $('fw-source').textContent = active ? (fw.source_ip || '—') : '—';
    $('fw-expires').textContent = active ? remaining(fw.expires_in) : '—';
  }

  function selectedWireGuard(data) {
    const selected = $('wg-select').value;
    const list = wireguards(data);
    return list.find((item) => item.name === selected) || list[0] || null;
  }

  function renderWireGuard(data) {
    const wg = selectedWireGuard(data);

    if (!wg) {
      $('wg-name').textContent = t('common.unavailable');
      $('wg-port').textContent = '—';
      $('wg-handshake').textContent = t('common.never');
      $('wg-traffic').textContent = '—';
      $('wg-status').textContent = t('common.unavailable');
      $('wg-dot').className = 'status-dot neutral';
      return;
    }

    const handshake = Number(wg.latest_handshake || 0);
    const recent = handshake > 0 && (Date.now() / 1000 - handshake) < 180;
    const gateActive = Boolean(data?.agent?.firewall?.active);

    $('wg-name').textContent = wg.name;
    $('wg-port').textContent = `UDP ${wg.listen_port}`;
    $('wg-handshake').textContent = age(handshake);
    $('wg-traffic').textContent = `${fmtBytes(wg.rx)} ↓ · ${fmtBytes(wg.tx)} ↑`;
    $('wg-status').textContent = recent
      ? t('wg.connected')
      : gateActive
        ? t('wg.listening')
        : `${t('wg.protected')} · ${t('wg.noHandshake')}`;
    $('wg-dot').className = `status-dot ${recent ? 'success' : 'neutral'}`;
  }

  function renderWans(data) {
    const list = $('wan-list');
    list.replaceChildren();

    const interfaces = Object.entries(data?.current?.interfaces || {})
      .map(([name, item]) => ({name, ...item}))
      .sort((a, b) => Number(b.active) - Number(a.active) || (a.address_type === 'public' ? -1 : 1));

    if (!interfaces.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = t('wan.noInterfaces');
      list.append(empty);
      return;
    }

    interfaces.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'wan-row';
      const publicWan = item.address_type === 'public';

      row.innerHTML = `
        <div class="wan-row-top">
          <div><span class="eyebrow"></span><h3></h3></div>
          <span class="state-badge ${item.active ? '' : 'muted-badge'}"></span>
        </div>
        <button type="button" class="ip-copy"><span></span><small></small></button>
        <div class="wan-meta"><span class="device"></span><span class="reported"></span></div>`;

      row.querySelector('.eyebrow').textContent = publicWan ? t('wan.public') : t('wan.private');
      row.querySelector('h3').textContent = item.name;
      row.querySelector('.state-badge').textContent = item.active ? t('wan.active') : t('wan.inactive');
      row.querySelector('.ip-copy span').textContent = item.ip || t('common.notObserved');
      row.querySelector('.ip-copy small').textContent = t('common.copy');
      row.querySelector('.device').textContent = item.device || t('wan.unknownDevice');
      row.querySelector('.reported').textContent = item.last_report_at
        ? t('wan.reported', {value: age(item.last_report_at)})
        : t('wan.neverReported');

      const copy = row.querySelector('.ip-copy');
      copy.disabled = !item.ip;
      copy.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(item.ip);
          toast(t('toast.ipCopied'));
        } catch (_) {
          toast(t('toast.clipboardUnavailable'), 'error');
        }
      });

      list.append(row);
    });

    $('wan-refresh').textContent = new Date().toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function renderSystem(data) {
    const reportedAt = Number(data?.agent?.reported_at || 0);
    const fresh = reportedAt && (Date.now() / 1000 - reportedAt) < 45;
    $('agent-state').textContent = fresh ? 'Online' : 'Waiting';
    $('system-dot').className = `status-dot ${fresh ? 'success' : 'neutral'}`;
    $('system-state').textContent = fresh
      ? t('header.openwrtOnline')
      : t('header.controlPlaneOnline');
  }

  function render(data) {
    state.data = data;
    state.csrf = data.csrf || '';

    syncSelect($('wan-select'), publicWans(data), (item) => `${item.name} · ${item.ip}`);
    syncSelect($('wg-select'), wireguards(data), (item) => `${item.name} · UDP ${item.listen_port}`);

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
      const response = await fetch('/api/v1/dashboard', {
        cache: 'no-store',
        credentials: 'same-origin'
      });
      if (response.status === 401) {
        location.reload();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (_) {
      $('system-state').textContent = t('header.statusUnavailable');
      $('system-dot').className = 'status-dot danger';
    }
  }

  async function post(path, body = {}) {
    if (state.busy) return;
    state.busy = true;
    window.RemoteGateGateControls?.render(state.data || {});

    try {
      const response = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': state.csrf
        },
        body: JSON.stringify(body)
      });

      const payload = response.status === 204
        ? {}
        : await response.json().catch(() => ({}));

      if (!response.ok) {
        if (payload.error === 'ipv4_required') {
          throw new Error(t('toast.ipv4Required'));
        }
        throw new Error(payload.error || `HTTP ${response.status}`);
      }

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
    onWireGuardChange: () => {
      if (state.data) renderWireGuard(state.data);
    }
  });

  document.querySelectorAll('[data-action="logout"]').forEach((button) => {
    button.addEventListener('click', logout);
  });

  window.addEventListener('remote-gate-language', () => {
    window.RemoteGateI18n?.apply();
    if (state.data) render(state.data);
  });

  $('workspace').addEventListener('workspacechange', () => {
    requestAnimationFrame(() => window.RemoteGateFit?.observe());
  });

  refresh();
  setInterval(refresh, 5000);
})();
