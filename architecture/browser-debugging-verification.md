# Browser debugging architecture and qualification status

Browser debugging extends the existing browser execution workflow through the
typed `WorkspaceGateway`, generated API operations, shared `ApiClient`, and
registration-scoped request admission lane. UI components do not construct
transport URLs or own a second client. Application result and snapshot
projections remain service-produced; the browser presents them and keeps mutable
review drafts separate from immutable saved evidence.

## Frozen result review

Result pages use one captured result/label context for list rows, assessment
filters, counts, and case details. Assessment filters select from those same
captured rows. Counts are computed over the captured base result after status,
split, and tag selection but before assessment filtering or page slicing. The
counts may overlap. A selected saved evaluation remains attached to its own
result and label snapshots; selecting the latest pair is an explicit action.
Paired snapshot selectors are admitted together so a result cannot be combined
with a different label boundary.

Application-facing values and HTTP DTOs keep count and numeric text exact. The
browser does not convert source numbers through floating point to construct or
reinterpret evidence. Result status, assessment membership, and probability
presentation are projections of saved records. If a probability projection is
unavailable or malformed, it is identified as unavailable without modifying
the underlying result source or fabricating native confidence.

Current-label review reads and writes the current authored label separately
from frozen evaluation evidence. Frozen case input identity is exposed as a
content hash, allowing the client to compare it with the current label review
before staging. A saved evaluation is never silently recomputed from the latest
label. Comparisons verify two saved evaluation identities and display the
service's saved outcome summary. Annotations and regression examples remain
separate records and do not dispatch model work.

## Groups and immutable snapshots

Choice-order diagnostics and regression checks use distinct typed gateway
operations. Preview is read-only; start, cancel, and resume are separate retained
mutations with their original request bodies and operation IDs. Unknown outcomes
remain unresolved until the exact original request is retried. A valid receipt
is recorded before any follow-up progress read, so read recovery cannot repeat a
write. Rendered-scope epochs fence late reads and mutation callbacks from
publishing into another group or replacement view.

Group progress and snapshots have separate presentation state. Snapshot list
and detail operations read already frozen service evidence; they do not invoke
group recovery, dispatch, or substitute a newer snapshot for a selected one.
The UI keeps the selected historical snapshot pinned as new snapshots arrive.
Summary decoding is narrow and exact: counts remain decimal text, the supported
diagnostic ratio text is not recalculated in the browser, and malformed shapes
fail closed. Regression-check snapshots retain their frozen member identities
and order.

## Reports and source privacy

Reports are created only after verifying a saved target, including a specific
diagnostic or check snapshot when applicable. Raw input, request, and response
inclusion flags default off and are explicit parts of the report request. A
report download reads saved report bytes. Unknown report creation keeps its
original request available for unchanged retry; a known receipt followed by a
read failure offers read-only recovery.

## Local installed qualification

Accepted runtime and packaged assets: `38e075cbca7e6e577bbe84d7766eaf6367cfb0bb`,
Python 3.11.16 outside the checkout, one global verification job, Chromium worker
one and browser retries zero. Four complete workflows passed: comparison C09
(57.798s, 11 fixture calls), groups G38 (263.925s, 5 fixture calls), saved-answer
review S20 (31.698s, no new calls), and reports R11 (85.376s, no new calls).
Every workflow observed zero live calls, source/artifact immutability, clean
process exit, capability revocation and empty workers, supervisor and registry.
Wheel/sdist, installed package/assets and MIT/license byte parity passed. Named
fake secret-store/model-list ports remain distinct from the production compiler,
application services and FixtureBackend.

The report run covered lost acknowledgement/exact replay, independent raw flags,
JSON/Markdown byte hashes, five download rejection/recovery cases, unchanged
reports after current relabelling, both projects' pinned reports, and a real
320-pixel view with no document horizontal overflow and Tab/Shift+Tab checks.
Report IDs/hashes wrap while exact source text remains locally scrollable.
These are automated fixture checks, not human accessibility or model quality.

[Safe qualification record](browser-debugging-evidence/qualification.json).
[Saved comparison](browser-debugging-evidence/comparison-original.png).
[Pinned historical group snapshot](browser-debugging-evidence/group-pinned-historical-snapshot.png).
[Regression examples](browser-debugging-evidence/regression-examples.png).
[320-pixel report](browser-debugging-evidence/report-narrow-320.png).
The owner visually inspected these screenshots. The group image shows settled
current progress while the earlier partial snapshot remains selected; it does
not show the later snapshot's final diagnostic ratio.

Existing Python evidence is reused only for unchanged Python semantics: 257
storage/runner/API checks and 173 security, recovery, schema and exact-JSON checks.
Frontend evidence includes a mapped 192-test baseline and the current 13 report
unit cases; these are overlapping evidence, not an additive total or a fresh
full-suite claim. Generator/types, production build/canonical assets and offline
wheel/sdist build/install passed. Current bundled-asset/socket/serve checks passed eleven cases in 4.78 seconds. There is no performance claim from
these durations or the roughly 2.14 MB minified JavaScript bundle.

Earlier failed attempts stay failed. G34-G36 passed browser assertions but needed
SIGKILL. G36's bounded parent pipe located a stall inside the qualification
helper's native faulthandler cancellation after server.run and retained-worker
snapshotting returned. The accepted G driver disables only that optional native
watchdog; worker/terminal/count/lifecycle checks and the 15-second cleanup gate
remain. Its underlying native cause is unproved. Report attempts also exposed
qualification observer/selector defects and a real narrow-view overflow; R11
qualifies their final correction. Prefix passes were never promoted to whole
workflow passes.

An independent Luna review covered source at `77f4f5` before Ali disabled agents.
The owner reviewed subsequent qualification and scoped CSS/class changes; this
is not a fresh independent final-commit review. M13 final installed integration,
CI, native Windows, physical accessibility/IME/keyring and live-provider evidence
remain separate gates. No package publication, release or hosted deployment is
included.
