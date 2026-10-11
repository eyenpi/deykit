# Browser execution local verification

Accepted runtime source and packaged assets: `fb9ab072ea19e62786df0dcb8a81815417fdada0`.
The installed Chromium workflow passed once in 56.221 seconds on Python 3.11.16,
with one worker, zero browser retries and one global verification slot. It used
the production package outside the checkout, the actual FixtureBackend/compiler/
application services, and named fake secret-store/model-list ports. No live
provider was resolved. Wheel, sdist and installed package/assets/license parity
and source/artifact immutability passed.

The six actual phases covered support-demo setup; zero-call dry review and
request opt-in; lost start acknowledgement and identical explicit replay;
held-dispatch cancellation followed by lost resume acknowledgement and identical
replay; explicitly refreshed frozen case inspection and independent request
reveal/clear; and a 320-pixel viewport with no document horizontal overflow.
Final authored outcomes were ten valid answers, one response error with one
dispatch, and one invalid input with no dispatch. Eleven unique attempts and
actual fixture dispatches were observed, with zero live dispatches. Shutdown
revoked the capability and left workers, supervisor and registry empty.

[Safe qualification record](browser-execution-evidence/qualification.json).
[Default frozen inspector](browser-execution-evidence/frozen-results-default.png).
[320-pixel run view](browser-execution-evidence/run-narrow-320.png).
These are automated authored-fixture screenshots, visually inspected by the
owner; they are not human accessibility or physical-platform acceptance.

Focused frontend evidence includes 39 tests across eight files before the later
inspector fixes, five global-cap tests across three files, and the final twelve
inspector/decoder tests across two files (2.51 seconds). Unchanged source evidence
was reused; these counts are overlapping checks, not an additive test total.
Generator, types, formatting, production bundle, canonical package assets and
offline wheel/sdist builds passed. Relevant Python projection/API/schema checks
passed: seventeen cases, Ruff and mypy (184 files). A broader group-cancellation
run failed once (15 passed/1 failed); the isolated unchanged-baseline and M11
case passed, then the full group module passed nine tests. The failed run remains
failed. Earlier installed attempts 01–11 are also failures; phase-prefix passes
are not whole-workflow acceptance. The successful workflow above is attempt 12.

Independent Luna static reviews covered the exact source fixes and final
integration. M13 integrated acceptance, CI, native Windows, physical accessibility,
IME/credential-store checks, and live-provider qualification remain separate.
The production JavaScript bundle still raises Vite's size warning (about 2.14 MB
minified, 238 KB compressed); no performance claim follows from this local gate.
