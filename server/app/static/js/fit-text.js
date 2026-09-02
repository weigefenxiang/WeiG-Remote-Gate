(() => {
  const observed = new WeakSet();
  const profiles = Object.freeze({
    hero: {max: 22, min: 7.5, floor: 6},
    value: {max: 20, min: 7.5, floor: 6},
    identity: {max: 17, min: 8.5, floor: 7},
    compact: {max: 13, min: 7.5, floor: 6},
    default: {max: 18, min: 10.5, floor: 7}
  });
  const selectorProfiles = Object.freeze([
    ['.verified-endpoint-value', 'hero'],
    ['.address-value', 'value'],
    ['.wan-address-copy', 'value'],
    ['.endpoint-trigger-copy strong', 'identity'],
    ['.endpoint-option-topline strong', 'identity'],
    ['.wan-row h3', 'identity'],
    ['.endpoint-trigger-address', 'compact'],
    ['.endpoint-option-address', 'compact']
  ]);
  const targetSelector = ['.fit-single-line', ...selectorProfiles.map(([selector]) => selector)].join(',');
  const resizeObserver = typeof ResizeObserver === 'function'
    ? new ResizeObserver((entries) => entries.forEach((entry) => fit(entry.target)))
    : null;
  let mutationFrame = 0;

  function number(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function inferredProfile(element) {
    const explicit = String(element?.dataset?.fitProfile || '');
    if (profiles[explicit]) return explicit;
    const matched = selectorProfiles.find(([selector]) => element?.matches?.(selector));
    return matched?.[1] || 'default';
  }

  function fitContract(element) {
    const profileName = inferredProfile(element);
    const profile = profiles[profileName] || profiles.default;
    if (!element.dataset.fitProfile) element.dataset.fitProfile = profileName;
    element.classList.add('fit-single-line');
    element.style.setProperty('min-width', '0');
    element.style.setProperty('max-width', '100%');
    element.style.setProperty('white-space', 'nowrap');
    element.style.setProperty('text-overflow', 'clip');
    element.style.setProperty('overflow', 'hidden');
    if (profileName === 'identity' && element.parentElement) {
      element.parentElement.style.setProperty('min-width', '0');
    }
    return {
      max: number(element.dataset.fitMax, profile.max),
      min: number(element.dataset.fitMin, profile.min),
      floor: number(element.dataset.fitFloor, profile.floor)
    };
  }

  function setFontSize(element, size) {
    element.style.setProperty('font-size', `${Math.max(1, size).toFixed(1)}px`, 'important');
  }

  function fit(element) {
    if (!element || !element.isConnected) return;
    const bounds = fitContract(element);
    const max = Math.max(bounds.max, bounds.min);
    const min = Math.min(max, bounds.min);
    const floor = Math.min(min, bounds.floor);
    setFontSize(element, max);

    const available = element.clientWidth;
    if (!available || element.scrollWidth <= available) return;

    let size = Math.max(min, max * (available / Math.max(1, element.scrollWidth)));
    setFontSize(element, size);

    for (let attempt = 0; attempt < 3 && element.scrollWidth > available && size > floor; attempt += 1) {
      size = Math.max(floor, size * (available / Math.max(1, element.scrollWidth)));
      setFontSize(element, size);
    }

    if (element.scrollWidth > available) {
      const emergency = Math.max(1, size * (available / Math.max(1, element.scrollWidth)));
      setFontSize(element, emergency);
    }
  }

  function targets(root = document) {
    const found = [];
    if (root?.matches?.(targetSelector)) found.push(root);
    root?.querySelectorAll?.(targetSelector).forEach((element) => found.push(element));
    return found;
  }

  function observe(root = document) {
    targets(root).forEach((element) => {
      fit(element);
      if (resizeObserver && !observed.has(element)) {
        observed.add(element);
        resizeObserver.observe(element);
      }
    });
  }

  const mutationObserver = typeof MutationObserver === 'function'
    ? new MutationObserver(() => {
      if (mutationFrame) return;
      mutationFrame = window.requestAnimationFrame(() => {
        mutationFrame = 0;
        observe();
      });
    })
    : null;

  window.RemoteGateFit = {fit, observe, profiles};
  window.addEventListener('resize', () => observe());
  window.addEventListener('remote-gate-language', () => window.requestAnimationFrame(() => observe()));

  function start() {
    observe();
    mutationObserver?.observe(document.documentElement, {subtree: true, childList: true, characterData: true});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
})();
