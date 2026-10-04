# Browser foundation

This is the frontend foundation for P16, not a completed workspace. It includes the flat workspace shell, start screen, explicit project-path forms, a server-data-driven overview, and tested reusable presentation components. The production gateway deliberately returns an unavailable-service error. It does not make up projects, execute requests against speculative routes, or report successful writes. The overview is exercised with authored data only in tests.

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
npm run format:check
```

`npm run build` typechecks and writes `dist/` with relative asset URLs for the later Python package build. Ordinary installed users will not need Node once P18 bundles these assets. `dist/` is generated and intentionally untracked. The browser test harness under `tests/` is not a production entry and is excluded from the build. No external fonts, images, credentials, or paid calls are used.

## Integration ownership

- `workspace/gateway.ts` is the presentation port for recent-project retrieval and explicit create/open/demo requests. P15 supplies its real adapter. Preserve operation IDs when retrying unchanged form submissions; changed input gets a new ID. A failed submission preserves the form.
- `api/client.ts` is the common transport boundary. A bootstrap adapter supplies a per-service capability in memory. Sensitive reads and writes use the capability; redirects are rejected. Paths are constrained to local resource paths. Pagination uses a separately encoded cursor/limit option; response ETags are exposed as `revision` for later conflict-aware writes. Runtime decoders are required; structured safe errors survive while raw HTML/transport exception text does not.
- The provisional capability, ETag, idempotency header names and response envelope must be reconciled with P15's actual generated contracts before wiring. Do not create a second fetch layer. There is no bootstrap or generated schema claim in this PR.
- `JsonSource` contains `source_text: string`. User JSON and server-produced exact previews must stay strings across the HTTP boundary. `JsonSourceEditor` never parses, pretty-prints, normalizes or validates JSON. The backend owns validation, exact values and hashes. Do not substitute `JSON.parse`/`JSON.stringify` of user documents in feature code.
- `Shell` owns the sidebar, toolbar and decision-only action slot. `Overview` receives actual project resources through props. P17 owns execution/evidence feature views added later; it should consume these components rather than fork the shell/client.
- `Modal` uses native `dialog.showModal()` for inert background, with explicit Tab wrapping for focus containment, handles Escape through the parent's dismissal policy, and restores the opener. `StagedDialog` asks Save/Discard/Keep editing and keeps failed saves open. Use controlled draft state and stable context keys.
- `ExpectedAnswers` only stages selection; the caller commits through its label service with reviewed input/revision identities. Empty selection never clears implicitly. `PredictionDisclosure` removes hidden prediction content from the DOM and resets on case/source change. Case identity must include decision/dataset/case context.
- `OptionOrder` moves presentation records without changing IDs; backend validation remains authoritative. `DataTable` uses table/caption/header semantics and focusable horizontal overflow. `ErrorSummary` can receive focus after blocked submissions.

## Remaining work

P15 bootstrap, generated transport models, real project registration/recent state, actual authoring/import/provider/history services, incomplete-draft autosave, conflict resolution and the full P16/P17 flows remain pending. Resource deep links, remembered view/filter/scroll state, sidebar resizing and command search remain integration work. Browser controls do not implement Python rules or metrics. The useful foundation must not be cited as completion of P16, A16/A46/A47 as whole-product gates, API security verification, Python packaging, cross-platform acceptance, live compatibility or manual assistive-technology acceptance.

Automated Chromium checks cover native modal focus containment/restoration, saved/unsaved JSON source retention, blocked submission focus, staged Save/Discard, prediction reveal reset and narrow layout. Unit tests cover exact source envelopes, transport failure handling, option movement and staged selection. They use authored data; no model-quality evidence is produced.

## Primary references checked during implementation

- [Vite getting started](https://vite.dev/guide/) documents the Node requirement; the lock and successful build establish the tested combination here.
- [WAI-ARIA modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) specifies focus containment, Escape and focus restoration. Native Chromium behavior is exercised separately from jsdom component tests.
- The locally approved flat document reference informs the 208px pale sidebar, 48px toolbar, 720px readable document, restrained controls and system font. Its authored example content is not shipped as live workspace data.
