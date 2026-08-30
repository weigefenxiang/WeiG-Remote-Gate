(() => {
  const key = 'weig-remote-gate:theme';
  const media = matchMedia('(prefers-color-scheme: dark)');

  function choice() {
    const saved = localStorage.getItem(key);
    return saved === 'light' || saved === 'dark' ? saved : 'auto';
  }

  function resolved(selected = choice()) {
    return selected === 'auto' ? (media.matches ? 'dark' : 'light') : selected;
  }

  function updateToggle() {
    const current = resolved();
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.dataset.resolvedTheme = current;
      button.setAttribute('aria-pressed', current === 'dark' ? 'true' : 'false');
      button.title = current === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
      button.setAttribute('aria-label', button.title);
    });
  }

  function apply() {
    const selected = choice();
    const current = resolved(selected);
    document.documentElement.dataset.theme = current;
    document.documentElement.dataset.themeChoice = selected;
    document.querySelectorAll('[data-theme-choice]').forEach((button) => {
      button.classList.toggle('active', button.dataset.themeChoice === selected);
      button.setAttribute('aria-pressed', button.dataset.themeChoice === selected ? 'true' : 'false');
    });
    updateToggle();
  }

  function setChoice(selected) {
    if (selected === 'auto') localStorage.removeItem(key);
    else if (selected === 'light' || selected === 'dark') localStorage.setItem(key, selected);
    else return;
    apply();
  }

  function toggleResolved() {
    setChoice(resolved() === 'dark' ? 'light' : 'dark');
  }

  document.addEventListener('click', (event) => {
    const choiceButton = event.target.closest('[data-theme-choice]');
    if (choiceButton) {
      setChoice(choiceButton.dataset.themeChoice);
      return;
    }
    if (event.target.closest('[data-theme-toggle]')) toggleResolved();
  });

  media.addEventListener?.('change', () => {
    if (choice() === 'auto') apply();
  });

  window.RemoteGateTheme = {apply, setChoice, toggle: toggleResolved, choice, resolved};
  apply();
})();
