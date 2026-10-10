import { useEffect, useState } from "react";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { ApiError, safeMessage } from "../../api/client";
import { ExpectedAnswers } from "../../components/ExpectedAnswers";
import { JsonSourceEditor } from "../../components/JsonSourceEditor";
import {
  LoadingState,
  ErrorSummary,
  EmptyState,
} from "../../components/States";
import { Modal } from "../../components/Modal";
import type {
  ProjectOverview,
  DatasetAuthoringOperations,
  ExampleAuthoringOperations,
  ResourceSummary,
} from "../../workspace/gateway";
import { useDirtyNavigationGuard } from "../../workspace/NavigationGuardPrompt";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import { isOutcomeUnknown } from "../../workspace/mutation-controller";
import { DataTable } from "../../components/DataTable";

type CasePage =
  ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">;
type CaseRead =
  ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get">;
type DatasetRead =
  ApiOperationData<"read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get">;
type LabelPage =
  ApiOperationData<"list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get">;
type LabelView =
  ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">;
type LabelMutationBody =
  ApiOperationBody<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
type CaseEditBody =
  ApiOperationBody<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">;
type AddCaseBody =
  ApiOperationBody<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post">;
type RemoveCaseBody =
  ApiOperationBody<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">;

const opId = () => crypto.randomUUID();

export function ExamplesPage({
  project,
  decision,
  operations,
  datasetOperations,
  navigation,
  datasetFromRoute,
  caseFromRoute,
  refreshToken,
  onDatasetChange,
  onImport,
  onSplit,
}: {
  project: ProjectOverview;
  decision?: ResourceSummary;
  operations: ExampleAuthoringOperations;
  datasetOperations: DatasetAuthoringOperations;
  navigation: WorkspaceNavigation;
  datasetFromRoute?: string;
  caseFromRoute?: string;
  refreshToken: number;
  onDatasetChange: (datasetId?: string, caseId?: string) => Promise<boolean>;
  onImport: () => void;
  onSplit: () => void;
}) {
  const registrationId = project.id;
  const [datasetId, setDatasetId] = useState(datasetFromRoute ?? "");
  const [dataset, setDataset] = useState<DatasetRead>();
  const [cases, setCases] = useState<CasePage>();
  const [caseCursor, setCaseCursor] = useState<string>();
  const [labels, setLabels] = useState<LabelPage>();
  const [labelCursor, setLabelCursor] = useState<string>();
  const [selectedCaseId, setSelectedCaseId] = useState(caseFromRoute);
  const [caseRead, setCaseRead] = useState<CaseRead>();
  const [labelView, setLabelView] = useState<LabelView>();
  const [stagedAnswers, setStagedAnswers] = useState<readonly string[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mutationInFlight, setMutationInFlight] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [editCase, setEditCase] = useState(false);
  const [inputSource, setInputSource] = useState("");
  const [metadataSource, setMetadataSource] = useState("");
  const [inputKind, setInputKind] = useState<"text" | "json">("text");
  const [note, setNote] = useState("");
  const [addCaseOpen, setAddCaseOpen] = useState(false);
  const [deleteCaseOpen, setDeleteCaseOpen] = useState(false);
  const [newInputKind, setNewInputKind] = useState<"text" | "json">("text");
  const [newInputSource, setNewInputSource] = useState("");
  const [newMetadataSource, setNewMetadataSource] = useState("{}");
  const [refreshGeneration, setRefreshGeneration] = useState(0);
  const [editorDirty, setEditorDirty] = useState(false);
  const [pendingLabel, setPendingLabel] = useState<{
    body: LabelMutationBody;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [pendingCase, setPendingCase] = useState<{
    body: CaseEditBody;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [pendingAdd, setPendingAdd] = useState<{
    body: AddCaseBody;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [pendingRemove, setPendingRemove] = useState<{
    body: RemoveCaseBody;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [caseConflictReviewed, setCaseConflictReviewed] = useState(false);
  const [addConflictReviewed, setAddConflictReviewed] = useState(false);
  const [removeConflictReviewed, setRemoveConflictReviewed] = useState(false);

  useEffect(() => {
    setDatasetId(datasetFromRoute ?? "");
    setSelectedCaseId(caseFromRoute);
  }, [caseFromRoute, datasetFromRoute]);

  useEffect(() => {
    if (!datasetId && project.datasets[0]) setDatasetId(project.datasets[0].id);
  }, [datasetId, project.datasets]);

  useEffect(() => {
    if (!datasetId) {
      setDataset(undefined);
      setCases(undefined);
      setLabels(undefined);
      setCaseRead(undefined);
      setLabelView(undefined);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(undefined);
    setCases(undefined);
    setLabels(undefined);
    setCaseRead(undefined);
    setLabelView(undefined);
    void Promise.all([
      operations.listCases({
        registrationId,
        datasetId,
        query: { limit: "50" },
        signal: controller.signal,
      }),
      datasetOperations.read({
        registrationId,
        datasetId,
        signal: controller.signal,
      }),
      decision
        ? operations.listLabels({
            registrationId,
            decisionId: decision.id,
            datasetId,
            query: { limit: "50" },
            signal: controller.signal,
          })
        : Promise.resolve(undefined),
    ])
      .then(([casePage, datasetResult, labelPage]) => {
        if (controller.signal.aborted) return;
        setCases(casePage.data);
        setCaseCursor(casePage.data.next_cursor ?? undefined);
        setDataset(datasetResult.data);
        if (labelPage) {
          setLabels(labelPage.data);
          setLabelCursor(labelPage.data.next_cursor ?? undefined);
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(safeMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [
    datasetOperations,
    decision,
    datasetId,
    operations,
    registrationId,
    refreshGeneration,
    refreshToken,
  ]);

  useEffect(() => {
    if (!datasetId || !selectedCaseId) {
      setCaseRead(undefined);
      setLabelView(undefined);
      setStagedAnswers([]);
      return;
    }
    const controller = new AbortController();
    setError(undefined);
    void Promise.all([
      operations.readCase({
        registrationId,
        datasetId,
        caseId: selectedCaseId,
        signal: controller.signal,
      }),
      decision
        ? operations.readLabel({
            registrationId,
            decisionId: decision.id,
            datasetId,
            caseId: selectedCaseId,
            signal: controller.signal,
          })
        : Promise.resolve(undefined),
    ])
      .then(([caseResult, labelResult]) => {
        if (controller.signal.aborted) return;
        setCaseRead(caseResult.data);
        setInputKind(caseResult.data.case.record.input_kind);
        setInputSource(caseResult.data.case.record.input_source);
        setMetadataSource(caseResult.data.case.record.metadata_source ?? "{}");
        setLabelView(labelResult?.data);
        setStagedAnswers(labelResult?.data.label?.acceptable_option_ids ?? []);
        setEditorDirty(false);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(safeMessage(cause));
      });
    return () => controller.abort();
  }, [decision, datasetId, operations, registrationId, selectedCaseId]);

  async function loadMoreCases() {
    if (!datasetId || !caseCursor || busy) return;
    setBusy(true);
    try {
      const result = await operations.listCases({
        registrationId,
        datasetId,
        query: { cursor: caseCursor, limit: "50" },
      });
      setCases((current) =>
        current
          ? {
              ...current,
              items: [...current.items, ...result.data.items],
              next_cursor: result.data.next_cursor,
            }
          : result.data,
      );
      setCaseCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function loadMoreLabels() {
    if (!datasetId || !decision || !labelCursor || busy) return;
    setBusy(true);
    try {
      const result = await operations.listLabels({
        registrationId,
        decisionId: decision.id,
        datasetId,
        query: { cursor: labelCursor, limit: "50" },
      });
      setLabels((current) =>
        current
          ? {
              ...current,
              items: [...current.items, ...result.data.items],
              next_cursor: result.data.next_cursor,
            }
          : result.data,
      );
      setLabelCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function selectCase(caseId: string) {
    if (caseId === selectedCaseId || !datasetId) return;
    const moved = await onDatasetChange(datasetId, caseId);
    if (!moved) return;
    setSelectedCaseId(caseId);
  }

  async function saveLabel(
    action: "set" | "resolve" | "dispute" | "clear",
  ): Promise<boolean> {
    if (
      !decision ||
      !datasetId ||
      !labelView ||
      (stagedAnswers.length === 0 && action !== "clear" && action !== "dispute")
    )
      return false;
    if (pendingLabel?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const body: LabelMutationBody = pendingLabel?.uncertain
      ? pendingLabel.body
      : {
          schema_version: 1,
          operation_id: opId(),
          edits: [
            {
              review: labelView.review,
              action,
              ...(action === "set" || action === "resolve"
                ? { acceptable_option_ids: stagedAnswers }
                : {}),
              ...(action === "set" || action === "resolve"
                ? { provenance: "human" as const }
                : {}),
              ...(note ? { note } : {}),
            },
          ],
        };
    try {
      await operations.saveLabels({
        registrationId,
        decisionId: decision.id,
        datasetId,
        body,
      });
      setPendingLabel(undefined);
      setNote("");
      const refreshed = await operations.readLabel({
        registrationId,
        decisionId: decision.id,
        datasetId,
        caseId: selectedCaseId!,
      });
      setLabelView(refreshed.data);
      setStagedAnswers(refreshed.data.label?.acceptable_option_ids ?? []);
      setEditorDirty(false);
      const page = await operations.listLabels({
        registrationId,
        decisionId: decision.id,
        datasetId,
        query: { limit: "50" },
      });
      setLabels(page.data);
      setLabelCursor(page.data.next_cursor ?? undefined);
    } catch (cause) {
      if (isOutcomeUnknown(cause))
        setPendingLabel({ body, uncertain: true, conflict: false });
      else if (cause instanceof ApiError && cause.status === 409)
        setPendingLabel({ body, uncertain: false, conflict: true });
      else setPendingLabel(undefined);
      setError(safeMessage(cause));
      return false;
    } finally {
      setBusy(false);
      setMutationInFlight(false);
    }
    return true;
  }

  async function reviewLabelConflict(): Promise<void> {
    if (!decision || !datasetId || !selectedCaseId) return;
    setBusy(true);
    setError(undefined);
    try {
      const refreshed = await operations.readLabel({
        registrationId,
        decisionId: decision.id,
        datasetId,
        caseId: selectedCaseId,
      });
      // Keep the user's staged answer intact. A new deliberate save will use
      // this reviewed server context and a fresh operation ID.
      setLabelView(refreshed.data);
      setPendingLabel(undefined);
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  function retryUnknownLabel() {
    const action = pendingLabel?.body.edits[0]?.action;
    if (pendingLabel?.uncertain && action) void saveLabel(action);
  }

  async function saveCase(): Promise<boolean> {
    if (!dataset || !caseRead || !selectedCaseId) return false;
    if (pendingCase?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const record = caseRead.case.record;
    const body: CaseEditBody = pendingCase?.uncertain
      ? pendingCase.body
      : {
          schema_version: 1,
          operation_id: opId(),
          expected_case_etag: caseRead.case.etag,
          expected_dataset_etag: dataset.etag,
          input_kind: inputKind,
          input_source: inputSource,
          tags: record.tags ?? [],
          split: record.split ?? "development",
          group_id: record.group_id ?? null,
          derived_from: record.derived_from ?? [],
          metadata_source: metadataSource,
        };
    try {
      await operations.editCase({
        registrationId,
        datasetId,
        caseId: selectedCaseId,
        body,
      });
      setPendingCase(undefined);
      setCaseConflictReviewed(false);
      setEditCase(false);
      setEditorDirty(false);
      const refreshed = await operations.readCase({
        registrationId,
        datasetId,
        caseId: selectedCaseId,
      });
      setCaseRead(refreshed.data);
      const refreshedDataset = await datasetOperations.read({
        registrationId,
        datasetId,
      });
      setDataset(refreshedDataset.data);
      if (decision) {
        const refreshedLabel = await operations.readLabel({
          registrationId,
          decisionId: decision.id,
          datasetId,
          caseId: selectedCaseId,
        });
        setLabelView(refreshedLabel.data);
      }
      const page = await operations.listCases({
        registrationId,
        datasetId,
        query: { limit: "50" },
      });
      setCases(page.data);
      setCaseCursor(page.data.next_cursor ?? undefined);
    } catch (cause) {
      if (isOutcomeUnknown(cause))
        setPendingCase({ body, uncertain: true, conflict: false });
      else if (cause instanceof ApiError && cause.status === 409) {
        setPendingCase({ body, uncertain: false, conflict: true });
        setCaseConflictReviewed(false);
      } else setPendingCase(undefined);
      setError(safeMessage(cause));
      return false;
    } finally {
      setBusy(false);
      setMutationInFlight(false);
    }
    return true;
  }

  async function reviewCaseConflict() {
    if (!dataset || !caseRead || !selectedCaseId) return;
    setBusy(true);
    setError(undefined);
    try {
      const [currentCase, currentDataset] = await Promise.all([
        operations.readCase({
          registrationId,
          datasetId,
          caseId: selectedCaseId,
        }),
        datasetOperations.read({ registrationId, datasetId }),
      ]);
      setCaseRead(currentCase.data);
      setDataset(currentDataset.data);
      setPendingCase(undefined);
      setCaseConflictReviewed(true);
      setNotice(
        "Current case and dataset versions reviewed. Your edited source is retained; reapply it deliberately.",
      );
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function addCase(): Promise<boolean> {
    if (!dataset) return false;
    if (pendingAdd?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const body: AddCaseBody = pendingAdd?.uncertain
      ? pendingAdd.body
      : {
          schema_version: 1,
          operation_id: opId(),
          expected_dataset_etag: dataset.etag,
          input_kind: newInputKind,
          input_source: newInputSource,
          metadata_source: newMetadataSource,
          tags: [],
          split: "development",
          group_id: null,
          derived_from: [],
        };
    try {
      const result = await operations.addCase({
        registrationId,
        datasetId,
        body,
      });
      setPendingAdd(undefined);
      setAddConflictReviewed(false);
      const createdId = result.data.case?.record.id;
      setAddCaseOpen(false);
      setEditorDirty(false);
      setNewInputSource("");
      setNewInputKind("text");
      setNewMetadataSource("{}");
      setRefreshGeneration((value) => value + 1);
      if (createdId) {
        setNotice("Example added. Select it from the cases list when ready.");
      }
    } catch (cause) {
      if (isOutcomeUnknown(cause))
        setPendingAdd({ body, uncertain: true, conflict: false });
      else if (cause instanceof ApiError && cause.status === 409) {
        setPendingAdd({ body, uncertain: false, conflict: true });
        setAddConflictReviewed(false);
      } else setPendingAdd(undefined);
      setError(safeMessage(cause));
      return false;
    } finally {
      setBusy(false);
      setMutationInFlight(false);
    }
    return true;
  }

  async function reviewAddConflict() {
    if (!dataset) return;
    setBusy(true);
    setError(undefined);
    try {
      const [currentDataset, currentCases] = await Promise.all([
        datasetOperations.read({ registrationId, datasetId }),
        operations.listCases({
          registrationId,
          datasetId,
          query: { limit: "50" },
        }),
      ]);
      setDataset(currentDataset.data);
      setCases(currentCases.data);
      setCaseCursor(currentCases.data.next_cursor ?? undefined);
      setPendingAdd(undefined);
      setAddConflictReviewed(true);
      setNotice(
        "Current dataset and cases reviewed. Your new example source is retained; reapply it deliberately.",
      );
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function removeSelectedCase() {
    if (!dataset || !caseRead || !selectedCaseId) return;
    if (pendingRemove?.conflict) return;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const body: RemoveCaseBody = pendingRemove?.uncertain
      ? pendingRemove.body
      : {
          schema_version: 1,
          operation_id: opId(),
          expected_case_etag: caseRead.case.etag,
          expected_dataset_etag: dataset.etag,
        };
    try {
      const result = await operations.removeCase({
        registrationId,
        datasetId,
        caseId: selectedCaseId,
        body,
      });
      setPendingRemove(undefined);
      setRemoveConflictReviewed(false);
      const cleared = result.data.cleared_label_ids;
      setDeleteCaseOpen(false);
      setRefreshGeneration((value) => value + 1);
      setNotice(
        "Case removed. Its last reviewed view remains until you select another case.",
      );
      if (cleared.length)
        setNotice(
          `Case removed. ${cleared.length} current label record(s) were cleared; label history remains available.`,
        );
    } catch (cause) {
      if (isOutcomeUnknown(cause))
        setPendingRemove({ body, uncertain: true, conflict: false });
      else if (cause instanceof ApiError && cause.status === 409) {
        setPendingRemove({ body, uncertain: false, conflict: true });
        setRemoveConflictReviewed(false);
      } else setPendingRemove(undefined);
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
      setMutationInFlight(false);
    }
  }

  async function reviewRemoveConflict() {
    if (!dataset || !caseRead || !selectedCaseId) return;
    setBusy(true);
    setError(undefined);
    try {
      const [currentCase, currentDataset] = await Promise.all([
        operations.readCase({
          registrationId,
          datasetId,
          caseId: selectedCaseId,
        }),
        datasetOperations.read({ registrationId, datasetId }),
      ]);
      setCaseRead(currentCase.data);
      setDataset(currentDataset.data);
      setPendingRemove(undefined);
      setRemoveConflictReviewed(true);
      setNotice(
        "Current case and dataset versions reviewed. Reapply removal deliberately if the case is still present.",
      );
    } catch (cause) {
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  const currentCase = caseRead?.case.record;
  const currentLabel = labelView?.label;
  const labelSetChanged =
    !!decision &&
    !!labelView &&
    [...stagedAnswers].sort().join("\0") !==
      [...(currentLabel?.acceptable_option_ids ?? [])].sort().join("\0");
  async function saveBeforeLeaving() {
    if (
      pendingLabel?.uncertain ||
      pendingCase?.uncertain ||
      pendingAdd?.uncertain ||
      pendingRemove?.uncertain
    )
      throw new Error(
        "A write may have completed. Retry its original request before leaving this examples page.",
      );
    if (
      pendingLabel?.conflict ||
      pendingCase?.conflict ||
      pendingAdd?.conflict ||
      pendingRemove?.conflict
    )
      throw new Error(
        "Review the current server state before reapplying or explicitly discarding this conflicted change.",
      );
    if (addCaseOpen && !(await addCase()))
      throw new Error(
        "The new example did not save. Its source is still available for review.",
      );
    const savedCase = editCase;
    if (savedCase && !(await saveCase()))
      throw new Error(
        "The case edit did not save. Its source is still available for review.",
      );
    if (decision && labelView && (labelSetChanged || note.trim())) {
      if (savedCase)
        throw new Error(
          "The case was saved. Review the refreshed label context before saving its answer.",
        );
      if (stagedAnswers.length === 0)
        throw new Error(
          "Choose an answer or explicitly clear this label before leaving.",
        );
      const action = currentLabel?.status === "disputed" ? "resolve" : "set";
      if (!(await saveLabel(action)))
        throw new Error(
          "The label did not save. Its staged answer is still available for review.",
        );
    }
  }
  const uncertainWrite = !!(
    pendingLabel?.uncertain ||
    pendingCase?.uncertain ||
    pendingAdd?.uncertain ||
    pendingRemove?.uncertain
  );
  const unresolvedConflict = !!(
    pendingLabel?.conflict ||
    pendingCase?.conflict ||
    pendingAdd?.conflict ||
    pendingRemove?.conflict
  );
  const navigationBlockedMessage = uncertainWrite
    ? "A write may have completed. Keep editing and retry its original request before leaving this examples page."
    : mutationInFlight
      ? "An examples write is still in progress. Keep this page open until it finishes."
      : undefined;
  const dirtyGuard = useDirtyNavigationGuard({
    dirty:
      editorDirty ||
      labelSetChanged ||
      (decision !== undefined && note.trim().length > 0) ||
      uncertainWrite ||
      unresolvedConflict ||
      mutationInFlight,
    blockedMessage: navigationBlockedMessage,
    save: saveBeforeLeaving,
    discard: () => {
      setEditorDirty(false);
      setNote("");
      if (currentCase) {
        setInputKind(currentCase.input_kind);
        setInputSource(currentCase.input_source);
        setMetadataSource(currentCase.metadata_source ?? "{}");
      }
      setStagedAnswers(currentLabel?.acceptable_option_ids ?? []);
      setEditCase(false);
      setAddCaseOpen(false);
      setDeleteCaseOpen(false);
      if (pendingLabel?.conflict) setPendingLabel(undefined);
      if (pendingCase?.conflict) setPendingCase(undefined);
      if (pendingAdd?.conflict) setPendingAdd(undefined);
      if (pendingRemove?.conflict) setPendingRemove(undefined);
      setCaseConflictReviewed(false);
      setAddConflictReviewed(false);
      setRemoveConflictReviewed(false);
    },
  });
  useEffect(
    () =>
      navigation.registerDirtyGuard(
        `examples:${registrationId}:${datasetId}:${decision?.id ?? "none"}`,
        dirtyGuard.guard,
      ),
    [datasetId, decision?.id, dirtyGuard.guard, navigation, registrationId],
  );
  const optionRows =
    labelView?.definition.questions[0].options.map((option) => ({
      id: option.id,
      name: option.name,
    })) ?? [];
  return (
    <>
      <article className="document examples-page">
        <header className="page-heading-row">
          <div>
            <h1>Examples</h1>
            <p className="muted">
              {decision
                ? `Labels for ${decision.name}`
                : "Project examples · no decision selected"}
            </p>
          </div>
          <div className="actions">
            <button type="button" onClick={onImport}>
              Import examples
            </button>
            <button type="button" onClick={onSplit} disabled={!datasetId}>
              Split dataset
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => setAddCaseOpen(true)}
              disabled={!datasetId}
            >
              Add example
            </button>
          </div>
        </header>
        {error && <ErrorSummary message={error} />}
        {notice && (
          <p role="status" className="save-status">
            {notice}
          </p>
        )}
        <div className="dataset-selector field">
          <label htmlFor="examples-dataset">Dataset</label>
          <select
            id="examples-dataset"
            value={datasetId}
            onChange={(event) => {
              const nextDatasetId = event.target.value;
              void onDatasetChange(nextDatasetId || undefined, undefined).then(
                (moved) => {
                  if (!moved) return;
                  setDatasetId(nextDatasetId);
                  setSelectedCaseId(undefined);
                },
              );
            }}
          >
            <option value="">Choose a dataset</option>
            {project.datasets.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        {!datasetId ? (
          <EmptyState title="Choose or create a dataset">
            Examples can be imported before a decision is created.
          </EmptyState>
        ) : loading || !cases ? (
          <LoadingState>Loading examples…</LoadingState>
        ) : cases.items.length === 0 ? (
          <EmptyState title="No examples yet">
            Add an example or import a CSV or JSONL file.
          </EmptyState>
        ) : (
          <div className="examples-layout">
            <section aria-labelledby="cases-heading">
              <h2 id="cases-heading">Cases</h2>
              <DataTable
                caption={`Cases in ${project.datasets.find((item) => item.id === datasetId)?.name ?? "selected dataset"}`}
                rows={cases.items}
                rowId={(item) => item.record.id}
                columns={[
                  {
                    key: "id",
                    heading: "Case",
                    render: (item) => (
                      <button
                        className="text-button"
                        onClick={() => selectCase(item.record.id)}
                      >
                        {item.record.id}
                      </button>
                    ),
                  },
                  {
                    key: "input",
                    heading: "Input preview",
                    render: (item) => (
                      <span className="source-preview">
                        {item.record.input_source.slice(0, 120)}
                      </span>
                    ),
                  },
                  {
                    key: "split",
                    heading: "Split",
                    render: (item) => item.record.split ?? "development",
                  },
                  {
                    key: "tags",
                    heading: "Tags",
                    render: (item) =>
                      (item.record.tags ?? []).join(", ") || "—",
                  },
                ]}
              />
              {caseCursor && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void loadMoreCases()}
                >
                  {busy ? "Loading…" : "Load more cases"}
                </button>
              )}
            </section>
            {decision && (
              <section aria-labelledby="label-list-heading">
                <h2 id="label-list-heading">Labels for {decision.name}</h2>
                {labels?.items.length ? (
                  <DataTable
                    caption={`Expected answers for ${decision.name}`}
                    rows={labels.items}
                    rowId={(item) => item.case.id}
                    columns={[
                      {
                        key: "case",
                        heading: "Case",
                        render: (item) => (
                          <button
                            className="text-button"
                            onClick={() => selectCase(item.case.id)}
                          >
                            {item.case.id}
                          </button>
                        ),
                      },
                      {
                        key: "answer",
                        heading: "Expected answer",
                        render: (item) =>
                          item.label?.acceptable_option_ids
                            .map(
                              (id) =>
                                item.definition.questions[0].options.find(
                                  (option) => option.id === id,
                                )?.name ?? id,
                            )
                            .join(", ") ?? "Unlabelled",
                      },
                      {
                        key: "status",
                        heading: "Status",
                        render: (item) =>
                          item.reasons.length
                            ? item.reasons.join(", ")
                            : item.status,
                      },
                    ]}
                  />
                ) : (
                  <p className="muted">
                    No labels are recorded for this decision and dataset.
                  </p>
                )}
                {labelCursor && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void loadMoreLabels()}
                  >
                    {busy ? "Loading…" : "Load more labels"}
                  </button>
                )}
              </section>
            )}
          </div>
        )}
        {selectedCaseId && currentCase && (
          <aside
            className="case-inspector"
            aria-labelledby="case-inspector-heading"
          >
            <header className="section-heading-row">
              <div>
                <h2 id="case-inspector-heading">{currentCase.id}</h2>
                <p className="muted">
                  Input, expected answers, and source context
                </p>
              </div>
              <button type="button" onClick={() => setEditCase(true)}>
                Edit input
              </button>
              <button type="button" onClick={() => setDeleteCaseOpen(true)}>
                Remove case
              </button>
            </header>
            <section className="section">
              <h3>Input</h3>
              <pre
                className="source-block"
                tabIndex={0}
                aria-label="Complete example input source"
              >
                {currentCase.input_source}
              </pre>
              <p className="muted">
                {currentCase.input_kind.toUpperCase()} · split{" "}
                {currentCase.split ?? "development"} · tags{" "}
                {(currentCase.tags ?? []).join(", ") || "none"}
              </p>
            </section>
            {decision && labelView ? (
              <section className="section label-review">
                <h3>Expected answers</h3>
                <p role="status">
                  {labelView.reasons.length
                    ? `Excluded: ${labelView.reasons.join(", ")}`
                    : labelView.status === "applicable"
                      ? `Applicable · ${currentLabel?.provenance ?? "unknown provenance"}`
                      : labelView.status}
                </p>
                {labelView.missing_option_ids.length > 0 && (
                  <p className="field-error">
                    Missing option IDs remain in this saved label:{" "}
                    {labelView.missing_option_ids.join(", ")}
                  </p>
                )}
                <ExpectedAnswers
                  options={optionRows}
                  selected={stagedAnswers}
                  onChange={(answers) => {
                    setStagedAnswers(answers);
                    setEditorDirty(true);
                  }}
                  onSave={() =>
                    void saveLabel(
                      currentLabel?.status === "disputed" ? "resolve" : "set",
                    )
                  }
                  saving={busy || pendingLabel?.uncertain}
                />
                {pendingLabel?.uncertain && (
                  <div className="warning-summary">
                    <p>
                      The label write outcome may be unknown. Retry the
                      identical request before changing its staged answer or
                      leaving this page.
                    </p>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={retryUnknownLabel}
                    >
                      Retry original label request
                    </button>
                  </div>
                )}
                {pendingLabel?.conflict && (
                  <div className="warning-summary">
                    <p>
                      The label changed elsewhere. Review the current saved
                      answer before deliberately reapplying your staged set.
                    </p>
                    <button
                      disabled={busy}
                      onClick={() => void reviewLabelConflict()}
                    >
                      Review current label
                    </button>
                  </div>
                )}
                {currentLabel?.status === "disputed" && (
                  <button
                    disabled={busy || pendingLabel?.uncertain}
                    onClick={() => void saveLabel("resolve")}
                  >
                    Resolve dispute with staged set
                  </button>
                )}
                {currentLabel && currentLabel.status !== "disputed" && (
                  <button
                    disabled={busy || pendingLabel?.uncertain}
                    onClick={() => void saveLabel("dispute")}
                  >
                    Dispute label
                  </button>
                )}
                {currentLabel && (
                  <button
                    disabled={busy || pendingLabel?.uncertain}
                    onClick={() => void saveLabel("clear")}
                  >
                    Clear label
                  </button>
                )}
                <label htmlFor="label-note">Provenance note</label>
                <input
                  id="label-note"
                  value={note}
                  disabled={pendingLabel?.uncertain}
                  onChange={(event) => {
                    setNote(event.target.value);
                    setEditorDirty(true);
                  }}
                />
                {labelView.status === "excluded" && (
                  <p className="muted">
                    This expectation is excluded from correctness until its
                    stale, disputed, or incompatible state is resolved.
                  </p>
                )}
              </section>
            ) : (
              <p className="muted">
                Select a decision to review or save its expected answers.
              </p>
            )}
          </aside>
        )}
        {editCase && currentCase && caseRead && (
          <Modal
            title={`Edit ${currentCase.id}`}
            onDismiss={() => {
              if (!busy && !pendingCase?.uncertain) setEditCase(false);
            }}
          >
            <div className="modal-body case-editor">
              {pendingCase?.uncertain && (
                <div className="warning-summary">
                  <p>
                    The case edit outcome may be unknown. The exact request is
                    retained; retry it before closing or changing the source.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void saveCase()}
                  >
                    Retry same case edit
                  </button>
                </div>
              )}
              {pendingCase?.conflict && (
                <div className="warning-summary">
                  <p>
                    The case or dataset changed elsewhere. Your edited source
                    remains staged until you review the current versions.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reviewCaseConflict()}
                  >
                    Review current case and dataset
                  </button>
                </div>
              )}
              {caseConflictReviewed && (
                <p role="status">
                  Current case and dataset versions were reviewed. Reapply the
                  retained edit with a new request.
                </p>
              )}
              <fieldset>
                <legend>Input format</legend>
                {(["text", "json"] as const).map((kind) => (
                  <label key={kind}>
                    <input
                      type="radio"
                      checked={inputKind === kind}
                      disabled={busy || pendingCase?.uncertain}
                      onChange={() => {
                        setInputKind(kind);
                        setEditorDirty(true);
                      }}
                    />
                    {kind.toUpperCase()}
                  </label>
                ))}
              </fieldset>
              <JsonSourceEditor
                label="Input source"
                value={inputSource}
                readOnly={busy || pendingCase?.uncertain}
                onChange={(value) => {
                  setInputSource(value);
                  setEditorDirty(true);
                }}
              />
              <JsonSourceEditor
                label="Metadata source"
                value={metadataSource}
                readOnly={busy || pendingCase?.uncertain}
                onChange={(value) => {
                  setMetadataSource(value);
                  setEditorDirty(true);
                }}
              />
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={busy || !!pendingCase?.conflict}
                  onClick={() => void saveCase()}
                >
                  {busy
                    ? "Saving…"
                    : caseConflictReviewed
                      ? "Reapply reviewed case edit"
                      : "Save input"}
                </button>
                <button
                  type="button"
                  disabled={busy || pendingCase?.uncertain}
                  onClick={() => setEditCase(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </Modal>
        )}
        {addCaseOpen && dataset && (
          <Modal
            title="Add example"
            onDismiss={() => {
              if (!busy && !pendingAdd?.uncertain) setAddCaseOpen(false);
            }}
          >
            <div className="modal-body case-editor">
              {pendingAdd?.uncertain && (
                <div className="warning-summary">
                  <p>
                    The add outcome may be unknown. The exact request is
                    retained; retry it before closing or changing the source.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void addCase()}
                  >
                    Retry same add request
                  </button>
                </div>
              )}
              {pendingAdd?.conflict && (
                <div className="warning-summary">
                  <p>
                    The dataset changed elsewhere. Your new example source
                    remains staged until you review current cases and the
                    dataset version.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reviewAddConflict()}
                  >
                    Review current cases and dataset
                  </button>
                </div>
              )}
              {addConflictReviewed && (
                <p role="status">
                  Current cases and dataset version were reviewed. Reapply the
                  retained example with a new request.
                </p>
              )}
              <fieldset>
                <legend>Input format</legend>
                {(["text", "json"] as const).map((kind) => (
                  <label key={kind}>
                    <input
                      type="radio"
                      checked={newInputKind === kind}
                      disabled={busy || pendingAdd?.uncertain}
                      onChange={() => {
                        setNewInputKind(kind);
                        setEditorDirty(true);
                      }}
                    />
                    {kind.toUpperCase()}
                  </label>
                ))}
              </fieldset>
              <JsonSourceEditor
                label="Input source"
                value={newInputSource}
                readOnly={busy || pendingAdd?.uncertain}
                onChange={(value) => {
                  setNewInputSource(value);
                  setEditorDirty(true);
                }}
              />
              <JsonSourceEditor
                label="Metadata source"
                value={newMetadataSource}
                readOnly={busy || pendingAdd?.uncertain}
                onChange={(value) => {
                  setNewMetadataSource(value);
                  setEditorDirty(true);
                }}
              />
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={busy || !!pendingAdd?.conflict}
                  onClick={() => void addCase()}
                >
                  {busy
                    ? "Adding…"
                    : addConflictReviewed
                      ? "Reapply reviewed example"
                      : "Add example"}
                </button>
                <button
                  type="button"
                  disabled={busy || pendingAdd?.uncertain}
                  onClick={() => setAddCaseOpen(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </Modal>
        )}
        {deleteCaseOpen && currentCase && (
          <Modal
            title={`Remove ${currentCase.id}?`}
            onDismiss={() => {
              if (!busy && !pendingRemove?.uncertain) setDeleteCaseOpen(false);
            }}
          >
            <div className="modal-body">
              <p>
                Removing this case clears its current labels from each decision
                while preserving label history. Re-adding the same ID later
                starts unlabelled.
              </p>
              {pendingRemove?.uncertain && (
                <div className="warning-summary">
                  <p>
                    The removal outcome may be unknown. Retry the identical
                    request before closing this confirmation.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void removeSelectedCase()}
                  >
                    Retry same removal
                  </button>
                </div>
              )}
              {pendingRemove?.conflict && (
                <div className="warning-summary">
                  <p>
                    The case or dataset changed elsewhere. Review the current
                    case and dataset versions before reapplying removal.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reviewRemoveConflict()}
                  >
                    Review current case and dataset
                  </button>
                </div>
              )}
              {removeConflictReviewed && (
                <p role="status">
                  Current case and dataset versions were reviewed. Reapply
                  removal deliberately.
                </p>
              )}
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={busy || !!pendingRemove?.conflict}
                  onClick={() => void removeSelectedCase()}
                >
                  {busy
                    ? "Removing…"
                    : removeConflictReviewed
                      ? "Reapply reviewed removal"
                      : "Remove case"}
                </button>
                <button
                  type="button"
                  disabled={busy || pendingRemove?.uncertain}
                  onClick={() => setDeleteCaseOpen(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </Modal>
        )}
      </article>
      {dirtyGuard.prompt}
    </>
  );
}
