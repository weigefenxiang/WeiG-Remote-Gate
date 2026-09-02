---
version: 8
name: WeiG-Remote-Gate
description: "A dense, tactile, adaptive network-security workspace with standardized spatial depth, modular controls, and a distinct Wei.G security identity."
---

# 1. Product philosophy

WeiG-Remote-Gate is a security control surface, not a marketing page.

Principles:
- Console first; marketing copy never pushes controls below the fold unnecessarily.
- Calm before flashy.
- One primary security action at a time.
- Depth communicates hierarchy and interaction.
- Animation explains state transitions; it never exists only for spectacle.
- Security state is always expressed by text and icon, never color alone.
- Never expose secrets, tokens or private keys in the UI.
- Never trade readability for an artificial one-screen requirement.
- Prefer larger typography and tighter information structure over tiny text and excessive whitespace.

## Design review gate

Every visual/layout/component change must be reviewed against the design-system approach documented by `awesome-design-md` before implementation: hierarchy, spacing, typography, surface depth, interaction state, motion, responsive behavior and accessibility are considered together rather than patched independently.

Reference means design discipline, not copying another project's appearance. WeiG Remote Gate keeps its own restrained security-console identity.

No visual change is complete until the affected component has:
- a reusable component contract;
- rest / hover / pressed / selected / disabled states where applicable;
- mobile and desktop behavior;
- reduced-motion behavior;
- automated regression coverage when the interaction is testable.

# 2. Workspace model

Canonical card priority:
1. Remote Gate
2. Current Client
3. WireGuard
4. Multi-WAN
5. Activity
6. System

Wide desktop uses two semantic zones:
- `Main Canvas`: Remote Gate, WireGuard and Multi-WAN by default.
- `Utility Rail`: Current Client, System and Activity by default.

Rules:
- Activity must not consume a full desktop row by default.
- Arrange mode may move cards between desktop zones.
- Persistence stores zone, order and preset size only; never secrets.
- Mobile ignores saved desktop placement and renders Gate, Client, WireGuard, WAN, Activity, System.
- Mobile never reuses desktop card spans or drag placement.
- Whole-page horizontal scrolling is forbidden.

# 3. Surface and elevation system

Depth is a design-system primitive, not a per-component decoration.

Required semantic surfaces:
- `canvas`
- `surface-1`
- `surface-2`
- `surface-raised`
- `surface-recessed`

Required elevation semantics:
- `--depth-z0`
- `--depth-z1`
- `--depth-z2`
- `--depth-z3`
- contact / ambient shadow
- rim light
- inner highlight
- recessed shadow

Visual hierarchy:
1. Canvas.
2. Workspace plane.
3. Card chassis.
4. Recessed field.
5. Raised control.
6. Selected / active surface.

Desktop hover lift should remain around 1-3px. Pressed controls move down about 1px and compress their shadow. Never use exaggerated scaling, uncontrolled neon glow or cyberpunk decoration.

# 4. Typography

Use native system fonts only:
`Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`

Monospace:
`"SFMono-Regular", Consolas, "Liberation Mono", monospace`

Targets:
- desktop console heading: 28-34px / 700+
- mobile console heading: 22-24px
- card title: 19-22px
- important value / IP: 17-21px
- body: 14-16px
- label: 12-14px
- button: 15-16px

Do not use 9-11px as the normal reading size for primary information.

## IPv6 hard rule

A complete IPv6 address must remain on exactly one line. It must never wrap, ellipsize, truncate or replace middle groups with `...`. Dynamic font fitting may reduce only that value's font size as the available width changes.

## NetworkIdentityText

Machine-identifying network values use one shared responsive text primitive. This includes public WireGuard endpoints, Current Client addresses, authorization sources, Access Endpoint WAN identities and addresses, EndpointPicker cards, Multi-WAN/WAN PATH identities and addresses, and equivalent future network identifiers.

The only fitting engine is `server/app/static/js/fit-text.js`. Do not create IPv6-, Endpoint-, WAN- or Dual-specific fitting utilities.

Canonical contract:
- new consumers declare `fit-single-line` and a semantic `data-fit-profile` when the default is not sufficient;
- `hero` is for the current public WireGuard Endpoint;
- `value` is for primary IP/address values;
- `identity` is for WAN/interface identity strings;
- `compact` is for EndpointPicker addresses and similarly dense controls;
- existing legacy selectors may be adapted centrally by `fit-text.js`, but new components must use the explicit contract;
- fitting starts at the normal semantic type size and only shrinks when the rendered value would overflow;
- a complete network identity must stay on one line and must not use ellipsis, truncation or middle replacement;
- fitting may use an emergency smaller size only when necessary to preserve the complete value inside the viewport;
- containing flex/grid items must permit shrinking (`min-width: 0` / `minmax(0, 1fr)` as appropriate);
- whole-page horizontal overflow is a contract failure, not an acceptable fallback.

Dual-stack presentation is not a separate text system. IPv4, IPv6, same-WAN Dual and split-WAN Dual all consume the same NetworkIdentityText primitive.

# 5. Brand identity

The canonical product asset is:

`server/app/static/Wei.G.ico`

The same asset is used for favicon and the persistent header brand control. Do not replace it with a text `WG` approximation or generate a second icon.

`BrandIcon` rules:
- rounded chassis around the canonical image;
- subtle top highlight, rim and contact shadow;
- restrained hover lift on fine-pointer devices;
- pressed compression on touch/pointer activation;
- clicking the header BrandIcon opens the Utility Sheet;
- the image remains decorative inside the already-labelled semantic button.

# 6. Buttons and segmented controls

Primary action target: approximately 50-54px high. Normal touch controls are 44px-class or larger on mobile.

Segmented controls use a recessed base; the selected item appears physically raised. IP Family, Access Scope, TTL presets, Language, Theme and feedback toggles share this interaction language.

Unavailable IP families remain visible when that helps explain device capability, but are disabled before interaction. Dual is disabled when either required Gate family capability is unavailable.

# 7. EndpointPicker and PathCard

The browser-native `<select>` may remain as an internal state bridge, but it must not be the visible endpoint/exit chooser.

`EndpointPicker` is the one interaction framework for both Access Endpoint and Internet Exit. Do not create separate Dual, IPv6, Mapped or Exit picker systems.

Desktop:
- opens a compact spatial picker/popover appropriate to the available viewport.

Mobile:
- opens a bottom sheet;
- uses a backdrop and safe-area padding;
- options are full-width tactile cards.

## PathCard

`PathCard` is the one option-card presentation primitive. It contains one or two `FamilyPathBlock` records:

```text
PathCard
  -> FamilyPathBlock[1] for IPv4 or IPv6
  -> FamilyPathBlock[2] for Dual
```

A `FamilyPathBlock` has exactly these semantic fields:
- family (`IPv4` / `IPv6`);
- WAN identity;
- optional Access role;
- complete machine value (endpoint/address).

Canonical Access roles are structured values, not text inferred by the renderer:

```text
Public Direct
Global Direct
Mapped
Try
Relay
```

`Recommended` / `推荐` is plan-ranking metadata and is separate from the Access role. Recommendation must never be reconstructed from role text, option order or visible labels.

For a single-family Access trigger, keep the selected path compact and two-line. The first line is:

```text
<WAN>   <family>   <flexible space>   <concise reachability when useful>
```

For `Public Direct`, the trigger may shorten only the trailing presentation token to `Public`; the structured role remains `Public Direct`. The second line is always the complete endpoint identity.

Example trigger:

```text
WAN2   IPv4                         Public
223.73.44.6:51820
```

The corresponding picker option keeps recommendation and role distinct:

```text
IPv4   WAN2              Recommended   Public Direct
223.73.44.6:51820
```

Mapped Access uses the same two-line block:

```text
IPv4   WAN                              Mapped
223.73.44.6:7179
```

Dual Access is always two blocks / four information lines:

```text
IPv4   WAN2                        Public Direct
223.73.44.6:7179
IPv6   WAN                         Global Direct
[240e:....]:51820
```

Same-WAN and split-WAN Dual use the exact same DOM/component structure. The WAN values communicate the topology, so do not repeat `Dual`, `Split WAN` or `Split Exit` inside the card.

Internet Exit consumes the same PathCard renderer. Exit rows show family, WAN and observed/known address value; they do not expose `Private/CGNAT` as a product role. A private/CGNAT local IPv4 WAN may still be a valid outbound exit when routing capability is valid.

Structured ownership is mandatory:
- `gate-controls.js` is the browser owner of Access Endpoint eligibility, ranking, option creation and PathCard row data;
- it writes structured `data-path-rows` and recommendation metadata (`data-path-primary`) onto the internal select options;
- `endpoint-picker.js` is render/interaction only: it consumes those structured records and must not parse `option.textContent`, infer Access roles from strings/order, or use `MutationObserver` to rediscover policy state;
- `app.js` must not re-filter, re-rank or relabel Access Endpoint options.

Responsive rules:
- family and optional role remain compact anchors;
- recommendation and role remain visually distinct tokens;
- WAN identity uses `NetworkIdentityText` `identity` profile;
- endpoint/address value uses `NetworkIdentityText` `compact` profile;
- the complete IPv6 value stays one line and is fitted rather than truncated;
- mobile and desktop use the same semantic DOM; only spacing/surface behavior changes;
- a 320px viewport must not cause whole-page horizontal overflow.

Opening/closing uses short transform/opacity motion. Essential information must never depend on hover.

# 8. Client Source model

IPv4 and IPv6 are independent per-session records. Observing or probing one family must never delete the other.

Priority:
- direct Cloudflare observation: `verified`;
- network/carrier probe: `heuristic` and shorter lived.

Automatic family recommendation prefers IPv4 when both are currently usable. This is a recommendation only: once the user manually selects IPv6, periodic refresh must not steal the selection while IPv6 remains usable.

The Current Client card displays both families independently and labels their provenance/freshness. Browser-local UI preferences never become authorization authority.

# 9. Remote Gate orb

The Gate orb is both visual anchor and, while CLOSED, a primary activation control.

CLOSED:
- entire orb is a semantic button;
- Enter/Space, pointer and touch call the same `activate()` path as the main button.

AUTHORIZING:
- interaction locked; progress motion may be shown.

OPEN:
- orb is status-only; explicit `Close access now` remains the destructive action.

ERROR:
- show textual reason and use the normal activation path for retry.

The orb and main Activate button share exactly the same `canActivate()` conditions: selected family has a current session source, selected family has an eligible endpoint, selected WireGuard exists, the required Gate capability is ready, no command is pending and UI is not busy.

# 10. Access Scope

Two scopes exist:
- `WireGuard only` — recommended default; Ping remains closed.
- `WireGuard + Ping` — additionally permits Echo Request from the selected source.

IPv6 Ping means only ICMPv6 Echo Request. Remote Gate never blanket-drops ICMPv6 control traffic such as NDP, RA or Packet Too Big.

# 11. DurationControl

Preset buttons are exactly:
- `1m`
- `5m`
- `15m`
- `30m`
- `Custom`

There is no `1h` preset.

Custom mode uses `DurationCrown`:
- minimum 0.5h;
- maximum 12h;
- exact 0.5h detents;
- a recessed rail and a raised tactile thumb;
- visible current value;
- keyboard-accessible range input underneath the visual treatment.

Server and OpenWrt firewall independently validate the same duration contract. The browser is never the final authority.

# 12. MotionFeedback

`motion-feedback.js` owns reusable interaction feedback.

Duration detents may provide:
- a short Web Audio synthesized mechanical tick;
- a short `navigator.vibrate()` pulse when available.

Rules:
- audio starts only after a user interaction permits AudioContext playback;
- sound and haptics are independently switchable in Utility Sheet;
- preferences are browser-local only;
- unsupported vibration is silently ignored;
- feedback never blocks the primary action;
- `prefers-reduced-motion` reduces visual motion, while user feedback toggles control sound/haptics.

# 13. WireGuard and WAN presentation

WireGuard remains a professional term and is not translated. Never expose private keys. A Handshake alone does not prove LAN routing health.

Multi-WAN cards may show network facts such as Public, Private/CGNAT, Global IPv6, NAT egress probe and mapped endpoint information. These are diagnostics/facts; they do not automatically become Access Endpoint or Internet Exit product labels.

Remote Gate remains INPUT-only. FORWARD, DNAT, UPnP, NAT-PMP and qBittorrent forwarding remain outside Gate ownership.

# 14. Activity stream

Default Activity is one event per line. Current-day entries show compact time, summaries stay one line where practical, and details may expand on demand. Activity/System typography must remain readable in the Utility Rail.

# 15. Language and theme

Source templates are English-first. Selection precedence: explicit browser-local choice, browser language, English fallback. Professional networking terms may remain English in Chinese UI.

Theme values: `auto`, `light`, `dark`. Theme bootstrap executes before first paint; persist only explicit user choice.

Mobile persistent header contains BrandIcon, product name and the circular resolved Light/Dark toggle. Language, full Appearance, interaction feedback and Sign out live in Utility Sheet.

# 16. Responsive behavior

>= 1200px:
- Main Canvas + Utility Rail;
- desktop-readable typography;
- endpoint picker uses a compact desktop interaction surface.

768-1199px:
- responsive flow layout;
- no desktop-zone span leakage.

< 768px:
- canonical single-column flow;
- drag disabled;
- 44px-class primary touch targets;
- EndpointPicker becomes a bottom sheet;
- custom duration remains comfortably draggable without horizontal page overflow;
- full network identities, including IPv6 endpoints, remain one line by dynamic fitting;
- Dual PathCard remains two FamilyPathBlocks/four information lines rather than collapsing into one overloaded line.

# 17. Accessibility

- WCAG AA text contrast.
- `:focus-visible` on interactive elements.
- Respect `prefers-reduced-motion`.
- Never rely on color alone.
- Dialog/sheet components support Escape, backdrop close and focus containment.
- Selected states expose ARIA state.
- Range control remains keyboard operable.
- CLOSED Gate orb remains a semantic button.
- Disabled family controls expose disabled state and an explanatory reason.

# 18. Module boundaries

CSS:
- `tokens.css`: colors, typography, spacing, radius and elevation tokens.
- `base.css`: reset, global typography and accessibility.
- `components.css`: established reusable controls/surfaces.
- `layout.css`: workspace flow/zones and responsive structure.
- `dashboard.css`: dashboard data presentation only.
- `spatial.css`: card/workspace spatial layer.
- `interaction.css`: BrandIcon, EndpointPicker/PathCard, DurationCrown and feedback-setting interaction surfaces.

JavaScript:
- `theme-bootstrap.js`: pre-paint theme/favicon bootstrap and early component asset loading.
- `theme.js`: theme state.
- `utility-panel.js`: Utility Sheet lifecycle/focus.
- `i18n.js`: language state/dictionaries.
- `fit-text.js`: the only NetworkIdentityText/single-line fitting engine; owns semantic profiles, resize observation and dynamic-content refitting.
- `workspace.js`: card flow/zones/order/drag persistence.
- `activity.js`: event summaries/expansion.
- `motion-feedback.js`: sound/haptic feedback abstraction.
- `client-sources.js`: missing-family IPv4/IPv6 probe completion.
- `endpoint-picker.js`: the one custom picker and PathCard renderer for Access Endpoint and Internet Exit; render/interaction only, with no policy inference from label text or DOM mutation observation.
- `duration-control.js`: presets-to-Custom bridge, range/detent/feedback.
- `gate-controls.js`: Family/Scope/TTL state, capability/eligibility, AccessPlan, InternetExitPlan, Access Endpoint option creation, structured PathCard view-model data and the single activation path.
- `app.js`: API state, refresh and general data rendering orchestration; it does not own Access Endpoint filtering/ranking/labels/options.

Do not put component-specific interaction code back into `app.js` when a dedicated module owns it. Do not create separate Dual/IPv6/Mapped/Exit picker, card or fitting frameworks.

# 19. Do / Don't

Do:
- keep the console calm, tactile, compact and data-first;
- use the canonical Wei.G asset;
- preserve both observed IP families;
- make recommendation separate from user choice and from Access role;
- reuse PathCard, component/elevation/motion/text-fit primitives;
- keep AccessPlan independent from InternetExitPlan;
- derive WireGuard service port from runtime service identity;
- test mobile and desktop interactions before release.

Don't:
- expose a browser-native Endpoint dropdown as the final UI;
- show Private/CGNAT as a selectable public Access Endpoint;
- expose Private/CGNAT as an Internet Exit product mode/role;
- make `app.js` a second Access Endpoint policy/label owner;
- let EndpointPicker parse option display text or observe mutations to infer policy semantics;
- repeat `Dual`, `Split WAN` or `Split Exit` when PathCard rows already express the topology;
- add a 1h preset to the duration group;
- allow Custom duration above 12h or off the 0.5h detents;
- delete IPv6 merely because IPv4 becomes available, or vice versa;
- add decorative neon everywhere;
- force a one-screen layout by globally shrinking typography;
- allow whole-page horizontal scrolling;
- create per-component IPv6/WAN/Endpoint fitting utilities;
- hard-code WAN2, wg0 or UDP 51820 in frontend business logic;
- create a second activation/planning implementation;
- expose WRITE_TOKEN, session secret or WireGuard private keys.
