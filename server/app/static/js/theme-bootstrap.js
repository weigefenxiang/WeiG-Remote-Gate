(() => {
  const favicon = document.createElement('link');
  favicon.rel = 'icon';
  favicon.type = 'image/png';
  favicon.href = '/static/Wei.G.ico';
  document.head.append(favicon);

  const interaction = document.createElement('link');
  interaction.rel = 'stylesheet';
  interaction.href = '/static/css/interaction.css';
  document.head.append(interaction);

  const key = 'weig-remote-gate:theme';
  const saved = localStorage.getItem(key);
  const choice = saved === 'light' || saved === 'dark' ? saved : 'auto';
  const resolved = choice === 'auto'
    ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : choice;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeChoice = choice;

  const modules = [
    '/static/js/motion-feedback.js',
    '/static/js/client-sources.js',
    '/static/js/endpoint-picker.js',
    '/static/js/duration-control.js'
  ];

  modules.forEach((src) => {
    if (document.querySelector(`script[src="${src}"]`)) return;
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    document.head.append(script);
  });

  function brandIcon() {
    const trigger = document.getElementById('utility-trigger');
    if (!trigger || trigger.querySelector('.brand-icon-image')) return;
    trigger.textContent = '';
    const image = document.createElement('img');
    image.className = 'brand-icon-image';
    image.src = '/static/Wei.G.ico';
    image.alt = '';
    image.width = 44;
    image.height = 44;
    image.decoding = 'async';
    trigger.append(image);
    trigger.classList.add('brand-icon-chassis');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', brandIcon, {once: true});
  else brandIcon();
})();
