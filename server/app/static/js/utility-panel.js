(() => {
  const trigger = document.getElementById('utility-trigger');
  const layer = document.getElementById('utility-layer');
  const sheet = document.getElementById('utility-sheet');
  if (!trigger || !layer || !sheet) return;

  let returnFocus = null;

  function focusables() {
    return Array.from(sheet.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'));
  }

  function open() {
    returnFocus = document.activeElement;
    layer.hidden = false;
    document.documentElement.classList.add('utility-open');
    trigger.setAttribute('aria-expanded', 'true');
    requestAnimationFrame(() => {
      layer.classList.add('open');
      sheet.focus({preventScroll: true});
    });
  }

  function close() {
    layer.classList.remove('open');
    document.documentElement.classList.remove('utility-open');
    trigger.setAttribute('aria-expanded', 'false');
    layer.hidden = true;
    if (returnFocus && typeof returnFocus.focus === 'function') returnFocus.focus({preventScroll: true});
  }

  trigger.addEventListener('click', () => layer.hidden ? open() : close());
  layer.querySelectorAll('[data-utility-close]').forEach((button) => button.addEventListener('click', close));

  document.addEventListener('keydown', (event) => {
    if (layer.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const items = focusables();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === sheet)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();
