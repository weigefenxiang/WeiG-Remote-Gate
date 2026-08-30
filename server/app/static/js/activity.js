(() => {
  function timeLabel(epoch) {
    const date = new Date(Number(epoch || 0) * 1000);
    if (!Number.isFinite(date.getTime())) return '—';

    const now = new Date();
    const sameDay =
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate();

    if (sameDay) {
      return date.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    }

    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const time = date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
    return `${month}-${day} ${time}`;
  }

  function compactDetails(event) {
    const type = String(event?.type || '');
    const values = [];

    if (type === 'login_success' || type === 'login_failed' || type === 'gate_close_requested') {
      if (event.source_ip) values.push(event.source_ip);
    } else if (type === 'gate_requested') {
      if (event.wan) values.push(event.wan);
      if (event.wireguard) values.push(event.wireguard);
    } else if (type === 'command_done' || type === 'command_failed') {
      if (event.action) values.push(event.action);
      if (event.detail) values.push(event.detail);
    } else {
      [event.source_ip, event.wan, event.wireguard, event.action, event.detail]
        .filter(Boolean)
        .slice(0, 2)
        .forEach((value) => values.push(value));
    }

    return values.map((value) => String(value)).filter(Boolean);
  }

  function fullDetails(event) {
    return [
      event.source_ip && `IP ${event.source_ip}`,
      event.wan && `WAN ${event.wan}`,
      event.wireguard && `WireGuard ${event.wireguard}`,
      event.action && `action ${event.action}`,
      event.detail && String(event.detail)
    ].filter(Boolean).join(' · ');
  }

  function render(list, rawEvents, t) {
    if (!list) return;
    list.replaceChildren();

    const events = Array.isArray(rawEvents) ? [...rawEvents].reverse() : [];
    if (!events.length) {
      const empty = document.createElement('div');
      empty.className = 'activity-empty';
      empty.textContent = t('activity.empty');
      list.append(empty);
      return;
    }

    events.slice(0, 6).forEach((event) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'activity-row';
      row.setAttribute('aria-expanded', 'false');

      const icon = document.createElement('span');
      icon.className = 'activity-icon';
      icon.setAttribute('aria-hidden', 'true');

      const time = document.createElement('time');
      time.textContent = timeLabel(event.at);

      const summary = document.createElement('span');
      summary.className = 'activity-summary fit-single-line';
      summary.dataset.fitMax = '13';
      summary.dataset.fitMin = '9.5';

      const title = document.createElement('strong');
      title.textContent = t(`event.${event.type || ''}`) || String(event.type || 'Event');
      summary.append(title);

      const parts = compactDetails(event);
      if (parts.length) {
        summary.append(document.createTextNode(` · ${parts.join(' · ')}`));
      }

      const detail = document.createElement('span');
      detail.className = 'activity-detail';
      detail.textContent = fullDetails(event) || title.textContent;

      row.append(icon, time, summary, detail);
      row.title = detail.textContent;

      row.addEventListener('click', () => {
        const expanded = !row.classList.contains('expanded');
        row.classList.toggle('expanded', expanded);
        row.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        requestAnimationFrame(() => window.RemoteGateFit?.observe(list));
      });

      list.append(row);
    });

    requestAnimationFrame(() => window.RemoteGateFit?.observe(list));
  }

  window.RemoteGateActivity = {render};
})();
