(() => {
  const observed = new WeakSet();
  const resizeObserver = typeof ResizeObserver === 'function'
    ? new ResizeObserver((entries) => entries.forEach((entry) => fit(entry.target)))
    : null;

  function number(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function fit(element) {
    if (!element || !element.isConnected) return;
    const max = number(element.dataset.fitMax, 18);
    const min = number(element.dataset.fitMin, 10.5);
    element.style.fontSize = `${max}px`;
    element.style.whiteSpace = 'nowrap';
    element.style.textOverflow = 'clip';
    element.style.overflow = 'hidden';

    const available = element.clientWidth;
    if (!available || element.scrollWidth <= available) return;

    const ratio = available / Math.max(1, element.scrollWidth);
    let size = Math.max(min, Math.floor(max * ratio * 10) / 10);
    element.style.fontSize = `${size}px`;

    if (element.scrollWidth > available && size > min) {
      size = Math.max(min, Math.floor(size * (available / element.scrollWidth) * 10) / 10);
      element.style.fontSize = `${size}px`;
    }
  }

  function observe(root = document) {
    root.querySelectorAll('.fit-single-line').forEach((element) => {
      fit(element);
      if (resizeObserver && !observed.has(element)) {
        observed.add(element);
        resizeObserver.observe(element);
      }
    });
  }

  window.RemoteGateFit = {fit, observe};
  window.addEventListener('resize', () => observe());
  window.addEventListener('remote-gate-language', () => requestAnimationFrame(() => observe()));

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => observe(), {once: true});
  } else {
    observe();
  }
})();
