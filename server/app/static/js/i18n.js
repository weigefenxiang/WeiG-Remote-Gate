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
      'dashboard.subtitle': 'Private by default. Open only the current client when needed.',
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
      'gate.publicWan': 'Public WAN',
      'gate.wireguard': 'WireGuard',
      'gate.family': 'IP Family',
      'gate.familyIpv4': 'IPv4',
      'gate.familyIpv6': 'IPv6',
      'gate.familyDual': 'Dual',
      'gate.familyNoteIpv4': 'IPv4 Gate is enabled only when this control request itself is using IPv4.',
      'gate.familyNoteIpv6': 'IPv6 is displayed but data-plane authorization is not enabled in this verified release.',
      'gate.duration': 'Access duration',
      'gate.activate': 'Activate remote access',
      'gate.close': 'Close access now',
      'gate.closedBadge': 'CLOSED',
      'gate.pendingBadge': 'PENDING',
      'gate.authorizedBadge': 'AUTHORIZED',
      'gate.errorBadge': 'ERROR',
      'client.eyebrow': 'CURRENT CLIENT',
      'client.title': 'Observed addresses',
      'client.requestVia': 'Request via',
      'client.ipv4': 'IPv4',
      'client.ipv6': 'IPv6',
      'client.authorization': 'Gate authorization',
      'client.currentRequest': 'Current request',
      'client.browserObserved': 'Observed by this browser',
      'client.displayOnly': 'Display only',
      'client.trustNote': 'Browser-saved addresses are display-only and are never trusted as authorization input.',
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
      'wan.eyebrow': 'PUBLIC WAN',
      'wan.title': 'Interfaces',
      'wan.waiting': 'Waiting for OpenWrt report…',
      'wan.noInterfaces': 'No WAN interfaces reported yet.',
      'wan.public': 'PUBLIC WAN',
      'wan.private': 'PRIVATE / CGNAT',
      'wan.active': 'ACTIVE',
      'wan.inactive': 'INACTIVE',
      'wan.reported': 'Reported {value}',
      'wan.neverReported': 'Never reported',
      'wan.unknownDevice': 'Unknown device',
      'activity.eyebrow': 'SECURITY EVENT STREAM',
      'activity.title': 'Recent activity',
      'activity.empty': 'No security events yet.',
      'system.eyebrow': 'SYSTEM',
      'system.title': 'Runtime',
      'system.agent': 'Agent',
      'system.requestFamily': 'Request family',
      'system.gateMode': 'Gate mode',
      'system.gateModeValue': 'Verified IPv4',
      'system.refresh': 'Refresh',
      'system.every5s': 'Every 5s',
      'event.login_success': 'Signed in',
      'event.login_failed': 'Sign-in failed',
      'event.gate_requested': 'Gate activation requested',
      'event.gate_close_requested': 'Gate close requested',
      'event.command_done': 'OpenWrt command completed',
      'event.command_failed': 'OpenWrt command failed',
      'event.command_expired': 'Command expired',
      'toast.ipCopied': 'IPv4 copied',
      'toast.clipboardUnavailable': 'Clipboard unavailable',
      'toast.closeQueued': 'Close command queued',
      'toast.authQueued': 'Authorization command queued',
      'toast.ipv4Required': 'Open this control page over IPv4 before activating the verified IPv4 Gate.',
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
      'dashboard.subtitle': '默认保持私有，仅在需要时临时开放当前 Client。',
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
      'gate.publicWan': 'Public WAN',
      'gate.wireguard': 'WireGuard',
      'gate.family': 'IP Family',
      'gate.familyIpv4': 'IPv4',
      'gate.familyIpv6': 'IPv6',
      'gate.familyDual': 'Dual',
      'gate.familyNoteIpv4': '只有当前控制请求本身使用 IPv4 时，才允许启用已验证的 IPv4 Gate。',
      'gate.familyNoteIpv6': 'IPv6 支持显示；本验证版本暂未启用 IPv6 数据面授权。',
      'gate.duration': '访问时长',
      'gate.activate': 'Activate remote access',
      'gate.close': '立即关闭访问',
      'gate.closedBadge': 'CLOSED',
      'gate.pendingBadge': 'PENDING',
      'gate.authorizedBadge': 'AUTHORIZED',
      'gate.errorBadge': 'ERROR',
      'client.eyebrow': 'CURRENT CLIENT',
      'client.title': '已观察地址',
      'client.requestVia': '当前请求',
      'client.ipv4': 'IPv4',
      'client.ipv6': 'IPv6',
      'client.authorization': 'Gate authorization',
      'client.currentRequest': '当前请求',
      'client.browserObserved': '本浏览器曾观察到',
      'client.displayOnly': '仅显示',
      'client.trustNote': '浏览器本地保存的地址只用于显示，绝不会作为可信授权输入。',
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
      'wan.eyebrow': 'PUBLIC WAN',
      'wan.title': 'Interfaces',
      'wan.waiting': '等待 OpenWrt 上报…',
      'wan.noInterfaces': '尚无 WAN Interface 上报。',
      'wan.public': 'PUBLIC WAN',
      'wan.private': 'PRIVATE / CGNAT',
      'wan.active': 'ACTIVE',
      'wan.inactive': 'INACTIVE',
      'wan.reported': '{value} 前上报',
      'wan.neverReported': '从未上报',
      'wan.unknownDevice': '未知 device',
      'activity.eyebrow': 'SECURITY EVENT STREAM',
      'activity.title': '最近 Activity',
      'activity.empty': '暂无 Security event。',
      'system.eyebrow': 'SYSTEM',
      'system.title': 'Runtime',
      'system.agent': 'Agent',
      'system.requestFamily': 'Request family',
      'system.gateMode': 'Gate mode',
      'system.gateModeValue': '已验证 IPv4',
      'system.refresh': 'Refresh',
      'system.every5s': '每 5 秒',
      'event.login_success': '已登录',
      'event.login_failed': '登录失败',
      'event.gate_requested': '已请求 Gate activation',
      'event.gate_close_requested': '已请求关闭 Gate',
      'event.command_done': 'OpenWrt 命令已完成',
      'event.command_failed': 'OpenWrt 命令失败',
      'event.command_expired': '命令已过期',
      'toast.ipCopied': 'IPv4 已复制',
      'toast.clipboardUnavailable': 'Clipboard 不可用',
      'toast.closeQueued': '关闭命令已排队',
      'toast.authQueued': '授权命令已排队',
      'toast.ipv4Required': '请让控制页通过 IPv4 连接后，再启用已验证的 IPv4 Gate。',
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
      button.classList.toggle('active', button.dataset.langChoice === language);
      button.setAttribute('aria-pressed', button.dataset.langChoice === language ? 'true' : 'false');
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => apply(), {once: true});
  } else {
    apply();
  }
})();
