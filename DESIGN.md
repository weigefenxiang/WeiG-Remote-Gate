---
version: 1
name: WeiG-Remote-Gate
description: "A calm, precise, spatial network-security console. The visual language combines Linear-like technical restraint, Apple-like whitespace and clarity, Stripe-like depth and gradient atmosphere, and a distinct WeiG security identity. Effects communicate state; decoration never competes with security information."
---

# 1. Design philosophy

WeiG-Remote-Gate is a security control surface, not a marketing page.

Principles:
- Calm before flashy.
- One primary action per screen.
- Depth through surfaces, hairlines, inner highlights and restrained shadows.
- Animation explains state transitions; it never exists only for spectacle.
- Security state is always expressed by text and icon, never color alone.
- No fake diagnostics. Do not label HTTP timing as ICMP ping.
- Never expose secrets, tokens or private keys in the UI.

# 2. Color tokens

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

# 3. Typography

Use native system fonts only:
`Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`

Monospace:
`"SFMono-Regular", Consolas, "Liberation Mono", monospace`

- display: 34-42px / 650 / tight tracking
- section title: 20-24px / 650
- card title: 15-17px / 650
- body: 14-16px / 400
- caption: 12-13px / 500
- numeric IP/status values use tabular numerals

# 4. Spacing

4px base rhythm:
4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64

Main desktop max-width: 1240px.
Mobile horizontal padding: 16px.
Desktop horizontal padding: 28px.

# 5. Radius

- xs: 8px
- sm: 12px
- md: 16px
- lg: 22px
- xl: 28px
- pill: 999px

# 6. Depth

Four visual layers:
1. Ambient canvas.
2. Main glass-like surface.
3. Cards and panels.
4. Interactive controls.

Cards use:
- 1px hairline border
- soft outer shadow
- subtle inset top highlight
- no heavy blur on low-power mobile devices

Hover elevation: max translateY(-2px).
Pressed: translateY(1px).
Never use exaggerated scale transforms.

# 7. Buttons

Primary:
- high contrast indigo
- pill or 14px radius
- visible top highlight and soft shadow
- minimum touch height 46px

Secondary:
- surface background + hairline
- no competing accent

Danger:
- red only for revoke/close/destructive actions

# 8. Gate control

The Remote Gate is the visual anchor.

States:
- CLOSED: neutral lock, no glow
- AUTHORIZING: indigo progress ring
- OPEN: controlled indigo halo
- CONNECTED: restrained success halo
- EXPIRING: amber countdown
- ERROR: red, explanatory copy

Always show a textual state label.

# 9. Theme behavior

Default theme is `auto`.
Supported values: `auto`, `light`, `dark`.

Auto follows `prefers-color-scheme` live.
Persist only an explicit user choice.
Theme bootstrap must execute before first paint to prevent white flash in dark mode.

# 10. Responsive behavior

>= 980px:
- Gate panel left
- Client/WireGuard status right
- WAN cards in 3-column grid when space permits

640-979px:
- two-column status grid
- WAN cards 2 columns

< 640px:
- single column
- 44px minimum touch target
- no hover-dependent information
- gate action remains above the fold when practical

# 11. Accessibility

- WCAG AA text contrast.
- `:focus-visible` ring on all interactive elements.
- Respect `prefers-reduced-motion`.
- Never rely on color only.
- Status changes use `aria-live=polite`.
- Buttons remain keyboard operable.

# 12. Do / Don't

Do:
- keep the dashboard calm and data-first
- use semantic status labels
- use native system fonts for fast first paint
- keep the WAN public IP readable and copyable
- make Gate activation a deliberate single action

Don't:
- put HTTP/HTTPS probes on the home WAN
- add decorative neon everywhere
- use glassmorphism on every element
- hard-code WAN2, wg0 or UDP 51820 in frontend code
- let the browser choose the IP address that gets authorized
- expose WRITE_TOKEN, session secret or WireGuard private keys
