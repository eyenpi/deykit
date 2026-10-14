# Making the repository public and finishing platform verification

Preparation does not change visibility, publish a package or prove CI passed.
The owner performs the visibility change below.

1. Review the merged preparation PR and final main commit. The current tree keeps
   the terminal workflows, headless API, tests, user guides, MIT license and
   contributor/security instructions. The UI and redundant engineering reports
   are removed. Historical files remain in Git history. Local `docs/`, credentials
   and private projects are not tracked. History, issues, PRs and authors become
   visible too; review them before changing visibility.
2. In GitHub **Settings → General → Danger Zone → Change repository visibility**,
   choose public. See [GitHub's instructions](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility).
   Enable private vulnerability reporting under **Security** if available.
3. Open **Actions → CI → Run workflow**, select main and record the exact head.
   Standard hosted runners are free for public repositories; larger runners and
   excess storage can incur charges. See [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
   Visibility alone does not prove an existing account restriction cleared.
4. Require the source/secret-scan job and all six native Python matrix entries to
   actually pass. Inspect JUnit artifacts and skipped native tests. Fix failures
   on a branch and rerun the final head. Do not bypass protection or mark
   unstarted jobs green. No frontend or browser CI job remains.
5. Update issues #18 and #19 with exact native results and close their remaining
   platform gates only when evidenced. POSIX and mocked checks are not Windows
   evidence. Browser/IME/layout acceptance is retired with the UI removal.

Optional OS keyring acceptance uses a unique disposable test entry. Verify
set/status/read/forget and cleanup without printing a provider key or changing
access approvals. An unavailable/locked backend remains an explicit limitation.

The preparation scan uses Gitleaks 8.30.1 default rules. Its only exception is an
exact generated OpenAPI hash line in the former frontend manifest; it is still
needed for historical commits. A synthetic-token negative control in that same
path verified detection was retained. The known external credential was absent
from 2,535 reachable Git blobs in the preparation snapshot. These scans do not
prove every possible secret is absent. Removing current files does not purge
history. Do not force-add ignored files or automatically rewrite history.

The two authorized live compatibility attempts are already consumed. No further
inference, release tag, package publication or hosted deployment is part of this
checklist.
