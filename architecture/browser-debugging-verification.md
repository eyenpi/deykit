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

## Evidence boundary

This note describes the authored browser behavior and intended evidence
boundaries. M12 installed qualification is **pending**. No installed-package
pass, browser performance result, live-provider observation, CI result, or
physical-platform acceptance is claimed here. Authored fixtures and local
automated checks remain distinct from installed qualification, live provider
quality, native Windows behavior, and manual accessibility or IME review. The
qualification record will be updated only from the exact accepted installed
workflow and its retained evidence.
