(() => {
  const MIN = 1800;
  const MAX = 43200;
  const STEP = 1800;
  const DEFAULT = 3600;

  const $ = (id) => document.getElementById(id);
  const zh = () => document.documentElement.dataset.lang === 'zh';

  function format(seconds) {
    const value = Number(seconds || 0);
    if (value < 3600) return `${Math.round(value / 60)}m`;
    const hours = value / 3600;
    return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`;
  }

  function ensureUi() {
    const root = $('ttl-segment');
    if (!root) return null;

    let custom = $('ttl-custom-button');
    if (!custom) {
      custom = document.createElement('button');
      custom.type = 'button';
      custom.id = 'ttl-custom-button';
      custom.dataset.ttl = String(DEFAULT);
      custom.dataset.customDuration = '1';
      custom.setAttribute('aria-expanded', 'false');
      custom.setAttribute('aria-controls', 'duration-custom-panel');
      custom.textContent = 'Custom';
      root.append(custom);
    }

    let panel = $('duration-custom-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'duration-custom-panel';
      panel.className = 'duration-custom-panel';
      panel.hidden = true;
      panel.innerHTML = `
        <div class="duration-readout">
          <span class="eyebrow">CUSTOM DURATION</span>
          <output id="duration-output" for="duration-slider">1h</output>
        </div>
        <div class="duration-rail" id="duration-fill">
          <input id="duration-slider" type="range" min="${MIN}" max="${MAX}" step="${STEP}" value="${DEFAULT}" aria-label="Custom access duration">
        </div>
        <div class="duration-scale" aria-hidden="true">
          <span>0.5h</span><span>12h</span>
        </div>`;
      root.insertAdjacentElement('afterend', panel);
    }

    return {root, custom, panel, slider: $('duration-slider')};
  }

  function setPanelOpen(open) {
    const panel = $('duration-custom-panel');
    const button = $('ttl-custom-button');
    if (!panel || !button) return;
    panel.hidden = !open;
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function syncValue(value, {commit = false, feedback = false} = {}) {
    const slider = $('duration-slider');
    const output = $('duration-output');
    const custom = $('ttl-custom-button');
    const fill = $('duration-fill');
    if (!slider || !output || !custom) return;

    let next = Number(value || DEFAULT);
    next = Math.min(MAX, Math.max(MIN, Math.round(next / STEP) * STEP));
    slider.value = String(next);
    custom.dataset.ttl = String(next);
    output.textContent = format(next);
    output.setAttribute('aria-label', zh() ? `自定义时长 ${format(next)}` : `Custom duration ${format(next)}`);
    custom.textContent = zh() ? '自定义' : 'Custom';
    slider.setAttribute('aria-label', zh() ? '自定义访问时长' : 'Custom access duration');
    if (fill) fill.style.setProperty('--duration-progress', `${((next - MIN) / (MAX - MIN)) * 100}%`);

    if (feedback) window.RemoteGateFeedback?.detent?.((next - MIN) / (MAX - MIN));
    if (commit) custom.click();
  }

  function bind() {
    const ui = ensureUi();
    if (!ui?.slider) return;
    const {root, slider, custom} = ui;
    let lastStep = Number(slider.value || DEFAULT) / STEP;

    root.addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      const isCustom = button.id === 'ttl-custom-button';
      setPanelOpen(isCustom);
      if (isCustom) syncValue(custom.dataset.ttl || slider.value || DEFAULT);
    });

    slider.addEventListener('input', () => {
      const value = Number(slider.value || DEFAULT);
      const step = value / STEP;
      const changed = step !== lastStep;
      lastStep = step;
      syncValue(value, {commit: true, feedback: changed});
    });

    slider.addEventListener('change', () => window.RemoteGateFeedback?.haptic?.(9));
    window.addEventListener('remote-gate-language', () => syncValue(slider.value));
    syncValue(slider.value || DEFAULT);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();

  window.RemoteGateDuration = {format, min: MIN, max: MAX, step: STEP};
})();
