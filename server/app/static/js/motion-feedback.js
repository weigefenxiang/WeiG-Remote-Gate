(() => {
  const SOUND_KEY = 'weig-remote-gate:feedback-sound';
  const HAPTIC_KEY = 'weig-remote-gate:feedback-haptic';
  let audioContext = null;

  const readBool = (key, fallback = true) => {
    const value = localStorage.getItem(key);
    if (value === '0') return false;
    if (value === '1') return true;
    return fallback;
  };

  const state = {
    sound: readBool(SOUND_KEY, true),
    haptic: readBool(HAPTIC_KEY, true)
  };

  function ensureAudio() {
    if (!state.sound) return null;
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return null;
    if (!audioContext) audioContext = new AudioContext();
    if (audioContext.state === 'suspended') audioContext.resume().catch(() => {});
    return audioContext;
  }

  function tick(strength = 1) {
    if (!state.sound) return;
    const context = ensureAudio();
    if (!context || context.state !== 'running') return;

    const now = context.currentTime;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const highpass = context.createBiquadFilter();
    oscillator.type = 'triangle';
    oscillator.frequency.setValueAtTime(1180 + Math.min(1, Math.max(0, strength)) * 260, now);
    oscillator.frequency.exponentialRampToValueAtTime(620, now + 0.026);
    highpass.type = 'highpass';
    highpass.frequency.value = 420;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.026, now + 0.003);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.032);
    oscillator.connect(highpass);
    highpass.connect(gain);
    gain.connect(context.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.036);
  }

  function haptic(duration = 7) {
    if (!state.haptic || typeof navigator.vibrate !== 'function') return;
    try { navigator.vibrate(Math.max(1, Math.min(12, Number(duration) || 7))); } catch (_) {}
  }

  function detent(strength = 1) {
    tick(strength);
    haptic(7);
  }

  function setSound(value) {
    state.sound = Boolean(value);
    localStorage.setItem(SOUND_KEY, state.sound ? '1' : '0');
    syncControls();
    if (state.sound) tick(0.45);
  }

  function setHaptics(value) {
    state.haptic = Boolean(value);
    localStorage.setItem(HAPTIC_KEY, state.haptic ? '1' : '0');
    syncControls();
    if (state.haptic) haptic(8);
  }

  function ensureControls() {
    const sheet = document.getElementById('utility-sheet');
    if (!sheet || document.getElementById('feedback-sound')) return;
    const signout = sheet.querySelector('[data-action="logout"]');
    const group = document.createElement('div');
    group.className = 'utility-group feedback-settings';
    group.innerHTML = `
      <span class="label">Interaction feedback</span>
      <div class="feedback-setting-row">
        <span>Sound</span>
        <div class="mini-switch utility-switch" id="feedback-sound" role="group" aria-label="Sound feedback">
          <button type="button" data-feedback-sound="on">On</button>
          <button type="button" data-feedback-sound="off">Off</button>
        </div>
      </div>
      <div class="feedback-setting-row">
        <span>Haptics</span>
        <div class="mini-switch utility-switch" id="feedback-haptic" role="group" aria-label="Haptic feedback">
          <button type="button" data-feedback-haptic="on">On</button>
          <button type="button" data-feedback-haptic="off">Off</button>
        </div>
      </div>`;
    if (signout) sheet.insertBefore(group, signout);
    else sheet.append(group);
  }

  function syncGroup(root, enabled, attr) {
    root?.querySelectorAll(`[${attr}]`).forEach((button) => {
      const desired = button.getAttribute(attr) === 'on';
      const active = desired === enabled;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function syncControls() {
    syncGroup(document.getElementById('feedback-sound'), state.sound, 'data-feedback-sound');
    syncGroup(document.getElementById('feedback-haptic'), state.haptic, 'data-feedback-haptic');
  }

  function bind() {
    ensureControls();
    document.getElementById('feedback-sound')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-feedback-sound]');
      if (!button) return;
      setSound(button.dataset.feedbackSound === 'on');
    });
    document.getElementById('feedback-haptic')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-feedback-haptic]');
      if (!button) return;
      setHaptics(button.dataset.feedbackHaptic === 'on');
    });
    document.addEventListener('pointerdown', ensureAudio, {once: true, passive: true});
    syncControls();
  }

  const api = window.RemoteGateFeedback || {};
  api.tick = tick;
  api.haptic = haptic;
  api.detent = detent;
  api.setSound = setSound;
  api.setHaptics = setHaptics;
  Object.defineProperties(api, {
    soundEnabled: {configurable: true, get: () => state.sound},
    hapticsEnabled: {configurable: true, get: () => state.haptic}
  });
  window.RemoteGateFeedback = api;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();
})();
