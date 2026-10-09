# Local API

The local browser workspace is served by the installed Python package. The API
binds only to IPv4 loopback, accepts the exact bound Host and Origin, and uses a
random in-memory capability for one service lifetime. The shell and manifest
assets are package resources; the server never serves project files as static
content. Project folders enter the process only after an explicit registration
request, and an opened source remains retained for that service lifetime.

The initial API exposes session bootstrap, recent project preferences, project
registration, authored demo creation, project description, overview, source
validation, and index rebuild. Requests are strict versioned JSON. Operation IDs
are carried in mutation bodies, project ETags remain opaque, and counts are
transport strings. Project opening is metadata-only. The demo is authored
fixture evidence and uses the same application services as CLI authoring; its
complete graph is committed as one durable operation and replayed from its
receipt.

The browser client keeps its session capability in memory, sends no cookies,
and never includes the capability in a URL. Reconnect is explicit and does not
resend a mutation. When registration succeeds but overview loading fails, the
gateway retains the registration ID and retries only the overview read.

The Python build consumes checked-in, hash-manifested browser assets. API
contract generation uses the isolated `frontend/tools/contracts` workspace and
is checked with `npm run generate:api:check` from the frontend directory.
Production verification must qualify an actual wheel built from the
sdist, serve its assets from an installed location, and exercise the bounded
loopback HTTP flow. Browser CSP, reconnect and packaged-shell screenshots are
separate evidence. Native Windows, CI, assistive technology and live provider
checks remain separate platform or authorization gates.
