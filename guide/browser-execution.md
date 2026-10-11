# Review and inspect executions in the browser

From a decision page, choose **Run** to review a fixture or live-provider run.
Choose the dataset, split, optional cases, definition version, execution mode,
and attempt limits. The local service reviews that proposal and shows the
selected and development cases, source identities, input errors, request hashes,
destination, compiler, model, and settings. Review is a dry run: it does not
create a run or dispatch model requests. Compiled request source is hidden unless
you explicitly reveal it.

Starting a reviewed run is a separate action. If the connection is lost after
submission, use **Retry original start request** to repeat the same operation.
The service may acknowledge the original run instead of creating another one.
Keep the review open until the request settles; the browser preserves an
uncertain request so that it cannot silently change into a different run.

The Runs page lists service-reported runs and their lifecycle states. Open a run
to see its progress, attempt limits, and available evaluation snapshots. A run
may continue after you leave the page. Refreshing or reopening it only reads
progress; it does not start, cancel, or resume work.

When a run is no longer active, inspect its frozen results and select an
evaluation when one is available. Result and label snapshot IDs identify the
evidence being shown. The case inspector reports the stored answer, expected
options, status, and exclusion reasons; it does not calculate a new accuracy
score from current labels. Input, request, response, and attempt details are
separate opt-in controls. Closing the inspector or changing its case or
evaluation clears revealed source from the page.

Cancel and resume are explicit actions. A cancel acknowledgement reports the
service's state; it does not claim that already-started work vanished. Resume
requires a fresh review of the pending cases and attempt cap. Unknown attempts
are excluded unless you explicitly include them, because the earlier remote
request may already have run. The local service remains authoritative when
reviewing, starting, cancelling, or resuming.

The lifetime attempt cap is a total request limit for the run, shared across
all selected cases and retries.

Fixture runs use authored request bindings and do not contact a live provider.
Preview validates the input and frozen execution context, but does not check
whether every selected case has a fixture binding. A missing binding is
reported during fixture dispatch as a `missing_fixture` or
`binding_not_found` response error. Live-provider runs may contact the selected
provider and may incur cost. The browser does not switch between these modes
automatically.

Use **Refresh frozen results** to deliberately select a newer current result
boundary after execution or resume. The inspector keeps the displayed snapshot
pair until that explicit refresh; selecting a saved evaluation keeps its historic
result and label snapshots. Progress refresh does not change that evidence pin.
