# Group lifecycle facades

Choice-order diagnostics and regression checks share one execution-group lifecycle.
Their resume facades pass the immutable expected kind into the shared service after
operation-receipt lookup; kind is an admission constraint and does not change the
legacy resume intent digest. Facades also forward optional acknowledgement callbacks
without translating the frozen `GroupAcknowledged` identity.

Callback-bearing create and resume acknowledgements admit the original receipt and
its group segment against one captured source epoch. Every linked child must have a
typed `segment_ready` event for that exact segment before the callback runs. This
path returns captured progress and does not invoke recovery or group snapshots. The
callback runs after the source read boundary and before scheduling. Execution-lock
activity is observed only after receipt, graph, and readiness admission succeeds;
missing receipts or readiness therefore do not probe ownership. Callback-free legacy
CLI receipt replay retains its existing progress-recovery behavior after receipt and
expected-kind admission.

Resume previews use the original group cap, captured member histories, and the
existing unknown-retry eligibility policy. They resolve frozen backends against the
same captured records for offline preflight, without changing business records,
receipts, reservations, cancellation controls, recovery state, or group snapshots.
Normal `consistent_read` and execution-activity probes may create disposable
`.deykit/locks` metadata files. Failed immutable admission and preflight return before
the execution-activity probe. Group
cancellation issues deterministic child cancellation operation IDs through the
existing run cancellation service, in frozen member order. A partial failure leaves
prior child controls durable; retry reuses their IDs. There is intentionally no
parent group cancellation receipt, so operation conflicts across different group
targets are not persisted by this facade.

These are authored local service boundaries. Their tests are not evidence of a
native HTTP workflow, an interrupted native commit, or live provider behavior.
