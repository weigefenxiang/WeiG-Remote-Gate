(() => {
  const STORAGE_KEY = 'remote-gate:language';
  const dictionaries = {
    en: {
      'common.unavailable': 'Unavailable',
      'common.unknown': 'Unknown',
      'common.never': 'Never',
      'common.notObserved': 'Not observed',
      'common.copy': 'Copy',
      'common.copied': 'Copied',
      'common.ready': 'Ready',
      'common.notReady': 'Not ready',
      'common.enabled': 'Enabled',
      'common.disabled': 'Disabled',
      'common.online': 'Online',
      'common.waiting': 'Waiting',
      'common.justNow': 'Just now',

      'header.secureRemoteAccess': 'Secure Remote Access',
      'header.systemOnline': 'System online',
      'header.openwrtOnline': 'OpenWrt online',
      'header.controlPlaneOnline': 'Control plane online',
      'header.statusUnavailable': 'Status unavailable',
      'header.arrange': 'Arrange',
      'header.done': 'Done',
      'header.resetLayout': 'Reset layout',
      'header.signOut': 'Sign out',
      'header.appearance': 'Appearance',
      'header.language': 'Language',
      'theme.auto': 'Auto',
      'theme.light': 'Light',
      'theme.dark': 'Dark',

      'dashboard.title': 'Remote access console',
      'dashboard.subtitle': 'Private by default. Open only a trusted client source when needed.',

      'gate.eyebrow': 'REMOTE GATE',
      'gate.title': 'Temporary WAN access',
      'gate.closed': 'Closed',
      'gate.closedSub': 'WAN input stays hidden',
      'gate.authorizing': 'Authorizing',
      'gate.closing': 'Closing',
      'gate.waitingAgent': 'Waiting for OpenWrt agent',
      'gate.open': 'Open',
      'gate.expiresIn': 'Expires in {value}',
      'gate.error': 'Error',
      'gate.agentFailed': 'Agent command failed',
      'gate.wireguard': 'WireGuard',
      'gate.endpoint': 'Access Endpoint',
      'gate.family': 'IP Family',
      'gate.duration': 'Access duration',
      'gate.scope': 'Access Scope',
      'gate.scopeWg': 'WireGuard only',
      'gate.scopeWgPing': 'WireGuard + Ping',
      'gate.recommended': 'Recommended',
      'gate.activate': 'Activate remote access',
      'gate.close': 'Close access now',
      'gate.closedBadge': 'CLOSED',
      'gate.pendingBadge': 'PENDING',
      'gate.authorizedBadge': 'AUTHORIZED',
      'gate.errorBadge': 'ERROR',
      'gate.familySourceMissing': '{family} cannot be selected until this signed-in session is recently observed over {family}.',
      'gate.ipv6Unavailable': 'IPv6 Gate is disabled or unavailable on this OpenWrt.',
      'gate.familyEndpointMissing': 'No reachable {family} WireGuard endpoint is currently reported.',

      'client.eyebrow': 'CURRENT CLIENT',
      'client.title': 'Trusted sources',
      'client.authorization': 'Gate authorization',
      'client.currentRequest': 'Current request',
      'client.serverObserved': 'Observed by VPS',
      'client.trustNote': 'Only addresses recently observed by the VPS through Cloudflare can be authorized. Browser-supplied IPs are never trusted.',

      'wg.eyebrow': 'WIREGUARD',
      'wg.title': 'Secure tunnel',
      'wg.interface': 'Interface',
      'wg.listenPort': 'Listen port',
      'wg.handshake': 'Latest Handshake',
      'wg.traffic': 'Traffic',
      'wg.status': 'Status',
      'wg.listening': 'Listening',
      'wg.connected': 'Connected',
      'wg.protected': 'Protected by Gate',
      'wg.noHandshake': 'No recent Handshake',
      'wg.lanHint': 'LAN access',
      'wg.lanHintValue': 'Verify client AllowedIPs and WG → LAN forwarding',

      'wan.eyebrow': 'MULTI-WAN',
      'wan.title': 'Access paths',
      'wan.path': 'WAN PATH',
      'wan.waiting': 'Waiting for OpenWrt report…',
      'wan.noInterfaces': 'No WAN paths reported yet.',
      'wan.direct': 'DIRECT',
      'wan.private': 'PRIVATE / CGNAT',
      'wan.nonGlobal': 'NON-GLOBAL',
      'wan.active': 'ACTIVE',
      'wan.inactive': 'INACTIVE',
      'wan.unknownDevice': 'Unknown device',
      'wan.noDefaultRoute': 'No default route',

      'activity.eyebrow': 'SECURITY EVENT STREAM',
      'activity.title': 'Recent activity',
      'activity.empty': 'No security events yet.',

      'system.eyebrow': 'SYSTEM',
      'system.title': 'Runtime',
      'system.agent': 'Agent',
      'system.requestFamily': 'Request family',
      'system.ipv4Gate': 'IPv4 Gate',
      'system.ipv6Gate': 'IPv6 Gate',
      'system.firewall': 'Firewall',
      'system.transport': 'Control path',

      'event.login_success': 'Signed in',
      'event.login_failed': 'Sign-in failed',
      'event.gate_requested': 'Gate activation requested',
      'event.gate_close_requested': 'Gate close requested',
      'event.command_done': 'OpenWrt command completed',
      'event.command_failed': 'OpenWrt command failed',
      'event.command_expired': 'Command expired',

      'toast.ipCopied': 'Address copied',
      'toast.clipboardUnavailable': 'Clipboard unavailable',
      'toast.closeQueued': 'Close command queued',
      'toast.authQueued': 'Authorization command queued',
      'toast.sourceNotObserved': 'The selected IP family has not been observed recently for this signed-in session.',
      'toast.ipv6Unavailable': 'IPv6 Gate is disabled or unavailable on OpenWrt.',
      'toast.endpointUnavailable': 'The selected access endpoint is no longer reachable.',
      'toast.agentUpgradeRequired': 'OpenWrt Agent must be upgraded before using this dual-stack feature.',
      'toast.familyMismatch': 'Trusted client source and endpoint IP families do not match.',
      'toast.invalidScope': 'Invalid access scope.',

      'workspace.moveEarlier': 'Move earlier',
      'workspace.moveLater': 'Move later',
      'workspace.size': 'Card size',
      'workspace.compact': 'Compact',
      'workspace.normal': 'Normal',
      'workspace.wide': 'Wide',
      'workspace.drag': 'Drag card',

      'login.controlPlane': 'PRIVATE CONTROL PLANE',
      'login.description': 'Enter through Cloudflare only. The home WAN does not expose an HTTP/HTTPS management endpoint for this project.',
      'login.username': 'Username',
      'login.password': 'Password',
      'login.remember': 'Remember this browser for 30 days',
      'login.signIn': 'Sign in securely',
      'login.loopback': 'Loopback-only backend'
    },

    zh: {
      'common.unavailable': '不可用',
      'common.unknown': '未知',
      'common.never': '从未',
      'common.notObserved': '未观察到',
      'common.copy': '复制',
      'common.copied': '已复制',
      'common.ready': 'Ready',
      'common.notReady': 'Not ready',
      'common.enabled': '已启用',
      'common.disabled': '已禁用',
      'common.online': 'Online',
      'common.waiting': '等待中',
      'common.justNow': '刚刚',

      'header.secureRemoteAccess': 'Secure Remote Access',
      'header.systemOnline': 'System online',
      'header.openwrtOnline': 'OpenWrt online',
      'header.controlPlaneOnline': 'Control plane online',
      'header.statusUnavailable': '状态不可用',
      'header.arrange': '排列',
      'header.done': '完成',
      'header.resetLayout': '重置布局',
      'header.signOut': '退出登录',
      'header.appearance': '外观',
      'header.language': '语言',
      'theme.auto': 'Auto',
      'theme.light': 'Light',
      'theme.dark': 'Dark',

      'dashboard.title': 'Remote access console',
      'dashboard.subtitle': '默认保持私有，仅在需要时临时开放 VPS 已可信观察到的 Client。',

      'gate.eyebrow': 'REMOTE GATE',
      'gate.title': '临时 WAN 访问',
      'gate.closed': 'Closed',
      'gate.closedSub': 'WAN input 保持隐藏',
      'gate.authorizing': 'Authorizing',
      'gate.closing': 'Closing',
      'gate.waitingAgent': '等待 OpenWrt Agent',
      'gate.open': 'Open',
      'gate.expiresIn': '{value} 后关闭',
      'gate.error': 'Error',
      'gate.agentFailed': 'Agent 命令失败',
      'gate.wireguard': 'WireGuard',
      'gate.endpoint': 'Access Endpoint',
      'gate.family': 'IP Family',
      'gate.duration': '访问时长',
      'gate.scope': 'Access Scope',
      'gate.scopeWg': '仅 WireGuard',
      'gate.scopeWgPing': 'WireGuard + Ping',
      'gate.recommended': '推荐',
      'gate.activate': 'Activate remote access',
      'gate.close': '立即关闭访问',
      'gate.closedBadge': 'CLOSED',
      'gate.pendingBadge': 'PENDING',
      'gate.authorizedBadge': 'AUTHORIZED',
      'gate.errorBadge': 'ERROR',
      'gate.familySourceMissing': '当前登录 Session 最近没有通过 {family} 被 VPS 可信观察到，因此暂不能选择 {family}。',
      'gate.ipv6Unavailable': '此 OpenWrt 的 IPv6 Gate 已禁用或当前不可用。',
      'gate.familyEndpointMissing': '当前没有上报可达的 {family} WireGuard Endpoint。',

      'client.eyebrow': 'CURRENT CLIENT',
      'client.title': '可信 Source',
      'client.authorization': 'Gate authorization',
      'client.currentRequest': '当前请求',
      'client.serverObserved': 'VPS 已观察',
      'client.trustNote': '只有 VPS 经 Cloudflare 最近真实观察到的地址才能授权；浏览器提交或本地保存的 IP 永远不作为可信输入。',

      'wg.eyebrow': 'WIREGUARD',
      'wg.title': 'Secure tunnel',
      'wg.interface': 'Interface',
      'wg.listenPort': 'Listen port',
      'wg.handshake': '最近 Handshake',
      'wg.traffic': 'Traffic',
      'wg.status': 'Status',
      'wg.listening': 'Listening',
      'wg.connected': 'Connected',
      'wg.protected': '受 Gate 保护',
      'wg.noHandshake': '暂无最近 Handshake',
      'wg.lanHint': 'LAN access',
      'wg.lanHintValue': '请确认 Client AllowedIPs 与 WG → LAN forwarding',

      'wan.eyebrow': 'MULTI-WAN',
      'wan.title': 'Access paths',
      'wan.path': 'WAN PATH',
      'wan.waiting': '等待 OpenWrt 上报…',
      'wan.noInterfaces': '尚无 WAN Path 上报。',
      'wan.direct': 'DIRECT',
      'wan.private': 'PRIVATE / CGNAT',
      'wan.nonGlobal': 'NON-GLOBAL',
      'wan.active': 'ACTIVE',
      'wan.inactive': 'INACTIVE',
      'wan.unknownDevice': '未知 device',
      'wan.noDefaultRoute': '无 default route',

      'activity.eyebrow': 'SECURITY EVENT STREAM',
      'activity.title': '最近 Activity',
      'activity.empty': '暂无 Security event。',

      'system.eyebrow': 'SYSTEM',
      'system.title': 'Runtime',
      'system.agent': 'Agent',
      'system.requestFamily': 'Request family',
      'system.ipv4Gate': 'IPv4 Gate',
      'system.ipv6Gate': 'IPv6 Gate',
      'system.firewall': 'Firewall',
      'system.transport': 'Control path',

      'event.login_success': '已登录',
      'event.login_failed': '登录失败',
      'event.gate_requested': '已请求 Gate activation',
      'event.gate_close_requested': '已请求关闭 Gate',
      'event.command_done': 'OpenWrt 命令已完成',
      'event.command_failed': 'OpenWrt 命令失败',
      'event.command_expired': '命令已过期',

      'toast.ipCopied': '地址已复制',
      'toast.clipboardUnavailable': 'Clipboard 不可用',
      'toast.closeQueued': '关闭命令已排队',
      'toast.authQueued': '授权命令已排队',
      'toast.sourceNotObserved': '当前登录 Session 最近没有可信观察到所选 IP Family 的 Client source。',
      'toast.ipv6Unavailable': 'OpenWrt 的 IPv6 Gate 已禁用或不可用。',
      'toast.endpointUnavailable': '所选 Access Endpoint 已不可达。',
      'toast.agentUpgradeRequired': '需要先升级 OpenWrt Agent 才能使用该双栈功能。',
      'toast.familyMismatch': '可信 Client source 与 Endpoint 的 IP Family 不一致。',
      'toast.invalidScope': 'Access Scope 无效。',

      'workspace.moveEarlier': '向前移动',
      'workspace.moveLater': '向后移动',
      'workspace.size': '卡片尺寸',
      'workspace.compact': 'Compact',
      'workspace.normal': 'Normal',
      'workspace.wide': 'Wide',
      'workspace.drag': '拖动卡片',

      'login.controlPlane': 'PRIVATE CONTROL PLANE',
      'login.description': '仅通过 Cloudflare 进入控制面；家庭 WAN 不暴露本项目的 HTTP/HTTPS 管理入口。',
      'login.username': 'Username',
      'login.password': 'Password',
      'login.remember': '此浏览器保持登录 30 天',
      'login.signIn': '安全登录',
      'login.loopback': 'Loopback-only backend'
    }
  };

  function detectedLanguage() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'en' || saved === 'zh') return saved;
    const languages = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language || ''];
    return languages.some((value) => /^zh(?:-|$)/i.test(String(value))) ? 'zh' : 'en';
  }

  let language = detectedLanguage();

  function interpolate(value, params) {
    return String(value).replace(/\{([A-Za-z0-9_]+)\}/g, (_, key) => String(params?.[key] ?? ''));
  }

  function t(key, params = {}) {
    const base = dictionaries[language]?.[key] ?? dictionaries.en[key] ?? key;
    return interpolate(base, params);
  }

  function apply(root = document) {
    root.querySelectorAll('[data-i18n]').forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    root.querySelectorAll('[data-i18n-title]').forEach((element) => {
      element.title = t(element.dataset.i18nTitle);
      if (element.hasAttribute('aria-label')) element.setAttribute('aria-label', t(element.dataset.i18nTitle));
    });
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    document.documentElement.dataset.lang = language;
    document.querySelectorAll('[data-lang-choice]').forEach((button) => {
      const active = button.dataset.langChoice === language;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function setLanguage(next, persist = true) {
    if (next !== 'en' && next !== 'zh') return;
    language = next;
    if (persist) localStorage.setItem(STORAGE_KEY, next);
    apply();
    window.dispatchEvent(new CustomEvent('remote-gate-language', {detail: {language}}));
  }

  window.RemoteGateI18n = {t, apply, setLanguage, get language() { return language; }};

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-lang-choice]');
    if (button) setLanguage(button.dataset.langChoice);
  });

  const ready = () => apply();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, {once: true});
  else ready();
})();
