---
version: 3
name: WeiG-Remote-Gate
description: "A dense, tactile, adaptive network-security workspace with standardized spatial depth, large readable controls, and a distinct WeiG security identity."
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
- No fake diagnostics. Do not label HTTP timing as ICMP ping.
- Never expose secrets, tokens or private keys in the UI.
- Never trade readability for an artificial one-screen requirement.
- Prefer larger typography and tighter information structure over tiny text and excessive whitespace.

# 2. Workspace model

Desktop uses an adaptive dense card workspace rather than a fixed dashboard grid.

Canonical card priority:
1. Remote Gate
2. Current Client
3. WireGuard
4. Public WAN
5. Activity
6. System

Desktop behavior:
- Use a 12-column grid with `grid-auto-flow: dense`.
- Wide windows should use available space instead of leaving large empty regions.
- Narrow windows reflow from 3 columns to 2 columns and then 1 column.
- Cards may naturally extend below the current viewport; vertical scrolling is valid.
- The page must not gain whole-page horizontal scrolling.
- Do not shrink all typography simply to force every card into the viewport.

Canonical wide-screen layout:
- Remote Gate: 8 columns.
- Current Client: 4 columns.
- WireGuard: 4 columns.
- Public WAN: 4 columns.
- System: 4 columns.
- Activity: full row when its size is `Wide`.

Desktop arrangement mode:
- Arrangement is opt-in; normal controls must never accidentally drag cards.
- Cards may be reordered by drag-and-drop.
- Accessible non-drag alternatives must exist for moving cards earlier/later.
- Card sizes use only `Compact`, `Normal`, and `Wide`; arbitrary pixel resizing is not allowed.
- Layout preferences are browser-local only and must never contain secrets or be uploaded to the server.
- A reset action restores the canonical default order and sizes.

Mobile behavior:
- Drag/reorder mode is disabled.
- Mobile uses the canonical fixed priority order.
- Touch scrolling must never conflict with card rearrangement.
- Header controls reflow below the brand; controls must never obscure the product name.

# 3. Color and surface tokens

Light and dark palettes remain centralized in `tokens.css`.

Required semantic surfaces:
- `canvas`
- `surface-1`
- `surface-2`
- `surface-raised`
- `surface-recessed`

Required border semantics:
- normal hairline
- strong hairline
- hover border
- active border

No component may invent its own unrelated depth language.

# 4. Typography

Use native system fonts only:

`Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`

Monospace:

`"SFMono-Regular", Consolas, "Liberation Mono", monospace`

Desktop targets:
- console heading: 28-34px / 700+
- card title: 19-22px / 650-750
- important value / IP: 18-21px
- body: 14-16px
- label: 12-13px
- button: 15-16px

Mobile targets:
- console heading: 22-24px
- card title: 19-21px
- important value: 17-19px
- body: 14-15px
- label: 12-13px
- button: 15-16px

Do not use 9-11px as the normal reading size for primary information.

## IPv6 hard rule

A complete IPv6 address must:
- remain on exactly one line;
- never wrap;
- never be ellipsized;
- never be truncated;
- never replace middle groups with `...`.

The UI must fit the full value by dynamically reducing only that value's font size. Width changes from responsive layout, card size changes, and window resizing must trigger a re-fit.

# 5. Spacing

Use a 4px base rhythm.

Desktop workspace max-width: 1500px.
Mobile horizontal padding: 12-16px.
Desktop horizontal padding: 22-28px.

Density rule:
- reduce duplicate copy, excessive card padding, and oversized vertical gaps before reducing readable font sizes.

# 6. Radius

- xs: 8px
- sm: 12px
- md: 16px
- lg: 22px
- xl: 26px
- pill: 999px

# 7. Standardized elevation system

Depth is a design-system primitive, not a per-component decoration.

Required tokens:
- `--elevation-card-rest`
- `--elevation-card-hover`
- `--elevation-card-pressed`
- `--elevation-control-rest`
- `--elevation-control-hover`
- `--elevation-control-pressed`
- `--elevation-recessed`
- `--highlight-top`
- `--highlight-control`

Visual layers:
1. Canvas.
2. Workspace.
3. Card.
4. Control.
5. Hover / active / pressed state.

Desktop card hover:
- maximum vertical lift around 2-3px;
- stronger but restrained shadow;
- slightly stronger border.

Control hover:
- maximum vertical lift around 1-2px.

Pressed:
- move down around 1px;
- compress the shadow so the control feels physically pressed.

Never use exaggerated scale animation, neon glow, or cyberpunk styling.

# 8. Buttons and segmented controls

Primary button target:
- desktop/mobile height around 50-54px;
- text 15-16px;
- raised surface with a top highlight;
- hover increases elevation;
- pressed state visibly compresses.

Normal controls:
- height around 42-46px desktop;
- 44-48px mobile.

Segmented controls:
- use a recessed base;
- the selected option appears physically raised from the base;
- unselected options may rise slightly on hover;
- pressed items return toward the base.

Language, Theme, TTL and IP Family share the same component behavior.

# 9. Remote Gate orb

The Gate orb is both the visual anchor and, while CLOSED, a primary activation control.

CLOSED:
- the entire orb is a semantic button;
- mouse hover raises the core and strengthens the ring;
- keyboard Enter/Space activates it;
- touch press uses the same action;
- the orb and the main Activate button call the exact same activation function.

AUTHORIZING:
- interaction is locked;
- progress motion may be shown.

OPEN:
- the orb is status-only and must not close access on an accidental click;
- explicit `Close access now` remains the destructive action.

ERROR:
- communicate the error textually;
- retry remains available through the normal activation path when safe.

The orb and main Activate button must share the same `canActivate()` conditions:
- trusted IPv4 request for the currently validated IPv4 path;
- Public WAN available;
- WireGuard interface available;
- no pending command;
- UI not busy.

# 10. Client address presentation

The Current Client card should display both IPv4 and IPv6 when observed.

Rules:
- current request family is explicitly labeled;
- browser-local address memory is display-only;
- remembered addresses are labeled as previously observed;
- Gate authorization identifies the trusted address actually authorized;
- IPv6 follows the single-line hard rule.

# 11. WireGuard presentation

WireGuard remains a professional term and is not translated.

Show at minimum:
- Interface
- Listen port
- Latest Handshake
- Traffic
- current connection status
- LAN access guidance when full route diagnostics are not available

Never expose a WireGuard private key.
Never imply LAN routing is healthy only because a Handshake exists.

# 12. Activity stream

The default Activity list is a dense single-line event stream.

Rules:
- one event per line by default;
- current-day events show only `HH:mm:ss`;
- older events use a compact date+time form;
- summary fields remove redundant low-value data;
- the summary remains one line and may dynamically fit;
- clicking an event may expand a secondary full-detail line;
- do not spend three default rows on title, metadata, and timestamp.

# 13. Language behavior

Source templates are English-first.

Selection precedence:
1. explicit browser-local user choice;
2. browser language detection;
3. English fallback.

Simplified Chinese is selected for `zh`-class browser languages.

Professional terms may remain English in Chinese UI, including:
`IP`, `IPv4`, `IPv6`, `WireGuard`, `Endpoint`, `Public WAN`, `TTL`, `Client`, `Server`, `Firewall`, `Backend`, `Handshake`, `Token`, and `Dual-stack`.

# 14. Theme behavior

Default theme is `auto`.
Supported values: `auto`, `light`, `dark`.

Auto follows `prefers-color-scheme` live.
Persist only an explicit user choice.
Theme bootstrap executes before first paint.

# 15. Responsive behavior

>= 1440px:
- dense 12-column workspace;
- large readable typography;
- primary workspace should normally require little or no scrolling.

1024-1439px:
- adaptive 2-3 column workspace;
- preserve desktop-readable typography.

768-1023px:
- 2 columns when practical;
- vertical scrolling is expected when viewport height is limited;
- arrangement mode remains available.

< 768px:
- canonical single-column card order;
- arrangement controls disabled;
- brand occupies its own header row;
- Language and Theme controls move below the brand and use large centered segmented bars;
- primary controls use 44px-class or larger touch targets;
- no hover-dependent essential information;
- full IPv6 remains one line by dynamic font fitting.

# 16. Accessibility

- WCAG AA text contrast.
- `:focus-visible` ring on all interactive elements.
- Respect `prefers-reduced-motion`.
- Never rely on color only.
- Status changes use `aria-live=polite` where appropriate.
- Buttons remain keyboard operable.
- The CLOSED Gate orb is a semantic button.
- Dragging has a button-equivalent reordering path.

# 17. Module boundaries

CSS:
- `tokens.css`: color, typography, spacing, radius and elevation.
- `base.css`: reset, global typography and accessibility.
- `components.css`: buttons, segmented controls, inputs, badges and reusable surfaces.
- `layout.css`: workspace grid, card sizing, drag layout and responsive structure.
- `dashboard.css`: Gate, Client, WireGuard, WAN, Activity and System presentation only.

JavaScript:
- `theme-bootstrap.js`: pre-paint theme bootstrap.
- `theme.js`: theme interaction.
- `i18n.js`: language state and dictionaries.
- `fit-text.js`: long single-line fitting such as IPv6.
- `workspace.js`: card order, sizes, drag mode and local persistence.
- `gate-controls.js`: Gate orb, Activate, Close, TTL and IP Family interactions.
- `activity.js`: compact event summaries and expansion.
- `app.js`: API state, data refresh and render orchestration.

# 18. Do / Don't

Do:
- keep the dashboard calm, tactile, compact and data-first;
- make typography and controls comfortably readable;
- use standardized elevation tokens;
- use dense layout before shrinking content;
- preserve public IP readability;
- keep Gate activation deliberate even when the orb is clickable.

Don't:
- put HTTP/HTTPS probes on the home WAN;
- add decorative neon everywhere;
- force one-screen layout by shrinking all typography;
- allow whole-page horizontal scrolling;
- allow arbitrary pixel card resizing;
- hard-code WAN2, wg0 or UDP 51820 in frontend code;
- create a second activation implementation for the Gate orb;
- let the browser choose the IP address that gets authorized;
- expose WRITE_TOKEN, session secret or WireGuard private keys.
