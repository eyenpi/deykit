# Browser authoring architecture

The browser uses the existing `WorkspaceGateway` and its operation-specific
authoring ports. `workspace-adapter.ts` delegates each typed operation to the same
singleton `ApiClient` used for project registration and reconnect. Generated
operation identifiers, arguments, request bodies, and response validators remain
owned by the API client/generator. Pages receive narrow authoring ports rather than
constructing transport requests or a second client.

`WorkspaceNavigation` validates hash routes before publishing them, retains the
last admitted route across external hash changes, and coordinates asynchronous
dirty guards for browser Back/Forward and in-app navigation. Route parameters are
resource identifiers plus the declared example selection keys. Registration IDs
scope an in-memory workspace view; portable project IDs and copied project roots
are not used as the local session key. No source text, filesystem path, credential,
or capability is stored in a route or browser persistence.

Decision and import source remains an exact string. The browser asks backend
projection and transform operations for structured controls, and submits the
service-returned source with its ETag and operation ID. Draft autosaves are
serialized; acknowledgements advance the ETag without replacing newer typing.
Conflicts and uncertain outcomes stop the queue and retain the editor source for
review. Import preview and split preview likewise remain server-produced documents;
the browser does not implement a row parser or split algorithm.

Label writes carry the full review projection. Case edits preserve the complete
case record context and both case and dataset ETags. Provider credentials are
excluded from profile reads and UI state except for the request-local password
field used by the OS-store operation; provider model listing is explicitly invoked.
Fixture requests use authored strict binding source strings, and reading request
details is opt-in.

The browser may author project content, labels, profiles, and fixtures. It does not
expose run dispatch, progress, resume, result review, comparison, reevaluation, or
diagnostic UI. A browser acceptance claim requires the packaged static assets with
the real local API; development-server or mock-gateway behavior is not equivalent.
