import { useEffect, useRef, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { safeMessage } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ErrorSummary, LoadingState } from "../../components/States";
import { JsonSourceEditor } from "../../components/JsonSourceEditor";
import type { DecisionAuthoringOperations } from "../../workspace/gateway";
import type {
  DirtyNavigationGuard,
  WorkspaceNavigation,
} from "../../workspace/navigation";
import type { WorkspaceRoute } from "../../workspace/routes";
import { RetainedMutation } from "../../workspace/mutation-controller";
import type { MutationState } from "../../workspace/mutation-controller";

type RevisionPage = ApiOperationData<"listDecisionRevisions">;
type RevisionData = ApiOperationData<"readDecisionRevision">;
type DiffData = ApiOperationData<"diffDecisionRevisions">;
type RestoreBody = ApiOperationBody<"restoreDecisionRevisionToDraft">;
type RestoreData = ApiOperationData<"restoreDecisionRevisionToDraft">;

export function DefinitionHistory({
  registrationId,
  decisionId,
  operations,
  navigation,
  onRestoredToDraft,
}: {
  registrationId: string;
  decisionId: string;
  operations: DecisionAuthoringOperations;
  navigation: WorkspaceNavigation;
  onRestoredToDraft: () => void;
}) {
  const [pages, setPages] = useState<RevisionPage[]>([]);
  const [selected, setSelected] = useState<RevisionData>();
  const [diff, setDiff] = useState<DiffData>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [cursor, setCursor] = useState<string>();
  const [restorePreview, setRestorePreview] = useState<RevisionData>();
  const [restoreState, setRestoreState] = useState<MutationState<RestoreData>>({
    kind: "idle",
  });
  const [reviewedDraft, setReviewedDraft] = useState<{
    etag: string;
    source: string;
  }>();
  const restoreMutation = useRef<
    RetainedMutation<RestoreBody, RestoreData> | undefined
  >(undefined);
  const restoreGuard = useRef<DirtyNavigationGuard | undefined>(undefined);
  const restoreGuardValue: DirtyNavigationGuard =
    restoreGuard.current ??
    (() => {
      const unresolvedRestore = () => {
        // Navigation can run before React renders the submitting state. Read
        // the live mutation so its original request survives until settlement.
        const state = restoreMutation.current?.state.kind;
        return state === "submitting" || state === "outcome-unknown";
      };
      return Object.assign(
        async (_target: WorkspaceRoute) => !unresolvedRestore(),
        { isDirty: unresolvedRestore },
      );
    })();
  restoreGuard.current = restoreGuardValue;

  useEffect(() => {
    restoreMutation.current = new RetainedMutation(async (body) => {
      return (
        await operations.restoreRevisionToDraft({
          registrationId,
          decisionId,
          body,
        })
      ).data;
    }, setRestoreState);
    setRestoreState({ kind: "idle" });
  }, [decisionId, operations, registrationId]);

  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `revision-restore:${registrationId}:${decisionId}`,
        restoreGuardValue,
      ),
    [decisionId, navigation, registrationId, restoreGuardValue],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(undefined);
    void operations
      .revisions({
        registrationId,
        decisionId,
        signal: controller.signal,
        query: { limit: "50" },
      })
      .then((result) => {
        if (controller.signal.aborted) return;
        setPages([result.data]);
        setCursor(result.data.next_cursor ?? undefined);
        setSelected(undefined);
        setDiff(undefined);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(safeMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [decisionId, operations, registrationId]);

  async function more() {
    if (!cursor || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await operations.revisions({
        registrationId,
        decisionId,
        query: { cursor, limit: "50" },
      });
      setPages((current) => [...current, result.data]);
      setCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function inspect(revisionId: string) {
    setBusy(true);
    setError(undefined);
    try {
      const result = await operations.revision({
        registrationId,
        decisionId,
        revisionId,
      });
      setSelected(result.data);
      setDiff(undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function compareWithLatest(revisionId: string) {
    setBusy(true);
    setError(undefined);
    try {
      const latest = await operations.latestRevision({
        registrationId,
        decisionId,
      });
      if (latest.data.revision.record.id === revisionId) {
        setDiff(undefined);
        return;
      }
      const result = await operations.diff({
        registrationId,
        decisionId,
        query: { before: revisionId, after: latest.data.revision.record.id },
      });
      setDiff(result.data);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    if (!restorePreview || busy || !restoreMutation.current) return;
    setBusy(true);
    setError(undefined);
    try {
      const state = restoreMutation.current.state;
      let result: RestoreData | undefined;
      if (state.kind === "outcome-unknown") {
        result = await restoreMutation.current.retryOriginal();
      } else {
        if (state.kind === "conflict" && !reviewedDraft) {
          setError(
            "The current draft changed. Review its source before starting a new restore.",
          );
          return;
        }
        const current = reviewedDraft
          ? undefined
          : await operations.read({ registrationId, decisionId });
        const expectedDraftEtag =
          reviewedDraft?.etag ?? current?.data.draft.etag;
        if (!expectedDraftEtag)
          throw new Error("The current draft ETag could not be read.");
        const body: RestoreBody = {
          schema_version: 1,
          expected_draft_etag: expectedDraftEtag,
          revision_id: restorePreview.revision.record.id,
          operation_id: crypto.randomUUID(),
        };
        if (state.kind !== "idle") restoreMutation.current.reset();
        setReviewedDraft(undefined);
        result = await restoreMutation.current.submit(body);
      }
      if (result) {
        setRestorePreview(undefined);
        setReviewedDraft(undefined);
        setError(undefined);
        onRestoredToDraft();
      } else {
        const nextState = restoreMutation.current.state;
        if (nextState.kind === "conflict")
          setError(
            "The draft changed before this restore completed. Review the current draft before reapplying.",
          );
        else if (nextState.kind === "outcome-unknown")
          setError(
            "The restore outcome is unknown. Retry the exact same request to learn whether it completed.",
          );
        else if (nextState.kind === "failed") setError(nextState.message);
      }
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function prepareRestore(revisionId: string) {
    setBusy(true);
    setError(undefined);
    try {
      const result = await operations.revision({
        registrationId,
        decisionId,
        revisionId,
      });
      restoreMutation.current?.reset();
      setRestoreState({ kind: "idle" });
      setReviewedDraft(undefined);
      setSelected(result.data);
      setRestorePreview(result.data);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function reviewCurrentDraft() {
    setBusy(true);
    setError(undefined);
    try {
      const result = await operations.read({ registrationId, decisionId });
      setReviewedDraft({
        etag: result.data.draft.etag,
        source: result.data.draft.record.editor_source,
      });
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  const revisions = pages.flatMap((page) => page.items);
  if (loading)
    return (
      <article className="document">
        <LoadingState>Loading decision history…</LoadingState>
      </article>
    );
  return (
    <article className="document">
      <header className="page-heading-row">
        <div>
          <h1>Version history</h1>
          <p className="muted">
            Saved definitions are immutable. The current draft stays separate.
          </p>
        </div>
      </header>
      {error && <ErrorSummary message={error} />}
      {revisions.length === 0 ? (
        <section className="empty-state">
          <h2>No saved versions</h2>
          <p className="muted">
            Save a valid decision version to begin its history.
          </p>
        </section>
      ) : (
        <table className="records-table">
          <caption>Saved decision versions</caption>
          <thead>
            <tr>
              <th scope="col">Version</th>
              <th scope="col">Saved</th>
              <th scope="col">Note</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {revisions.map((item) => {
              const revision = item.revision.record;
              return (
                <tr key={revision.id}>
                  <th scope="row">
                    <code>{revision.id}</code>
                  </th>
                  <td>{revision.created_at}</td>
                  <td>
                    {revision.note || <span className="muted">No note</span>}
                  </td>
                  <td className="actions">
                    <button
                      type="button"
                      onClick={() => void inspect(revision.id)}
                    >
                      Inspect
                    </button>
                    <button
                      type="button"
                      onClick={() => void compareWithLatest(revision.id)}
                    >
                      Compare to latest
                    </button>
                    <button
                      type="button"
                      onClick={() => void prepareRestore(revision.id)}
                    >
                      Restore to draft…
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {cursor && (
        <button type="button" disabled={busy} onClick={() => void more()}>
          {busy ? "Loading…" : "Load more versions"}
        </button>
      )}
      {selected && (
        <section className="section revision-inspector">
          <h2>Version {selected.revision.record.id}</h2>
          <p>
            <code>{selected.revision.record.content_hash}</code>
          </p>
          <p className="muted">
            Read-only definition detail from the saved version.
          </p>
          <dl>
            <dt>Question</dt>
            <dd>
              {selected.revision.record.definition.questions[0].instructions}
            </dd>
            <dt>Options</dt>
            <dd>
              {selected.revision.record.definition.questions[0].options
                .map((option) => option.name)
                .join(", ")}
            </dd>
          </dl>
          <details className="section saved-source">
            <summary>Exact saved editor source</summary>
            <JsonSourceEditor
              label="Saved editor source"
              value={selected.editor_source}
              readOnly
              rows={14}
            />
          </details>
        </section>
      )}
      {diff && (
        <section aria-label="Difference from latest version">
          <h2>Difference from latest</h2>
          <ul>
            <li>Question changed: {diff.question_changed ? "Yes" : "No"}</li>
            <li>Input changed: {diff.input_changed ? "Yes" : "No"}</li>
            <li>
              Option order changed: {diff.option_order_changed ? "Yes" : "No"}
            </li>
            <li>
              Added option IDs: {diff.added_option_ids.join(", ") || "None"}
            </li>
            <li>
              Removed option IDs: {diff.removed_option_ids.join(", ") || "None"}
            </li>
          </ul>
        </section>
      )}
      {restorePreview && (
        <Modal
          title="Restore this version to the draft?"
          onDismiss={() => {
            if (!busy && restoreState.kind !== "outcome-unknown") {
              setRestorePreview(undefined);
              setReviewedDraft(undefined);
            }
          }}
        >
          <div className="modal-body">
            <p>
              The saved version will replace the current draft after the service
              checks its latest ETag. Existing saved versions and evidence stay
              unchanged.
            </p>
            <h3>Version to restore</h3>
            <p>
              <code>{restorePreview.revision.record.id}</code> ·{" "}
              {restorePreview.revision.record.created_at}
            </p>
            <p>
              {
                restorePreview.revision.record.definition.questions[0]
                  .instructions
              }
            </p>
            <ul>
              {restorePreview.revision.record.definition.questions[0].options.map(
                (option) => (
                  <li key={option.id}>{option.name}</li>
                ),
              )}
            </ul>
            <JsonSourceEditor
              label="Editor source to restore"
              value={restorePreview.editor_source}
              readOnly
              rows={10}
            />
            {restoreState.kind === "conflict" && (
              <section aria-label="Current draft after conflict">
                <p role="status">
                  The saved version was not restored. The current draft remains
                  unchanged.
                </p>
                {reviewedDraft ? (
                  <JsonSourceEditor
                    label="Reviewed current draft source"
                    value={reviewedDraft.source}
                    readOnly
                    rows={10}
                  />
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reviewCurrentDraft()}
                  >
                    Review current draft
                  </button>
                )}
              </section>
            )}
            {restoreState.kind === "outcome-unknown" && (
              <p role="status">
                The restore outcome is unknown. Keep this dialog open and retry
                the original request.
              </p>
            )}
            <div className="actions">
              <button
                type="button"
                className="primary"
                disabled={
                  busy || (restoreState.kind === "conflict" && !reviewedDraft)
                }
                onClick={() =>
                  restoreState.kind === "conflict" && !reviewedDraft
                    ? void reviewCurrentDraft()
                    : void restore()
                }
              >
                {restoreState.kind === "outcome-unknown"
                  ? "Retry the same restore request"
                  : restoreState.kind === "conflict"
                    ? "Restore over reviewed draft"
                    : "Restore to draft"}
              </button>
              <button
                type="button"
                disabled={busy || restoreState.kind === "outcome-unknown"}
                onClick={() => {
                  setRestorePreview(undefined);
                  setReviewedDraft(undefined);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </Modal>
      )}
    </article>
  );
}
