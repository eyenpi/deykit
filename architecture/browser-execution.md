# Browser execution architecture

Execution pages use the same `WorkspaceGateway`, generated operation types,
`ApiClient`, and registration-keyed admission lane as browser authoring. Run
preview is a read-only POST in that lane. Once dispatched, each request retains
HTTP and parsed-body settlement; an aborted read suppresses publication, while
an admitted mutation still returns its real receipt or failure. The lane does
not retry, rewrite operation IDs, or extend across a service-owned run.

`RunReview` captures one proposal and requests a server-produced preview. The
preview's reviewed context and case projections are shown together; optional
request-source reveal repeats the same proposal through the preview operation
with its explicit include flag. A revealed response replaces the earlier review
only when its request generation is still current. Start uses a retained
mutation containing the exact operation ID, expected review hash, and request.
An uncertain response leaves that request available for explicit replay. A
valid start receipt is known before the page reads progress, so a later read
failure offers read-only recovery and cannot turn into another start.
The configured lifetime attempt cap is one total request budget across all
selected cases and retries.

Preview validates input and frozen execution context. It does not establish
that each selected case has a fixture binding; a missing binding is reported by
fixture dispatch as a `missing_fixture` or `binding_not_found` response error.

`RunList` and `RunDetail` publish only responses matching the current
registration, route, run, and read generation. Detail polling is non-overlapping,
completion-relative, and pauses while the document is hidden. The browser stops
polling when the service reports execution inactive; navigation, reload, and
polling never invoke a mutation. Cancel and resume have separate retained
operation records. Resume review is advisory because the API does not provide a
resume review hash; the service revalidates the frozen run when the explicit
resume request arrives.

The result inspector pins evaluation and snapshot identities across pages and
case details. Its adapter-side decoder validates the known fields of generic
result source objects and fails closed on malformed required values. It does
not parse user-authored input, request, response, probability, or confidence
source strings. Raw categories are fetched only after their individual reveal
controls are enabled and are cleared when the selected run, evaluation, case,
or registration changes. Evaluation and result reads are evidence inspection;
the browser does not create an evaluation or derive new accuracy metrics.

Fixture dispatch remains on the normal execution service path and uses authored
fixture bindings. Per-case binding availability is determined at dispatch,
not by preview. Live dispatch remains distinct and is never selected as an
automatic fallback. Automated fixture verification is local authored evidence;
it does not establish live-provider quality, physical platform behavior, or
provider qualification.
