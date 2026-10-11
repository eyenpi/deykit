# Review saved results and investigate regressions

The debugging pages inspect evidence already saved by the local service. Reading,
assessing, comparing, annotating, and creating regression examples do not call a
model provider. Provider work occurs only when you explicitly start or resume an
execution group, or start a run from the execution workflow.

## Inspect and assess results

Open a run and choose a result and label snapshot pair, or select a saved
evaluation. The pair identifies the frozen result and label evidence shown by
the inspector. Progress updates do not silently replace that selection. Use the
explicit refresh control when you want to select the latest available evidence.
Saved evaluations continue to refer to the snapshots they recorded.

The case list can show all cases, cases to inspect, incorrect cases, or
unlabelled cases. Counts describe the captured result set before assessment
filtering and paging; they can overlap and should not be added as if they were
separate groups. A case assessment uses the stored case outcome and the selected
label snapshot. It does not rescore the run from labels that have since changed.

Current-label review is a separate authoring action. Before staging a current
label, check that the current input hash matches the frozen case input identity
and that the question and option identities still fit the frozen result. Saving
a current label does not rewrite a saved evaluation or its label snapshot. If a
write succeeds but the follow-up read fails, use the read-only refresh. An
uncertain write can only be retried with its original request.

Raw input, request, response, and attempt details start hidden. Reveal each
source category only when needed. Revealed content is cleared when its case or
frozen result context changes.

## Compare evaluations and preserve regressions

To compare evaluations, enter two saved evaluation IDs and verify both against
the service before creating the comparison. The saved comparison records its
evaluation and result-snapshot identities and reports the service's outcome
buckets. Comparison reads saved evidence and makes no provider calls.

An annotation is a note attached to a specific run and case; it does not alter
the saved result. A regression example is a saved reference for a decision. It
preserves the selected case and its source result identity rather than inventing
an expected answer. Removing one is a separate explicit action.

## Run bounded debugging groups

A choice-order diagnostic previews a selected dataset case set, order count,
signed seed, provider or fixture profile, and execution settings. A regression
check previews selected saved regression examples and their frozen case/input
identities. Review the server-produced preview before explicitly starting either
group. The lifetime request cap is shared across every group member and retry;
per-member limits do not increase that cap. Settings and numeric identities are
shown using the service's exact text values.

The progress page separates current group progress from a selected immutable
snapshot. New snapshots may appear while progress advances, but the displayed
snapshot stays selected until you choose another one. Snapshot reads are
read-only and preserve the recorded members, ordering, summary, and case
identities. A snapshot is not a live view of current progress.

Cancel and resume are explicit operations. Resume first shows a fresh preview
of pending work and the remaining shared attempt budget. If a start, cancel, or
resume acknowledgement is uncertain, retry the original request unchanged; do
not create a replacement action while its outcome is unresolved. Once a receipt
is known, a later progress-read failure can be recovered with a read without
repeating the mutation.

## Create and download reports

Verify the selected run, evaluation, comparison, diagnostic snapshot, or check
snapshot before creating a report. The report records the selected evidence
identities. Raw inputs, requests, and responses are individually off by
default; select only the categories that belong in that report. A saved report
can be inspected or downloaded later without starting new execution.
