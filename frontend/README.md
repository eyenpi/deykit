# Browser foundation

The browser shell connects to the installed loopback API for recent projects,
explicit project registration, the authored Sandbox demo, and project overviews.
It keeps the session capability in memory and preserves the current form across
an explicit reconnect.

## Run and verify

Tested on macOS arm64 with Node 26.10.0 and npm 11.19.1. Dependencies are exactly pinned in `package.json` and `package-lock.json`; Node 22.12 or later is required. Other Node/platform combinations are not yet verified.

```sh
cd frontend
npm ci
npm run dev
npm run build
npm test
npx playwright install chromium
npm run test:browser
npm run test:browser:installed
npm run format:check
```

`npm run build` typechecks and writes `dist/` with relative asset URLs. The
Python packaging step copies that build into the checked-in package assets. The
installed browser test expects an already running package installation and a
loopback origin in `DEYKIT_INSTALLED_API_URL`; it creates a fresh authored demo,
simulates the response being lost after the server commits, then checks explicit
reconnect and receipt replay. It saves initial, error, reconnect, and opened-demo
screenshots under `test-results/installed-api/`. The browser test harness under
`tests/` is not a production entry and is excluded from the build. No external
fonts, credentials, or provider calls are used.

## Integration ownership

- `workspace/gateway.ts` is the presentation port for recent-project retrieval and explicit create/open/demo requests. Preserve operation IDs when retrying unchanged form submissions; changed input gets a new ID. A failed submission preserves the form. Recent-folder actions prefill the selected path; successful opens focus the new overview heading once.
- `api/client.ts` is the common transport boundary. Bootstrap supplies a per-service capability in memory. Sensitive reads and writes use the capability; redirects are rejected. Paths are constrained to declared local API routes. Pagination uses a separately encoded cursor/limit option; response ETags are exposed as `revision` for later conflict-aware writes. Runtime decoders are generated from the packaged OpenAPI contract, and structured safe errors survive while raw response or exception text does not.
- The isolated `frontend/tools/contracts` workspace generates strict transport types and validators without runtime schema fetching or dynamic code evaluation.
- `JsonSource` contains `source_text: string`. User JSON and server-produced exact previews must stay strings across the HTTP boundary. `JsonSourceEditor` never parses, pretty-prints, normalizes or validates JSON. The backend owns validation, exact values and hashes. Do not substitute `JSON.parse`/`JSON.stringify` of user documents in feature code.
- `Shell` owns the sidebar, toolbar and decision-only action slot. `Overview` receives actual project resources through props. P17 owns execution/evidence feature views added later; it should consume these components rather than fork the shell/client. Narrow navigation moves focus into the revealed menu, restores it on Escape/selection, and keeps focus visible across breakpoint changes.
- `Modal` uses native `dialog.showModal()` for inert background, with explicit Tab wrapping for focus containment, handles Escape through the parent's dismissal policy, and restores the opener. `StagedDialog` asks Save/Discard/Keep editing and keeps failed saves open. Use controlled draft state and stable context keys.
- `ExpectedAnswers` only stages selection; the caller commits through its label service with reviewed input/revision identities. Empty selection never clears implicitly. `PredictionDisclosure` removes hidden prediction content from the DOM and resets on case/source change. Case identity must include decision/dataset/case context.
- `OptionOrder` moves presentation records without changing IDs; backend validation remains authoritative. `DataTable` uses table/caption/header semantics and focusable horizontal overflow. `ErrorSummary` can receive focus after blocked submissions.

## Remaining work

Decision authoring, imports, provider setup, execution, evidence, history, and
conflict resolution remain later work. Resource deep links, remembered
view/filter/scroll state, sidebar resizing, and command search remain pending.
Browser controls do not implement Python rules or metrics. The installed
acceptance check covers the M07 loopback workflow; it does not establish
cross-platform support, CI acceptance, live-provider compatibility, or manual
assistive-technology acceptance.

Automated Chromium checks cover native modal focus containment/restoration, saved/unsaved JSON source retention, blocked submission focus, staged Save/Discard, prediction reveal reset narrow layout, recent-folder selection and focus transitions after project opens and responsive navigation changes. Unit tests cover exact source envelopes, transport failure handling, option movement and staged selection. They use authored data; no model-quality evidence is produced.

## Primary references checked during implementation

- [Vite getting started](https://vite.dev/guide/) documents the Node requirement; the lock and successful build establish the tested combination here.
- [WAI-ARIA modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) specifies focus containment, Escape and focus restoration. Native Chromium behavior is exercised separately from jsdom component tests.
- The locally approved flat document reference informs the 208px pale sidebar, 48px toolbar, 720px readable document, restrained controls and system font. Its authored example content is not shipped as live workspace data.
