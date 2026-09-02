# Browser Validation

Browser validation is a separate evidence layer from routine `v0.3.x CI` and from real-device hardware validation.

## Workflows

`v0.3.x CI` remains the routine `dev` workflow. It runs contract/static tests, Python compilation, shell syntax, the native mapper host build/check and JavaScript syntax. It does not execute Playwright.

`Release Browser Validation` remains the manual `main` release workflow.

`Dev Candidate Browser Matrix` exists only to obtain executable browser evidence for an exact `dev` release candidate before `main` is promoted. A `dev` commit runs this matrix only when its English commit message contains the explicit marker `[browser-matrix]`. Ordinary `dev` pushes do not execute the browser jobs.

Both release and candidate entry points call the same reusable `Browser Matrix Core`, so Linux/Windows behavior and browser-test ownership cannot drift between two workflow implementations.

## Browser Matrix contract

The shared matrix runs Chromium on both `ubuntu-latest` and `windows-latest`. Before test execution it verifies that the checked-out commit equals `GITHUB_SHA`.

Fixture lifetime is explicit rather than accidental. Linux keeps the fixture process alive across the individually reported browser-test steps. Hosted Windows runners may reclaim child processes at a step boundary, so Windows starts the fixture and executes the complete browser regression sequence inside one PowerShell step with `finally` cleanup. This preserves real Windows Chromium coverage without relying on runner orphan-process behavior.

The current executable regression set is:

- dashboard layout/responsive regression;
- Access `PathCard` regression;
- split-WAN Dual Access regression;
- manual endpoint preference regression;
- WireGuard-bound plan preference regression;
- Gate exact-profile/runtime-authority regression;
- manual Internet Exit regression, including mobile/desktop Light and Dark theme interaction;
- mixed Access/Internet Exit regression.

A successful candidate matrix is Browser Matrix evidence for that exact `dev` SHA only. Any later commit invalidates that evidence and requires a new explicit candidate run.

## Truth rules

Do not report Browser Matrix PASS from routine CI, JavaScript syntax checks or static tests.

Do not report real-device hardware PASS from any browser workflow. Hardware status remains controlled by `docs/CURRENT-DEVICE-VALIDATION.md` and requires actual device evidence.

The candidate workflow does not promote or modify `main`; promotion remains a separate user-authorized action after the required validation scope is complete.
