(() => {
  const key = 'weig-remote-gate:theme';
  const media = matchMedia('(prefers-color-scheme: dark)');

  function choice() {
    const saved = localStorage.getItem(key);
    return saved === 'light' || saved === 'dark' ? saved : 'auto';
  }

  function apply() {
    const selected = choice();
    const resolved = selected === 'auto' ? (media.matches ? 'dark' : 'light') : selected;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themeChoice = selected;
    document.querySelectorAll('[data-theme-choice]').forEach((button) => {
      button.classList.toggle('active', button.dataset.themeChoice === selected);
      button.setAttribute('aria-pressed', button.dataset.themeChoice === selected ? 'true' : 'false');
    });
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-theme-choice]');
    if (!button) return;
    const selected = button.dataset.themeChoice;
    if (selected === 'auto') localStorage.removeItem(key);
    else localStorage.setItem(key, selected);
    apply();
  });

  media.addEventListener?.('change', () => {
    if (choice() === 'auto') apply();
  });

  apply();
})();
