(() => {
  const $ = (id) => document.getElementById(id);
  const state = { data: null, csrf: '', ttl: 300, busy: false };

  const EVENT_LABELS = {
    login_success: 'Signed in',
    login_failed: 'Sign-in failed',
    gate_requested: 'Gate activation requested',
    gate_close_requested: 'Gate close requested',
    command_done: 'OpenWrt command completed',
    command_failed: 'OpenWrt command failed',
    command_expired: 'Command expired'
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
    let v = n, i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
    return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function age(epoch) {
    const ts = Number(epoch || 0);
    if (!ts) return 'Never';
    const seconds = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (seconds < 10) return 'Just now';
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  function remaining(seconds) {
    const n = Math.max(0, Number(seconds || 0));
    if (!n) return '—';
    const m = Math.floor(n / 60);
    const s = Math.floor(n % 60);
    return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
  }

  function publicWans(data) {
    const interfaces = data?.current?.interfaces || {};
    return Object.entries(interfaces)
      .filter(([, item]) => item && item.active && item.address_type === 'public')
      .map(([name, item]) => ({ name, ...item }));
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
      option.textContent = 'Unavailable';
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

  function renderGate(data) {
    const pending = data?.gate?.queue?.pending;
    const last = data?.gate?.queue?.last;
    const fw = data?.agent?.firewall || {};
    const active = Boolean(fw.active);
    const pendingAction = pending?.action;
    const orb = $('gate-orb');

    let mode = 'closed', title = 'Closed', subtitle = 'WAN input stays hidden', badge = 'CLOSED';
    if (pendingAction === 'activate') {
      mode = 'authorizing'; title = 'Authorizing'; subtitle = 'Waiting for OpenWrt agent'; badge = 'PENDING';
    } else if (pendingAction === 'close') {
      mode = 'authorizing'; title = 'Closing'; subtitle = 'Waiting for OpenWrt agent'; badge = 'PENDING';
    } else if (active) {
      mode = 'open'; title = 'Open'; subtitle = `Expires in ${remaining(fw.expires_in)}`; badge = 'AUTHORIZED';
    } else if (last?.state === 'failed') {
      mode = 'error'; title = 'Error'; subtitle = last.detail || 'Agent command failed'; badge = 'ERROR';
    }

    orb.dataset.state = mode;
    $('gate-state').textContent = title;
    $('gate-substate').textContent = subtitle;
    $('gate-state-badge').textContent = badge;
    $('gate-lock').textContent = active ? '◇' : '◆';
    $('activate-button').classList.toggle('hidden', active);
    $('close-button').classList.toggle('hidden', !active);
    $('activate-button').disabled = state.busy || Boolean(pending) || !$('wan-select').value || !$('wg-select').value;
    $('close-button').disabled = state.busy || Boolean(pending);
  }

  function renderFirewall(data) {
    const fw = data?.agent?.firewall || {};
    const active = Boolean(fw.active);
    $('fw-dot').className = `status-dot ${active ? 'success' : 'neutral'}`;
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
      $('wg-name').textContent = 'Unavailable';
      $('wg-port').textContent = '—';
      $('wg-handshake').textContent = 'Never';
      $('wg-traffic').textContent = '—';
      $('wg-dot').className = 'status-dot neutral';
      return;
    }
    const handshake = Number(wg.latest_handshake || 0);
    const recent = handshake > 0 && (Date.now() / 1000 - handshake) < 180;
    $('wg-name').textContent = wg.name;
    $('wg-port').textContent = String(wg.listen_port);
    $('wg-handshake').textContent = age(handshake);
    $('wg-traffic').textContent = `${fmtBytes(wg.rx)} ↓ · ${fmtBytes(wg.tx)} ↑`;
    $('wg-dot').className = `status-dot ${recent ? 'success' : 'neutral'}`;
  }

  function renderWans(data) {
    const grid = $('wan-grid');
    grid.replaceChildren();
    const interfaces = Object.entries(data?.current?.interfaces || {})
      .map(([name, item]) => ({ name, ...item }))
      .sort((a, b) => Number(b.active) - Number(a.active) || (a.address_type === 'public' ? -1 : 1));

    if (!interfaces.length) {
      const empty = document.createElement('div');
      empty.className = 'empty depth-card';
      empty.textContent = 'No WAN interfaces reported yet.';
      grid.append(empty);
      return;
    }

    interfaces.forEach((item) => {
      const card = document.createElement('article');
      card.className = 'wan-card depth-card';
      const publicWan = item.address_type === 'public';
      card.innerHTML = `
        <div class="wan-card-top">
          <div>
            <span class="eyebrow">${publicWan ? 'PUBLIC WAN' : 'PRIVATE / CGNAT'}</span>
            <h3></h3>
          </div>
          <span class="state-badge ${item.active ? '' : 'muted-badge'}">${item.active ? 'ACTIVE' : 'INACTIVE'}</span>
        </div>
        <button type="button" class="ip-copy" title="Copy IPv4"><span></span><small>Copy</small></button>
        <div class="wan-meta">
          <span>${item.device || 'Unknown device'}</span>
          <span>${item.last_report_at ? `Reported ${age(item.last_report_at)}` : 'Never reported'}</span>
        </div>`;
      card.querySelector('h3').textContent = item.name;
      card.querySelector('.ip-copy span').textContent = item.ip || 'Not reported';
      const copy = card.querySelector('.ip-copy');
      copy.disabled = !item.ip;
      copy.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(item.ip);
          toast('IPv4 copied');
        } catch (_) {
          toast('Clipboard unavailable', 'error');
        }
      });
      grid.append(card);
    });

    $('wan-refresh').textContent = `Updated ${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})}`;
  }

  function renderActivity(data) {
    const list = $('activity-list');
    list.replaceChildren();
    const events = Array.isArray(data?.activity) ? [...data.activity].reverse() : [];
    if (!events.length) {
      const empty = document.createElement('div');
      empty.className = 'activity-empty muted';
      empty.textContent = 'No security events yet.';
      list.append(empty);
      return;
    }

    events.slice(0, 12).forEach((event) => {
      const row = document.createElement('div');
      row.className = 'activity-row';
      const title = EVENT_LABELS[event.type] || String(event.type || 'Event');
      const details = [
        event.source_ip,
        event.wan,
        event.wireguard,
        event.action,
        event.detail
      ].filter(Boolean).join(' · ');
      const time = new Date(Number(event.at || 0) * 1000).toLocaleString([], {hour12:false});
      row.innerHTML = `<span class="activity-icon"></span><div><strong></strong><small></small></div><time></time>`;
      row.querySelector('strong').textContent = title;
      row.querySelector('small').textContent = details || 'WeiG Remote Gate';
      row.querySelector('time').textContent = time;
      list.append(row);
    });
  }

  function render(data) {
    state.data = data;
    state.csrf = data.csrf || '';
    $('client-ip').textContent = data.client_ip || 'Unknown';

    syncSelect($('wan-select'), publicWans(data), (item) => `${item.name} · ${item.ip}`);
    syncSelect($('wg-select'), wireguards(data), (item) => `${item.name} · UDP ${item.listen_port}`);

    renderWireGuard(data);
    renderFirewall(data);
    renderGate(data);
    renderWans(data);
    renderActivity(data);

    const reportedAt = Number(data?.agent?.reported_at || 0);
    const agentFresh = reportedAt && (Date.now() / 1000 - reportedAt) < 45;
    $('system-state').textContent = agentFresh ? 'OpenWrt online' : 'Control plane online';
  }

  async function refresh() {
    try {
      const response = await fetch('/api/v1/dashboard', {cache:'no-store', credentials:'same-origin'});
      if (response.status === 401) { location.reload(); return; }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (error) {
      $('system-state').textContent = 'Status unavailable';
    }
  }

  async function post(path, body = {}) {
    if (state.busy) return;
    state.busy = true;
    renderGate(state.data || {});
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
      const payload = response.status === 204 ? {} : await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      toast(path.includes('close') ? 'Close command queued' : 'Authorization command queued');
      await refresh();
    } catch (error) {
      toast(String(error.message || error), 'error');
    } finally {
      state.busy = false;
      renderGate(state.data || {});
    }
  }

  $('ttl-segment').addEventListener('click', (event) => {
    const button = event.target.closest('[data-ttl]');
    if (!button) return;
    state.ttl = Number(button.dataset.ttl);
    $('ttl-segment').querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
  });

  $('wg-select').addEventListener('change', () => {
    if (state.data) renderWireGuard(state.data);
  });

  $('activate-button').addEventListener('click', () => {
    post('/api/v1/gate/activate', {
      wan: $('wan-select').value,
      wireguard: $('wg-select').value,
      ttl: state.ttl
    });
  });

  $('close-button').addEventListener('click', () => post('/api/v1/gate/close'));

  $('logout-button').addEventListener('click', async () => {
    const response = await fetch('/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'X-CSRF-Token': state.csrf},
      redirect: 'follow'
    });
    location.href = response.url || '/';
  });

  refresh();
  setInterval(refresh, 5000);
})();
