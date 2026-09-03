# Browser Validation

Browser validation is a separate evidence layer from routine `v0.3.x CI` and from real-device hardware validation.

## Workflows

`v0.3.x CI` remains the routine `dev` workflow. It runs contract/static tests, Python compilation, shell syntax, native mapper host build/check and JavaScript syntax. It does not execute Playwright.

`Release Browser Validation` remains the manual `main` release workflow.

`Dev Candidate Browser Matrix` exists only to obtain executable browser evidence for an exact `dev` release candidate before `main` promotion. A `dev` commit runs this matrix only when its English commit message contains `[browser-matrix]`. Ordinary `dev` pushes do not execute browser jobs.

Both entry points call the same reusable `Browser Matrix Core`, preventing Linux/Windows test ownership drift.

## Browser Matrix contract

The shared matrix runs Chromium on `ubuntu-latest` and `windows-latest` and verifies checkout HEAD equals `GITHUB_SHA` before execution.

Linux keeps the fixture alive across individually reported steps. Hosted Windows runners may reclaim child processes at a step boundary, so Windows starts the fixture and executes the complete regression sequence inside one PowerShell step with `finally` cleanup.

Executable regression set:
- dashboard layout/responsive regression across nine viewports;
- Access `PathCard` regression;
- split-WAN Dual Access regression;
- manual endpoint preference regression;
- WireGuard-bound plan preference regression;
- Gate exact-profile/runtime-authority regression;
- manual Internet Exit regression including Mobile/Desktop and Light/Dark;
- mixed Access/Internet Exit regression.

### Scalar Dual Access requirement

Browser regressions must prove that IP Family `Dual` exposes exactly one family-pure IPv4 Access selector and one family-pure IPv6 Access selector. Each selector uses the shared EndpointPicker/PathCard/FamilyPathBlock implementation and each selected option contains one FamilyPathBlock. Tests must reject any `dual:<ipv4>:<ipv6>` option identity or other IPv4×IPv6 precomputed option list.

The same tests verify the Activate request carries `endpoint_ids.ipv4` and `endpoint_ids.ipv6` directly from those scalar selections and that selection/fallback/family switching never posts Activate.

Internet Exit remains independently scalar. Mobile/Desktop regressions verify LAN=0 selectors, single-family=1 matching selector, Dual=2 scalar selectors, no redundant visible `IPv4 WAN`/`IPv6 WAN` headings, no Access port identity, adaptive stacked/side-by-side layout and Light/Dark stability.

The WireGuard-bound regression continues to exercise rapid EndpointPicker close/reopen. A stale close timer must never hide a newly opened picker session.

A successful candidate matrix is Browser Matrix evidence for that exact `dev` SHA only. Any later commit invalidates it.

## Truth rules

Do not report Browser Matrix PASS from routine CI, JavaScript syntax checks or static tests. Do not report real-device hardware PASS from any browser workflow. Hardware status requires actual device evidence and remains separate from the candidate workflow. The candidate workflow does not promote or modify `main`.
