(() => {
  const MAX_VISIBLE = 4;
  const DEFAULT_MS = 3600;
  let sequence = 0;

  function stack() {
    let root = document.getElementById('feedback-stack');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'feedback-stack';
    root.className = 'feedback-stack';
    root.setAttribute('aria-live', 'polite');
    root.setAttribute('aria-relevant', 'additions');
    document.body.append(root);
    return root;
  }

  function iconFor(kind) {
    return {info: 'i', success: '✓', warning: '!', error: '×'}[kind] || 'i';
  }

  function normalizeKind(kind) {
    return ['info', 'success', 'warning', 'error'].includes(kind) ? kind : 'info';
  }

  function dismiss(card) {
    if (!card || card.dataset.closing === '1') return;
    card.dataset.closing = '1';
    card.classList.add('feedback-leave');
    window.setTimeout(() => card.remove(), 210);
  }

  function notify(message, kind = 'info', options = {}) {
    const text = String(message || '').trim();
    if (!text) return null;
    const type = normalizeKind(kind);
    const root = stack();
    const card = document.createElement('div');
    const id = `feedback-${++sequence}`;
    card.id = id;
    card.className = `feedback-card feedback-${type}`;
    card.dataset.kind = type;
    card.setAttribute('role', type === 'error' ? 'alert' : 'status');

    const icon = document.createElement('span');
    icon.className = 'feedback-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = iconFor(type);

    const copy = document.createElement('div');
    copy.className = 'feedback-copy';
    const title = document.createElement('strong');
    title.textContent = String(options.title || ({info: 'Remote Gate', success: 'Completed', warning: 'Please wait', error: 'Action failed'}[type]));
    const body = document.createElement('span');
    body.textContent = text;
    copy.append(title, body);

    const close = document.createElement('button');
    close.className = 'feedback-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Dismiss');
    close.textContent = '×';
    close.addEventListener('click', () => dismiss(card));

    const progress = document.createElement('span');
    progress.className = 'feedback-progress';
    const duration = Math.max(1400, Number(options.duration || DEFAULT_MS));
    progress.style.setProperty('--feedback-duration', `${duration}ms`);

    card.append(icon, copy, close, progress);
    root.prepend(card);
    while (root.children.length > MAX_VISIBLE) root.lastElementChild?.remove();
    requestAnimationFrame(() => card.classList.add('feedback-entered'));
    window.setTimeout(() => dismiss(card), duration);
    return id;
  }

  function bridgeLegacyToast() {
    const legacy = document.getElementById('toast');
    if (!legacy) return;
    legacy.classList.add('feedback-legacy-bridge');
    const relay = () => {
      if (!legacy.classList.contains('show')) return;
      const text = legacy.textContent.trim();
      if (text) notify(text, legacy.dataset.kind === 'error' ? 'error' : 'info');
      legacy.classList.remove('show');
    };
    new MutationObserver(relay).observe(legacy, {attributes: true, childList: true, characterData: true, subtree: true});
  }

  function bind() {
    stack();
    bridgeLegacyToast();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();

  window.RemoteGateFeedback = {notify, dismiss};
})();
