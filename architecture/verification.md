# Verification status

Deykit is terminal-first. The frontend, bundled browser assets, browser launch
options and browser-only qualification drivers are removed. The optional API
remains headless. Existing portable projects and immutable evidence are unchanged.

## Current local verification

The UI-removal/public-preparation branch is checked on macOS arm64 / Python 3.11.
The final PR records exact local results and source identity. Packaging verifies
that no UI files remain, installs wheel and sdist outside the checkout with
locked dependencies, and runs the authored terminal walkthrough from the wheel.
Tests are offline, run sequentially, and make no provider requests.

## Retained historical evidence

At `874e750`, [PR #52](https://github.com/eyenpi/deykit/pull/52) recorded a
clean-installed 99-command/8-phase terminal workflow and source-scoped
security/recovery/exact-JSON checks. Two separate synthetic Jev text/JSON
compatibility attempts completed with one attempt each and zero retries.
They establish bounded compatibility, not model quality; the authorized live
budget is exhausted. No new inference is needed for removing the UI.

Historical browser evidence belongs to the retired UI. The
[archived acceptance record](https://github.com/eyenpi/deykit/tree/4feb8577f0244ba728cc9db9bea25920e70cfea0/architecture)
retains original commit boundaries, artifacts and limitations. Older failed or
interrupted runs remain failed; there is no fresh full-suite aggregate claim.

## Remaining platform gates

Hosted jobs did not start because GitHub reported a billing/spending-limit block
while the repository was private. The consolidated **CI** configuration is not
a passing result. After the owner makes the repository public, run it on final
main and retain actual native Linux/macOS/Windows × Python 3.11/3.13 results.
It covers offline tests, process-crash recovery, cross-platform source copies,
clean installs, the terminal walkthrough and redacted history. No UI job remains.

POSIX and mocked ports cannot substitute for native Windows observations.
Physical power-loss durability remains unverified on every platform. Optional
OS keyring acceptance is separate from injected credential-store tests.
Browser layout, keyboard, IME and screen-reader gates are retired with the UI.
Follow the [public repository checklist](../guide/public-repository.md).
