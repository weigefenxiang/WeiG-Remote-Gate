(() => {
  const current = document.currentScript;
  const currentUrl = new URL(current?.src || location.href, location.href);
  const assetVersion = currentUrl.searchParams.get('v') || '';
  const assetUrl = (path) => assetVersion ? `${path}?v=${encodeURIComponent(assetVersion)}` : path;

  const favicon = document.createElement('link');
  favicon.rel = 'icon';
  favicon.type = 'image/png';
  favicon.href = '/static/Wei.G.ico';
  document.head.append(favicon);

  const interaction = document.createElement('link');
  interaction.rel = 'stylesheet';
  interaction.href = assetUrl('/static/css/interaction.css');
  document.head.append(interaction);

  const key = 'weig-remote-gate:theme';
  const saved = localStorage.getItem(key);
  const choice = saved === 'light' || saved === 'dark' ? saved : 'auto';
  const resolved = choice === 'auto'
    ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : choice;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeChoice = choice;

  // Security-critical client discovery and semantic Gate dependencies are loaded explicitly by dashboard.html.
  // Optional presentation modules inherit the immutable build SHA from this script URL.
  [
    '/static/js/motion-feedback.js',
    '/static/js/duration-control.js'
  ].forEach((src) => {
    if (document.querySelector(`script[data-remote-gate-module="${src}"]`)) return;
    const script = document.createElement('script');
    script.src = assetUrl(src);
    script.async = false;
    script.dataset.remoteGateModule = src;
    document.head.append(script);
  });
})();
