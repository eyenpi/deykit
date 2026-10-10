import { useCallback, useEffect, useRef, useState } from "react";
import type { Ref } from "react";
import type { ApiOperationBody, ApiOperationData } from "../api/client";
import { safeMessage } from "../api/client";
import { DataTable } from "../components/DataTable";
import { ErrorSummary, LoadingState, WarningList } from "../components/States";
import { useDirtyNavigationGuard } from "./NavigationGuardPrompt";
import type {
  DecisionAuthoringOperations,
  ProjectOverview,
  ResourceSummary,
} from "./gateway";
import type { WorkspaceNavigation } from "./navigation";
import {
  QueuedMutationNotAdmitted,
  RetainedMutation,
} from "./mutation-controller";
import type { MutationState } from "./mutation-controller";

type DecisionPage = ApiOperationData<"listDecisions">;
type RestoreData = ApiOperationData<"restoreDecision">;
type RestoreBody = ApiOperationBody<"restoreDecision">;
type RestoreRequest = {
  registrationId: string;
  decisionId: string;
  body: RestoreBody;
};
type ProjectOwner = { registrationId: string; lifetime: number };
type OwnedPage = {
  owner: ProjectOwner;
  data?: DecisionPage;
  loading: boolean;
  error?: string;
};
type OwnedMutation = {
  owner: ProjectOwner;
  controller: RetainedMutation<RestoreRequest, RestoreData>;
};

export function Overview({
  project,
  headingRef,
  onDecision,
  onCreateDecision,
  onCreateDataset,
  onExamples,
  decisionOperations,
  onDecisionsChanged,
  navigation,
}: {
  project: ProjectOverview;
  headingRef?: Ref<HTMLHeadingElement>;
  onDecision: (decision: ResourceSummary) => void;
  onCreateDecision: () => void;
  onCreateDataset: () => void;
  onExamples: () => void;
  decisionOperations: DecisionAuthoringOperations;
  onDecisionsChanged: () => void;
  navigation: WorkspaceNavigation;
}) {
  const ownerRef = useRef<ProjectOwner>({
    registrationId: project.id,
    lifetime: 0,
  });
  if (ownerRef.current.registrationId !== project.id) {
    ownerRef.current = {
      registrationId: project.id,
      lifetime: ownerRef.current.lifetime + 1,
    };
  }
  const owner = ownerRef.current;
  const mountedRef = useRef(false);
  const isLiveOwner = useCallback(
    (candidate: ProjectOwner) =>
      mountedRef.current && ownerRef.current === candidate,
    [],
  );
  const operationsRef = useRef(decisionOperations);
  operationsRef.current = decisionOperations;
  const decisionsChangedRef = useRef(onDecisionsChanged);
  decisionsChangedRef.current = onDecisionsChanged;

  const [, setMutationRevision] = useState(0);
  const mutationRef = useRef<OwnedMutation | undefined>(undefined);
  if (!mutationRef.current || mutationRef.current.owner !== owner) {
    mutationRef.current = {
      owner,
      controller: new RetainedMutation(
        async (request) => {
          if (!isLiveOwner(owner)) throw new QueuedMutationNotAdmitted();
          return (
            await operationsRef.current.restore({
              registrationId: request.registrationId,
              decisionId: request.decisionId,
              body: request.body,
            })
          ).data;
        },
        () => {
          if (isLiveOwner(owner))
            setMutationRevision((revision) => revision + 1);
        },
      ),
    };
  }
  const mutation = mutationRef.current.controller;
  const mutationState: MutationState<RestoreData> = mutation.state;
  const readEpochRef = useRef(0);
  const readLockRef = useRef<ProjectOwner | undefined>(undefined);
  const readControllerRef = useRef<
    { owner: ProjectOwner; controller: AbortController } | undefined
  >(undefined);
  const [readBusy, setReadBusy] = useState(false);
  const [archive, setArchive] = useState<OwnedPage>();
  const currentArchive = archive?.owner === owner ? archive : undefined;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      readEpochRef.current += 1;
      readLockRef.current = undefined;
      readControllerRef.current?.controller.abort();
      readControllerRef.current = undefined;
    };
  }, []);

  const isDirtyNow = useCallback(() => {
    const state = mutationRef.current?.controller.state.kind;
    return state === "submitting" || state === "outcome-unknown";
  }, []);
  const isBlockedNow = isDirtyNow;
  const blockedMessage =
    mutationState.kind === "submitting"
      ? "The restore request is still being confirmed. Keep editing until it settles."
      : mutationState.kind === "outcome-unknown"
        ? "The restore outcome is unknown. Retry the same restore action before leaving."
        : undefined;
  const navigationGuard = useDirtyNavigationGuard({
    dirty: isDirtyNow(),
    isDirtyNow,
    isBlockedNow,
    blockedMessage,
    save: async () => undefined,
    discard: () => undefined,
  });

  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `overview-restore:${project.id}`,
        navigationGuard.guard,
      ),
    [navigation, navigationGuard.guard, project.id],
  );

  useEffect(() => {
    const requestOwner = owner;
    const controller = new AbortController();
    const epoch = ++readEpochRef.current;
    setArchive({ owner: requestOwner, loading: true });
    setReadBusy(true);
    readLockRef.current = requestOwner;
    readControllerRef.current = { owner: requestOwner, controller };
    void operationsRef.current
      .list({
        registrationId: requestOwner.registrationId,
        query: { include_archived: "true", limit: "50" },
        signal: controller.signal,
      })
      .then((result) => {
        if (
          controller.signal.aborted ||
          !isLiveOwner(requestOwner) ||
          readEpochRef.current !== epoch
        )
          return;
        setArchive({
          owner: requestOwner,
          data: result.data,
          loading: false,
        });
      })
      .catch((cause: unknown) => {
        if (
          !controller.signal.aborted &&
          isLiveOwner(requestOwner) &&
          readEpochRef.current === epoch
        )
          setArchive({
            owner: requestOwner,
            loading: false,
            error: safeMessage(cause),
          });
      })
      .finally(() => {
        if (isLiveOwner(requestOwner) && readEpochRef.current === epoch) {
          readLockRef.current = undefined;
          if (readControllerRef.current?.controller === controller)
            readControllerRef.current = undefined;
          setReadBusy(false);
        }
      });
    return () => {
      controller.abort();
      if (readControllerRef.current?.owner === requestOwner) {
        readControllerRef.current.controller.abort();
        readControllerRef.current = undefined;
      }
    };
  }, [decisionOperations, owner, isLiveOwner]);

  const mutationBlocksActions =
    mutationState.kind === "submitting" ||
    mutationState.kind === "outcome-unknown";
  const reviewRequired =
    mutationState.kind === "conflict" ||
    mutationState.kind === "failed" ||
    mutationState.kind === "committed";

  async function readArchive(cursor?: string) {
    const requestOwner = owner;
    if (
      !isLiveOwner(requestOwner) ||
      readLockRef.current === requestOwner ||
      mutationRef.current?.controller.state.kind === "submitting" ||
      mutationRef.current?.controller.state.kind === "outcome-unknown" ||
      ((mutationRef.current?.controller.state.kind === "conflict" ||
        mutationRef.current?.controller.state.kind === "failed" ||
        mutationRef.current?.controller.state.kind === "committed") &&
        cursor !== undefined)
    )
      return;
    const epoch = ++readEpochRef.current;
    const previous = currentArchive;
    const controller = new AbortController();
    readLockRef.current = requestOwner;
    readControllerRef.current = { owner: requestOwner, controller };
    setReadBusy(true);
    setArchive({
      owner: requestOwner,
      data: previous?.data,
      loading: !cursor,
    });
    try {
      const result = await operationsRef.current.list({
        registrationId: requestOwner.registrationId,
        query: {
          include_archived: "true",
          ...(cursor ? { cursor } : {}),
          limit: "50",
        },
        signal: controller.signal,
      });
      if (!isLiveOwner(requestOwner) || readEpochRef.current !== epoch) return;
      setArchive({
        owner: requestOwner,
        data:
          cursor && previous?.data
            ? {
                ...previous.data,
                items: [...previous.data.items, ...result.data.items],
                next_cursor: result.data.next_cursor,
              }
            : result.data,
        loading: false,
      });
      if (
        mutationRef.current?.owner === requestOwner &&
        (mutationRef.current.controller.state.kind === "conflict" ||
          mutationRef.current.controller.state.kind === "failed" ||
          mutationRef.current.controller.state.kind === "committed")
      )
        mutationRef.current.controller.reset();
    } catch (cause) {
      if (isLiveOwner(requestOwner) && readEpochRef.current === epoch)
        setArchive({
          owner: requestOwner,
          data: previous?.data,
          loading: false,
          error: safeMessage(cause),
        });
    } finally {
      if (isLiveOwner(requestOwner) && readEpochRef.current === epoch) {
        readLockRef.current = undefined;
        if (readControllerRef.current?.controller === controller)
          readControllerRef.current = undefined;
        setReadBusy(false);
      }
    }
  }

  async function restore(item: DecisionPage["items"][number]) {
    const requestOwner = owner;
    const currentMutation = mutationRef.current;
    if (
      !isLiveOwner(requestOwner) ||
      currentArchive?.owner !== requestOwner ||
      !currentArchive.data ||
      readLockRef.current === requestOwner ||
      mutationRef.current !== currentMutation ||
      currentMutation?.owner !== requestOwner
    )
      return;
    const controller = currentMutation.controller;
    const state = controller.state;
    const acknowledgedItem = currentArchive.data.items.find(
      (listed) => listed.decision.record.id === item.decision.record.id,
    );
    if (
      !acknowledgedItem ||
      acknowledgedItem.decision.etag !== item.decision.etag ||
      !acknowledgedItem.decision.record.archived
    )
      return;
    if (
      state.kind === "submitting" ||
      state.kind === "conflict" ||
      state.kind === "failed" ||
      state.kind === "committed" ||
      (state.kind === "outcome-unknown" &&
        controller.originalRequest?.decisionId !== item.decision.record.id)
    )
      return;

    setArchive((current) =>
      current?.owner === requestOwner
        ? { ...current, error: undefined }
        : current,
    );
    let result: RestoreData | undefined;
    if (state.kind === "outcome-unknown") {
      result = await controller.retryOriginal();
    } else {
      const request: RestoreRequest = {
        registrationId: requestOwner.registrationId,
        decisionId: item.decision.record.id,
        body: {
          schema_version: 1,
          expected_etag: acknowledgedItem.decision.etag,
          operation_id: crypto.randomUUID(),
        },
      };
      result = await controller.submit(request);
    }
    if (!isLiveOwner(requestOwner)) return;
    if (!result) return;

    const original = controller.originalRequest;
    if (
      !original ||
      original.registrationId !== requestOwner.registrationId ||
      original.decisionId !== result.record.id
    ) {
      setArchive((current) =>
        current?.owner === requestOwner
          ? {
              ...current,
              error:
                "The restore response did not match the requested decision. Review the archive before continuing.",
            }
          : current,
      );
      return;
    }

    readEpochRef.current += 1;
    if (readLockRef.current === requestOwner) {
      readLockRef.current = undefined;
      setReadBusy(false);
    }
    if (readControllerRef.current?.owner === requestOwner) {
      readControllerRef.current.controller.abort();
      readControllerRef.current = undefined;
    }
    setArchive((current) => {
      if (current?.owner !== requestOwner || !current.data) return current;
      return {
        owner: requestOwner,
        loading: false,
        data: {
          ...current.data,
          items: current.data.items.map((listed) =>
            listed.decision.record.id === result.record.id
              ? { ...listed, decision: result }
              : listed,
          ),
        },
      };
    });
    controller.reset();
    if (isLiveOwner(requestOwner)) decisionsChangedRef.current();
  }

  const archived =
    currentArchive?.data?.items.filter(
      (item) => item.decision.record.archived,
    ) ?? [];
  const stateMessage =
    mutationState.kind === "outcome-unknown"
      ? "The restore outcome is unknown. Retry the same restore action to learn whether it completed."
      : mutationState.kind === "conflict" || mutationState.kind === "failed"
        ? mutationState.message
        : undefined;
  const currentDecisionId = mutation.originalRequest?.decisionId ?? undefined;

  return (
    <article className="document">
      <h1 ref={headingRef} tabIndex={-1}>
        {project.name}
      </h1>
      <WarningList warnings={project.warnings} />
      <p className="muted">Project folder</p>
      <div className="section">
        <p className="muted">Project location</p>
        <p className="path">{project.path}</p>
      </div>
      <section className="section">
        <h2>Decisions</h2>
        <p className="muted">Define the question and allowed answers.</p>
        {project.decisions.length > 0 && (
          <DataTable
            caption="Project decisions"
            rows={project.decisions}
            rowId={(row) => row.id}
            columns={[
              {
                key: "name",
                heading: "Decision",
                render: (row) => (
                  <button
                    className="text-button"
                    onClick={() => onDecision(row)}
                  >
                    {row.name}
                  </button>
                ),
              },
              {
                key: "id",
                heading: "ID",
                render: (row) => <code>{row.id}</code>,
              },
            ]}
          />
        )}
        <button className="primary" onClick={onCreateDecision}>
          Create decision
        </button>
      </section>
      <section className="section">
        <h2>Examples</h2>
        <p className="muted">
          Add inputs now, even before defining a decision.
        </p>
        {project.datasets.length > 0 && (
          <DataTable
            caption="Project datasets"
            rows={project.datasets}
            rowId={(row) => row.id}
            columns={[
              { key: "name", heading: "Dataset", render: (row) => row.name },
            ]}
          />
        )}
        <div className="actions">
          <button onClick={onCreateDataset}>Create dataset</button>
          <button onClick={onExamples}>Open examples</button>
        </div>
      </section>
      <section className="section">
        <h2>Archived decisions</h2>
        {currentArchive?.error && (
          <ErrorSummary message={currentArchive.error} />
        )}
        {stateMessage && <ErrorSummary message={stateMessage} />}
        {(!currentArchive ||
          (currentArchive.loading && !currentArchive.data)) && (
          <LoadingState>Loading decision archive…</LoadingState>
        )}
        {currentArchive?.loading && currentArchive.data && (
          <LoadingState>Refreshing decision archive…</LoadingState>
        )}
        {currentArchive?.data &&
          archived.length === 0 &&
          !currentArchive.loading && (
            <p className="muted">No archived decisions.</p>
          )}
        {archived.length > 0 && (
          <DataTable
            caption="Archived decisions"
            rows={archived}
            rowId={(row) => row.decision.record.id}
            columns={[
              {
                key: "name",
                heading: "Decision",
                render: (row) => row.decision.record.name,
              },
              {
                key: "id",
                heading: "ID",
                render: (row) => <code>{row.decision.record.id}</code>,
              },
              {
                key: "restore",
                heading: "Action",
                render: (row) => (
                  <button
                    disabled={
                      (mutationBlocksActions &&
                        !(
                          mutationState.kind === "outcome-unknown" &&
                          currentDecisionId === row.decision.record.id
                        )) ||
                      reviewRequired ||
                      readBusy ||
                      currentArchive?.loading
                    }
                    onClick={() => void restore(row)}
                  >
                    {mutationState.kind === "submitting" &&
                    currentDecisionId === row.decision.record.id
                      ? "Restoring…"
                      : mutationState.kind === "outcome-unknown" &&
                          currentDecisionId === row.decision.record.id
                        ? "Retry same restore action"
                        : "Restore"}
                  </button>
                ),
              },
            ]}
          />
        )}
        {reviewRequired ? (
          <button
            type="button"
            disabled={readBusy}
            onClick={() => void readArchive()}
          >
            Review archived decisions
          </button>
        ) : currentArchive?.error ? (
          <button
            type="button"
            disabled={readBusy || mutationBlocksActions}
            onClick={() => void readArchive()}
          >
            Reload archived decisions
          </button>
        ) : null}
        {currentArchive?.data?.next_cursor && (
          <button
            type="button"
            disabled={readBusy || mutationBlocksActions || reviewRequired}
            onClick={() =>
              void readArchive(currentArchive.data?.next_cursor ?? undefined)
            }
          >
            Load more decisions
          </button>
        )}
      </section>
      {navigationGuard.prompt}
    </article>
  );
}
