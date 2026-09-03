(() => {
  const KEY = 'remote-gate:plan-preferences:v1';
  const MODES = ['ipv4', 'ipv6', 'dual'];
  const FAMILIES = ['ipv4', 'ipv6'];
  const controls = window.RemoteGateGateControls;
  if (!controls?.bind || !controls?.render) return;

  let context = null;
  let wireguardRestoreDone = false;
  const runtimeWireguards = {};
  const originalBind = controls.bind.bind(controls);
  const originalRender = controls.render.bind(controls);

  function safeText(value, maximum = 128) {
    const text = String(value || '').trim();
    return text && text.length <= maximum ? text : '';
  }

  function cleanSelection(value) {
    if (!value || typeof value !== 'object') return null;
    const selection = {
      value: safeText(value.value, 256),
      wan: safeText(value.wan, 64),
      method: safeText(value.method, 32),
    };
    return selection.value ? selection : null;
  }

  function emptyPreferences() {
    return {schema: 1, lastFamily: '', lastWireguard: '', endpoints: {}};
  }

  function loadPreferences() {
    let raw;
    try {
      raw = JSON.parse(localStorage.getItem(KEY) || '{}');
    } catch (_) {
      return emptyPreferences();
    }
    if (!raw || typeof raw !== 'object' || Number(raw.schema || 0) !== 1) return emptyPreferences();
    const result = emptyPreferences();
    result.lastFamily = MODES.includes(raw.lastFamily) ? raw.lastFamily : '';
    result.lastWireguard = safeText(raw.lastWireguard, 64);
    const endpoints = raw.endpoints && typeof raw.endpoints === 'object' ? raw.endpoints : {};
    FAMILIES.forEach((family) => {
      const item = endpoints[family];
      const selection = cleanSelection(item?.selection);
      const wireguard = safeText(item?.wireguard, 64);
      if (selection && wireguard) result.endpoints[family] = {wireguard, selection};
    });
    return result;
  }

  function savePreferences(value) {
    try {
      localStorage.setItem(KEY, JSON.stringify(value));
    } catch (_) {
      // Browser storage is a convenience only; runtime authority never depends on it.
    }
  }

  function modeHasSavedIntent(saved, mode) {
    if (mode === 'dual') return FAMILIES.every((family) => saved.endpoints[family]?.wireguard === saved.lastWireguard);
    return FAMILIES.includes(mode) && saved.endpoints[mode]?.wireguard === saved.lastWireguard;
  }

  function normalizeSavedMode(saved) {
    if (saved.lastFamily && modeHasSavedIntent(saved, saved.lastFamily)) return;
    const fallback = FAMILIES.find((family) => saved.endpoints[family]);
    saved.lastFamily = fallback || '';
    saved.lastWireguard = fallback ? saved.endpoints[fallback].wireguard : '';
  }

  function hydrateState(nextContext) {
    context = nextContext;
    const state = context?.state;
    if (!state) return;
    if (!state.endpointSelections || typeof state.endpointSelections !== 'object') state.endpointSelections = {};
    if (!state.endpointManualSelections || typeof state.endpointManualSelections !== 'object') state.endpointManualSelections = {};

    const saved = loadPreferences();
    if (!saved.lastWireguard) return;
    let hydrated = false;
    FAMILIES.forEach((family) => {
      const item = saved.endpoints[family];
      if (!item || item.wireguard !== saved.lastWireguard) return;
      state.endpointSelections[family] = {...item.selection};
      state.endpointManualSelections[family] = true;
      runtimeWireguards[family] = item.wireguard;
      hydrated = true;
    });
    if (hydrated && saved.lastFamily && modeHasSavedIntent(saved, saved.lastFamily)) {
      state.family = saved.lastFamily;
      state.familyManual = true;
    }
  }

  function discardWireguard(saved, wireguard) {
    FAMILIES.forEach((family) => {
      if (saved.endpoints[family]?.wireguard === wireguard) delete saved.endpoints[family];
      if (runtimeWireguards[family] === wireguard) {
        delete runtimeWireguards[family];
        if (context?.state?.endpointSelections?.[family] && context?.state?.endpointManualSelections?.[family]) {
          delete context.state.endpointSelections[family];
          context.state.endpointManualSelections[family] = false;
        }
      }
    });
    if (saved.lastWireguard === wireguard) {
      saved.lastWireguard = '';
      saved.lastFamily = '';
      if (context?.state) context.state.familyManual = false;
    }
    savePreferences(saved);
  }

  function restoreWireguard() {
    if (wireguardRestoreDone || !context) return;
    const select = document.getElementById('wg-select');
    if (!select || !select.options.length) return;
    const saved = loadPreferences();
    const wireguard = saved.lastWireguard;
    if (!wireguard) {
      wireguardRestoreDone = true;
      return;
    }
    const exists = [...select.options].some((option) => option.value === wireguard);
    if (!exists) {
      discardWireguard(saved, wireguard);
      wireguardRestoreDone = true;
      return;
    }
    if (select.value !== wireguard) {
      select.value = wireguard;
      context.onWireGuardChange?.();
    }
    wireguardRestoreDone = true;
  }

  function reconcileRuntimeWireguard() {
    const state = context?.state;
    const wireguard = safeText(document.getElementById('wg-select')?.value, 64);
    if (!state || !wireguard) return;
    FAMILIES.forEach((family) => {
      if (!state.endpointManualSelections?.[family]) {
        delete runtimeWireguards[family];
        return;
      }
      const boundWireguard = safeText(runtimeWireguards[family], 64);
      if (!boundWireguard || boundWireguard === wireguard) return;
      delete state.endpointSelections[family];
      state.endpointManualSelections[family] = false;
      delete runtimeWireguards[family];
    });
  }

  function persistFamily(family) {
    if (!context || !FAMILIES.includes(family)) return;
    const state = context.state || {};
    const saved = loadPreferences();
    const selection = cleanSelection(state.endpointSelections?.[family]);
    const manual = Boolean(state.endpointManualSelections?.[family]);
    const wireguard = safeText(document.getElementById('wg-select')?.value, 64);

    if (!manual || !selection || !wireguard) {
      delete runtimeWireguards[family];
      delete saved.endpoints[family];
      normalizeSavedMode(saved);
      savePreferences(saved);
      return;
    }

    runtimeWireguards[family] = wireguard;
    saved.endpoints[family] = {wireguard, selection};
    const mode = MODES.includes(state.family) ? state.family : family;
    saved.lastFamily = mode === 'dual' && !FAMILIES.every((item) => saved.endpoints[item]?.wireguard === wireguard) ? family : mode;
    saved.lastWireguard = wireguard;
    savePreferences(saved);
  }

  controls.bind = (nextContext) => {
    hydrateState(nextContext);
    const originalOnWireGuardChange = nextContext?.onWireGuardChange;
    if (nextContext && typeof nextContext === 'object') {
      nextContext.onWireGuardChange = (...args) => {
        reconcileRuntimeWireguard();
        return originalOnWireGuardChange?.(...args);
      };
    }
    return originalBind(nextContext);
  };

  controls.render = (currentData) => {
    restoreWireguard();
    reconcileRuntimeWireguard();
    return originalRender(currentData);
  };

  window.addEventListener('remote-gate-endpoint-selection', (event) => {
    persistFamily(String(event?.detail?.family || ''));
  });

  window.RemoteGatePlanPreferences = {
    key: KEY,
    load: loadPreferences,
    clear() {
      try { localStorage.removeItem(KEY); } catch (_) {}
    },
  };
})();
