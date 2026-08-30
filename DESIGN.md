---
version: 2
name: WeiG-Remote-Gate
description: "A calm, precise, adaptive network-security workspace. The visual language combines technical restraint, clear spatial hierarchy, restrained depth, and a distinct WeiG security identity. Effects communicate state; decoration never competes with security information."
---

# 1. Product philosophy

WeiG-Remote-Gate is a security control surface, not a marketing page.

Principles:
- Console first; marketing copy never pushes controls below the fold unnecessarily.
- Calm before flashy.
- One primary security action at a time.
- Depth through surfaces, hairlines, inner highlights and restrained shadows.
- Animation explains state transitions; it never exists only for spectacle.
- Security state is always expressed by text and icon, never color alone.
- No fake diagnostics. Do not label HTTP timing as ICMP ping.
- Never expose secrets, tokens or private keys in the UI.
- Never trade readability for an artificial one-screen requirement.

# 2. Workspace model

Desktop uses an adaptive card workspace rather than a fixed dashboard grid.

Default card priority:
1. Remote Gate
2. Current Client
3. WireGuard
4. Public WAN
5. Activity
6. System

Desktop behavior:
- Wide windows should show the primary workspace with minimal scrolling.
- Narrow windows reflow from 3 columns to 2 columns and then 1 column.
- Cards may naturally extend below the current viewport; vertical scrolling is valid.
- The page must not gain whole-page horizontal scrolling.
- Do not shrink all typography simply to force every card into the viewport.

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

# 3. Color tokens

## Light
- canvas: #F5F7FB
- canvas-elevated: #FFFFFF
- surface-1: rgba(255,255,255,.78)
- surface-2: rgba(255,255,255,.92)
- ink: #11131A
- ink-muted: #667085
- ink-subtle: #98A2B3
- hairline: rgba(17,19,26,.10)
- primary: #5965E8
- primary-hover: #6874F2
- success: #16A36A
- warning: #D8871A
- danger: #D84A4A

## Dark
- canvas: #090B10
- canvas-elevated: #0F1219
- surface-1: rgba(20,24,33,.78)
- surface-2: rgba(25,30,41,.94)
- ink: #F7F8FA
- ink-muted: #A8B0BE
- ink-subtle: #737C8C
- hairline: rgba(255,255,255,.10)
- primary: #7D86FF
- primary-hover: #9299FF
- success: #42C98A
- warning: #F0AA48
- danger: #FF6B6B

# 4. Typography

Use native system fonts only:
`Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`

Monospace:
`"SFMono-Regular", Consolas, "Liberation Mono", monospace`

- console heading: 25-34px / 700 / tight tracking
- section title: 17-22px / 650-720
- body: 13-16px / 400
- caption: 10-12px / 500-650
- numeric IP/status values use a monospace stack and tabular numerals where available
- desktop typography should remain comfortably larger than mobile typography

## IPv6 hard rule

A complete IPv6 address must:
- remain on exactly one line;
- never wrap;
- never be ellipsized;
- never be truncated;
- never replace middle groups with `...`.

The UI must fit the full value by dynamically reducing only that value's font size to a documented minimum. Width changes from responsive layout, card size changes, and window resizing must trigger a re-fit. Card padding may be reduced before reaching the minimum font size.

# 5. Spacing

4px base rhythm:
4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64

Desktop workspace max-width: 1500px.
Mobile horizontal padding: 12-16px.
Desktop horizontal padding: 22-28px.

# 6. Radius

- xs: 8px
- sm: 12px
- md: 16px
- lg: 22px
- xl: 28px
- pill: 999px

# 7. Depth

Four visual layers:
1. Ambient canvas.
2. Main surface.
3. Cards and panels.
4. Interactive controls.

Cards use:
- 1px hairline border
- soft outer shadow
- subtle inset top highlight
- restrained blur

Hover elevation: max translateY(-2px).
Pressed: translateY(1px).
Never use exaggerated scale transforms.
Never create a neon/cyberpunk visual language.

# 8. Buttons and segmented controls

Preserve the existing WeiG button language:
- rounded geometry
- subtle top highlight
- controlled depth
- clear active state
- no excessive glow

Primary:
- high contrast indigo
- 14px radius
- soft control shadow
- minimum touch height around 44-46px

Secondary:
- surface background + hairline
- no competing accent

Danger:
- red only for revoke/close/destructive actions

Segmented controls are preferred for small mutually exclusive choices such as Theme, Language, TTL and IP Family.

# 9. Gate control

The Remote Gate is the visual anchor.

States:
- CLOSED: neutral lock, no glow
- AUTHORIZING: indigo progress ring
- OPEN: controlled halo
- CONNECTED: restrained success state
- EXPIRING: countdown
- ERROR: red, explanatory copy

Always show a textual state label.

The verified IPv4 data-plane path must not be weakened for UI convenience. Browser-local remembered IP values are display-only and must never become trusted authorization inputs.

IPv6 controls must remain visibly unavailable until the corresponding firewall path is implemented and hardware-validated. Never present display support as data-plane support.

# 10. Client address presentation

The Current Client card should display both IPv4 and IPv6 when they have been observed by the browser session.

Rules:
- The current request family must be explicitly labeled.
- Browser-local address memory is only a convenience for dual-stack visibility.
- A remembered address must be labeled as previously observed rather than current.
- Gate authorization must clearly identify the trusted address actually being authorized.
- IPv6 uses the single-line fitting rule above.

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

# 12. Language behavior

The source templates are English-first.

Language selection precedence:
1. explicit browser-local user choice;
2. browser language detection;
3. English fallback.

Simplified Chinese is selected for `zh`, `zh-CN`, `zh-SG`, and `zh-Hans`-class browser languages. Unknown languages fall back to English.

Professional terms may remain English in Chinese UI, including:
`IP`, `IPv4`, `IPv6`, `WireGuard`, `Endpoint`, `Public WAN`, `TTL`, `Client`, `Server`, `Firewall`, `Backend`, `Handshake`, `Token`, and `Dual-stack`.

# 13. Theme behavior

Default theme is `auto`.
Supported values: `auto`, `light`, `dark`.

Auto follows `prefers-color-scheme` live.
Persist only an explicit user choice.
Theme bootstrap must execute before first paint to prevent a light flash in dark mode.

# 14. Responsive behavior

>= 1440px:
- 3-column adaptive workspace
- `Wide` cards span two columns
- primary cards should normally fit with little or no scrolling

1024-1439px:
- 2-column adaptive workspace
- preserve desktop-readable typography

768-1023px:
- 2 columns when practical, otherwise natural single-column reflow
- vertical scrolling is expected when viewport height is limited
- desktop arrangement mode remains available

< 768px:
- canonical single-column card order
- arrangement controls disabled
- compact Gate visualization
- 44px-class touch targets for primary actions
- no hover-dependent essential information
- full IPv6 remains one line by dynamic font fitting

# 15. Accessibility

- WCAG AA text contrast.
- `:focus-visible` ring on all interactive elements.
- Respect `prefers-reduced-motion`.
- Never rely on color only.
- Status changes use `aria-live=polite` where appropriate.
- Buttons remain keyboard operable.
- Dragging must have a button/keyboard-equivalent reordering path.

# 16. Do / Don't

Do:
- keep the dashboard calm, compact and data-first
- use semantic status labels
- preserve readable desktop typography while reflowing cards
- keep public IP values readable and copyable
- show both observed IP families without confusing display state with authorization state
- keep Gate activation a deliberate single action

Don't:
- put HTTP/HTTPS probes on the home WAN
- add decorative neon everywhere
- use glassmorphism on every element
- force a one-screen layout by shrinking all typography
- allow whole-page horizontal scrolling
- allow arbitrary pixel card resizing
- hard-code WAN2, wg0 or UDP 51820 in frontend code
- let the browser choose the IP address that gets authorized
- expose WRITE_TOKEN, session secret or WireGuard private keys
