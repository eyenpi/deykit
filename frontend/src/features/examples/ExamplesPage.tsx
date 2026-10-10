import { useEffect, useRef, useState } from "react";
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
type LabelMutationReceipt =
  ApiOperationData<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
type CaseEditBody =
  ApiOperationBody<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">;
type CaseMutationReceipt =
  ApiOperationData<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">;
type AddCaseBody =
  ApiOperationBody<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post">;
type RemoveCaseBody =
  ApiOperationBody<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">;

type ReadContext = {
  registrationId: string;
  datasetId: string;
  decisionId?: string;
  selectedCaseId?: string;
  refreshGeneration: number;
  refreshToken: number;
};

type CommittedRefresh =
  | {
      kind: "label";
      context: ReadContext;
      decisionId: string;
      caseId: string;
      receipt: LabelMutationReceipt;
      body: LabelMutationBody;
      stagedGeneration: number;
      stagedAnswers: readonly string[];
      note: string;
    }
  | {
      kind: "case";
      context: ReadContext;
      caseId: string;
      decisionId?: string;
      receipt: CaseMutationReceipt;
      body: CaseEditBody;
      stagedGeneration: number;
      inputKind: "text" | "json";
      inputSource: string;
      metadataSource: string;
    };

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
  const [committedRefresh, setCommittedRefresh] = useState<CommittedRefresh>();
  const committedRefreshRef = useRef<CommittedRefresh>();
  const caseEditGeneration = useRef(0);
  const labelEditGeneration = useRef(0);
  const [caseConflictReviewed, setCaseConflictReviewed] = useState(false);
  const [addConflictReviewed, setAddConflictReviewed] = useState(false);
  const [removeConflictReviewed, setRemoveConflictReviewed] = useState(false);
  const currentReadContext = useRef<ReadContext>({
    registrationId,
    datasetId,
    decisionId: decision?.id,
    selectedCaseId,
    refreshGeneration,
    refreshToken,
  });
  currentReadContext.current = {
    registrationId,
    datasetId,
    decisionId: decision?.id,
    selectedCaseId,
    refreshGeneration,
    refreshToken,
  };
  function isCurrentContext(context: typeof currentReadContext.current) {
    const current = currentReadContext.current;
    return (
      current.registrationId === context.registrationId &&
      current.datasetId === context.datasetId &&
      current.decisionId === context.decisionId &&
      current.selectedCaseId === context.selectedCaseId &&
      current.refreshGeneration === context.refreshGeneration &&
      current.refreshToken === context.refreshToken
    );
  }
  function isCommittedRefreshCurrent(pending: CommittedRefresh) {
    return (
      committedRefreshRef.current === pending &&
      isCurrentContext(pending.context) &&
      decision?.id === pending.context.decisionId
    );
  }
  function clearCommittedRefresh(pending: CommittedRefresh) {
    if (committedRefreshRef.current !== pending) return;
    committedRefreshRef.current = undefined;
    setCommittedRefresh(undefined);
  }
  async function refreshCommittedView(
    pending: CommittedRefresh,
  ): Promise<boolean> {
    if (!isCommittedRefreshCurrent(pending)) {
      setError(
        "The saved item belongs to a different selection. Reload it before editing.",
      );
      return false;
    }
    try {
      if (pending.kind === "label") {
        const submitted = pending.body.edits[0];
        if (!submitted)
          throw new Error("The saved label request is unavailable.");
        const receiptMatches = pending.receipt.changes.some(
          (change) =>
            change.operation_id === pending.body.operation_id &&
            change.case_id === pending.caseId &&
            change.dataset_id === pending.context.datasetId &&
            change.decision_id === pending.decisionId,
        );
        if (!receiptMatches)
          throw new Error("The saved label receipt did not match this review.");
        const refreshedLabel = await operations.readLabel({
          registrationId: pending.context.registrationId,
          decisionId: pending.decisionId,
          datasetId: pending.context.datasetId,
          caseId: pending.caseId,
        });
        if (!isCommittedRefreshCurrent(pending)) return false;
        const page = await operations.listLabels({
          registrationId: pending.context.registrationId,
          decisionId: pending.decisionId,
          datasetId: pending.context.datasetId,
          query: { limit: "50" },
        });
        if (!isCommittedRefreshCurrent(pending)) return false;
        const review = refreshedLabel.data.review;
        if (
          review.case_id !== pending.caseId ||
          review.dataset_id !== pending.context.datasetId ||
          review.decision_id !== pending.decisionId
        )
          throw new Error("The refreshed label belongs to a different review.");

        const reviewChanged =
          review.decision_etag !== submitted.review.decision_etag ||
          review.draft_etag !== submitted.review.draft_etag ||
          review.input_hash !== submitted.review.input_hash;
        setLabelView(refreshedLabel.data);
        setLabels(page.data);
        setLabelCursor(page.data.next_cursor ?? undefined);
        if (reviewChanged) {
          setPendingLabel({
            body: pending.body,
            uncertain: false,
            conflict: true,
          });
          setNotice(
            "Label saved. Its current review changed; review it before reapplying your staged answer.",
          );
        } else if (labelEditGeneration.current === pending.stagedGeneration) {
          setStagedAnswers(
            refreshedLabel.data.label?.acceptable_option_ids ?? [],
          );
          setNote("");
          setEditorDirty(false);
          setPendingLabel(undefined);
          setNotice(undefined);
        }
        clearCommittedRefresh(pending);
        setError(undefined);
        return true;
      }

      const receiptCase = pending.receipt.case;
      if (
        !receiptCase ||
        receiptCase.record.id !== pending.caseId ||
        receiptCase.record.dataset_id !== pending.context.datasetId ||
        pending.receipt.dataset.record.id !== pending.context.datasetId
      )
        throw new Error("The saved case receipt did not match this case.");
      const refreshedCase = await operations.readCase({
        registrationId: pending.context.registrationId,
        datasetId: pending.context.datasetId,
        caseId: pending.caseId,
      });
      if (!isCommittedRefreshCurrent(pending)) return false;
      const refreshedDataset = await datasetOperations.read({
        registrationId: pending.context.registrationId,
        datasetId: pending.context.datasetId,
      });
      if (!isCommittedRefreshCurrent(pending)) return false;
      const refreshedLabel = pending.decisionId
        ? await operations.readLabel({
            registrationId: pending.context.registrationId,
            decisionId: pending.decisionId,
            datasetId: pending.context.datasetId,
            caseId: pending.caseId,
          })
        : undefined;
      if (!isCommittedRefreshCurrent(pending)) return false;
      const page = await operations.listCases({
        registrationId: pending.context.registrationId,
        datasetId: pending.context.datasetId,
        query: { limit: "50" },
      });
      if (!isCommittedRefreshCurrent(pending)) return false;
      if (
        refreshedCase.data.case.record.id !== pending.caseId ||
        refreshedCase.data.case.record.dataset_id !==
          pending.context.datasetId ||
        refreshedDataset.data.record.id !== pending.context.datasetId ||
        (refreshedLabel &&
          (refreshedLabel.data.review.case_id !== pending.caseId ||
            refreshedLabel.data.review.dataset_id !==
              pending.context.datasetId ||
            refreshedLabel.data.review.decision_id !== pending.decisionId))
      )
        throw new Error("The refreshed case belongs to a different review.");

      const currentCaseChanged =
        receiptCase.etag !== refreshedCase.data.case.etag ||
        pending.receipt.dataset.etag !== refreshedDataset.data.etag;
      setCaseRead(refreshedCase.data);
      setDataset(refreshedDataset.data);
      if (refreshedLabel) setLabelView(refreshedLabel.data);
      setCases(page.data);
      setCaseCursor(page.data.next_cursor ?? undefined);
      if (currentCaseChanged) {
        setPendingCase({
          body: pending.body,
          uncertain: false,
          conflict: true,
        });
        setCaseConflictReviewed(false);
        setEditCase(true);
        setNotice(
          "Case saved. Newer case or dataset changes were found; review before reapplying.",
        );
      } else if (caseEditGeneration.current === pending.stagedGeneration) {
        setInputKind(refreshedCase.data.case.record.input_kind);
        setInputSource(refreshedCase.data.case.record.input_source);
        setMetadataSource(
          refreshedCase.data.case.record.metadata_source ?? "{}",
        );
        setEditorDirty(false);
        setEditCase(false);
        setPendingCase(undefined);
        setNotice(undefined);
      }
      clearCommittedRefresh(pending);
      setError(undefined);
      return true;
    } catch (cause) {
      if (isCommittedRefreshCurrent(pending)) setError(safeMessage(cause));
      return false;
    }
  }
  async function refreshCommittedOutcome() {
    const pending = committedRefreshRef.current;
    if (!pending || busy) return;
    setBusy(true);
    setError(undefined);
    await refreshCommittedView(pending);
    setBusy(false);
  }

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
    async function loadExamples() {
      const casePage = await operations.listCases({
        registrationId,
        datasetId,
        query: { limit: "50" },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const datasetResult = await datasetOperations.read({
        registrationId,
        datasetId,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const labelPage = decision
        ? await operations.listLabels({
            registrationId,
            decisionId: decision.id,
            datasetId,
            query: { limit: "50" },
            signal: controller.signal,
          })
        : undefined;
      if (controller.signal.aborted) return;
      setCases(casePage.data);
      setCaseCursor(casePage.data.next_cursor ?? undefined);
      setDataset(datasetResult.data);
      if (labelPage) {
        setLabels(labelPage.data);
        setLabelCursor(labelPage.data.next_cursor ?? undefined);
      }
    }
    void loadExamples()
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
    const requestedDatasetId = datasetId;
    const requestedCaseId = selectedCaseId;
    const requestedDecision = decision;
    const controller = new AbortController();
    setError(undefined);
    async function loadSelectedCase() {
      const caseResult = await operations.readCase({
        registrationId,
        datasetId: requestedDatasetId,
        caseId: requestedCaseId,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const labelResult = requestedDecision
        ? await operations.readLabel({
            registrationId,
            decisionId: requestedDecision.id,
            datasetId: requestedDatasetId,
            caseId: requestedCaseId,
            signal: controller.signal,
          })
        : undefined;
      if (controller.signal.aborted) return;
      setCaseRead(caseResult.data);
      setInputKind(caseResult.data.case.record.input_kind);
      setInputSource(caseResult.data.case.record.input_source);
      setMetadataSource(caseResult.data.case.record.metadata_source ?? "{}");
      setLabelView(labelResult?.data);
      setStagedAnswers(labelResult?.data.label?.acceptable_option_ids ?? []);
      setEditorDirty(false);
    }
    void loadSelectedCase().catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(safeMessage(cause));
    });
    return () => controller.abort();
  }, [decision, datasetId, operations, registrationId, selectedCaseId]);

  async function loadMoreCases() {
    if (!datasetId || !caseCursor || busy) return;
    const context = currentReadContext.current;
    setBusy(true);
    try {
      const result = await operations.listCases({
        registrationId,
        datasetId,
        query: { cursor: caseCursor, limit: "50" },
      });
      if (!isCurrentContext(context)) return;
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
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      if (isCurrentContext(context)) setBusy(false);
    }
  }

  async function loadMoreLabels() {
    if (!datasetId || !decision || !labelCursor || busy) return;
    const context = currentReadContext.current;
    setBusy(true);
    try {
      const result = await operations.listLabels({
        registrationId,
        decisionId: decision.id,
        datasetId,
        query: { cursor: labelCursor, limit: "50" },
      });
      if (!isCurrentContext(context)) return;
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
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      if (isCurrentContext(context)) setBusy(false);
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
      committedRefreshRef.current ||
      !decision ||
      !datasetId ||
      !labelView ||
      !selectedCaseId ||
      (stagedAnswers.length === 0 && action !== "clear" && action !== "dispute")
    )
      return false;
    if (pendingLabel?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const context = { ...currentReadContext.current };
    const decisionId = decision.id;
    const caseId = selectedCaseId;
    const stagedGeneration = labelEditGeneration.current;
    const stagedAnswersAtSubmit = [...stagedAnswers];
    const noteAtSubmit = note;
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
                ? { acceptable_option_ids: stagedAnswersAtSubmit }
                : {}),
              ...(action === "set" || action === "resolve"
                ? { provenance: "human" as const }
                : {}),
              ...(noteAtSubmit ? { note: noteAtSubmit } : {}),
            },
          ],
        };
    let receipt: LabelMutationReceipt;
    try {
      receipt = (
        await operations.saveLabels({
          registrationId: context.registrationId,
          decisionId,
          datasetId: context.datasetId,
          body,
        })
      ).data;
    } catch (cause) {
      if (isOutcomeUnknown(cause))
        setPendingLabel({ body, uncertain: true, conflict: false });
      else if (cause instanceof ApiError && cause.status === 409)
        setPendingLabel({ body, uncertain: false, conflict: true });
      else setPendingLabel(undefined);
      setError(safeMessage(cause));
      setBusy(false);
      setMutationInFlight(false);
      return false;
    }

    const pending: CommittedRefresh = {
      kind: "label",
      context,
      decisionId,
      caseId,
      receipt,
      body,
      stagedGeneration,
      stagedAnswers: stagedAnswersAtSubmit,
      note: noteAtSubmit,
    };
    committedRefreshRef.current = pending;
    setCommittedRefresh(pending);
    setPendingLabel(undefined);
    setNotice(undefined);
    setMutationInFlight(false);
    await refreshCommittedView(pending);
    setBusy(false);
    return true;
  }

  async function reviewLabelConflict(): Promise<void> {
    if (!decision || !datasetId || !selectedCaseId) return;
    const context = currentReadContext.current;
    setBusy(true);
    setError(undefined);
    try {
      const refreshed = await operations.readLabel({
        registrationId,
        decisionId: decision.id,
        datasetId,
        caseId: selectedCaseId,
      });
      if (!isCurrentContext(context)) return;
      // Keep the user's staged answer intact. A new deliberate save will use
      // this reviewed server context and a fresh operation ID.
      setLabelView(refreshed.data);
      setPendingLabel(undefined);
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      if (isCurrentContext(context)) setBusy(false);
    }
  }

  function retryUnknownLabel() {
    const action = pendingLabel?.body.edits[0]?.action;
    if (pendingLabel?.uncertain && action) void saveLabel(action);
  }

  async function saveCase(): Promise<boolean> {
    if (committedRefreshRef.current || !dataset || !caseRead || !selectedCaseId)
      return false;
    if (pendingCase?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const context = { ...currentReadContext.current };
    const caseId = selectedCaseId;
    const decisionId = decision?.id;
    const stagedGeneration = caseEditGeneration.current;
    const inputKindAtSubmit = inputKind;
    const inputSourceAtSubmit = inputSource;
    const metadataSourceAtSubmit = metadataSource;
    const record = caseRead.case.record;
    const body: CaseEditBody = pendingCase?.uncertain
      ? pendingCase.body
      : {
          schema_version: 1,
          operation_id: opId(),
          expected_case_etag: caseRead.case.etag,
          expected_dataset_etag: dataset.etag,
          input_kind: inputKindAtSubmit,
          input_source: inputSourceAtSubmit,
          tags: record.tags ?? [],
          split: record.split ?? "development",
          group_id: record.group_id ?? null,
          derived_from: record.derived_from ?? [],
          metadata_source: metadataSourceAtSubmit,
        };
    let receipt: CaseMutationReceipt;
    try {
      receipt = (
        await operations.editCase({
          registrationId: context.registrationId,
          datasetId: context.datasetId,
          caseId,
          body,
        })
      ).data;
    } catch (cause) {
      if (isOutcomeUnknown(cause))
        setPendingCase({ body, uncertain: true, conflict: false });
      else if (cause instanceof ApiError && cause.status === 409) {
        setPendingCase({ body, uncertain: false, conflict: true });
        setCaseConflictReviewed(false);
      } else setPendingCase(undefined);
      setError(safeMessage(cause));
      setBusy(false);
      setMutationInFlight(false);
      return false;
    }

    const pending: CommittedRefresh = {
      kind: "case",
      context,
      caseId,
      decisionId,
      receipt,
      body,
      stagedGeneration,
      inputKind: inputKindAtSubmit,
      inputSource: inputSourceAtSubmit,
      metadataSource: metadataSourceAtSubmit,
    };
    committedRefreshRef.current = pending;
    setCommittedRefresh(pending);
    setPendingCase(undefined);
    setNotice(undefined);
    setMutationInFlight(false);
    await refreshCommittedView(pending);
    setBusy(false);
    return true;
  }

  async function reviewCaseConflict() {
    if (!dataset || !caseRead || !selectedCaseId) return;
    const context = currentReadContext.current;
    setBusy(true);
    setError(undefined);
    try {
      const currentCase = await operations.readCase({
        registrationId,
        datasetId,
        caseId: selectedCaseId,
      });
      if (!isCurrentContext(context)) return;
      const currentDataset = await datasetOperations.read({
        registrationId,
        datasetId,
      });
      if (!isCurrentContext(context)) return;
      setCaseRead(currentCase.data);
      setDataset(currentDataset.data);
      setPendingCase(undefined);
      setCaseConflictReviewed(true);
      setNotice(
        "Current case and dataset versions reviewed. Your edited source is retained; reapply it deliberately.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      if (isCurrentContext(context)) setBusy(false);
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
    const context = currentReadContext.current;
    setBusy(true);
    setError(undefined);
    try {
      const currentDataset = await datasetOperations.read({
        registrationId,
        datasetId,
      });
      if (!isCurrentContext(context)) return;
      const currentCases = await operations.listCases({
        registrationId,
        datasetId,
        query: { limit: "50" },
      });
      if (!isCurrentContext(context)) return;
      setDataset(currentDataset.data);
      setCases(currentCases.data);
      setCaseCursor(currentCases.data.next_cursor ?? undefined);
      setPendingAdd(undefined);
      setAddConflictReviewed(true);
      setNotice(
        "Current dataset and cases reviewed. Your new example source is retained; reapply it deliberately.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      if (isCurrentContext(context)) setBusy(false);
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
    const context = currentReadContext.current;
    setBusy(true);
    setError(undefined);
    try {
      const currentCase = await operations.readCase({
        registrationId,
        datasetId,
        caseId: selectedCaseId,
      });
      if (!isCurrentContext(context)) return;
      const currentDataset = await datasetOperations.read({
        registrationId,
        datasetId,
      });
      if (!isCurrentContext(context)) return;
      setCaseRead(currentCase.data);
      setDataset(currentDataset.data);
      setPendingRemove(undefined);
      setRemoveConflictReviewed(true);
      setNotice(
        "Current case and dataset versions reviewed. Reapply removal deliberately if the case is still present.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      if (isCurrentContext(context)) setBusy(false);
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
    if (committedRefreshRef.current) {
      const kind = committedRefreshRef.current.kind;
      throw new Error(
        kind === "label"
          ? "The label was saved. Refresh its current review before leaving or starting another change."
          : "The case was saved. Refresh its current review before leaving or starting another change.",
      );
    }
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
    if (committedRefreshRef.current) {
      throw new Error(
        "The case was saved. Refresh its current review before saving another change or leaving.",
      );
    }
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
      if (committedRefreshRef.current) {
        throw new Error(
          "The label was saved. Refresh its current review before leaving.",
        );
      }
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
  const navigationBlockedMessage = committedRefresh
    ? committedRefresh.kind === "label"
      ? "The label was saved. Refresh its current review before leaving this examples page."
      : "The case was saved. Refresh its current review before leaving this examples page."
    : uncertainWrite
      ? "A write may have completed. Keep editing and retry its original request before leaving this examples page."
      : mutationInFlight
        ? "An examples write is still in progress. Keep this page open until it finishes."
        : undefined;
  const dirtyGuard = useDirtyNavigationGuard({
    dirty:
      editorDirty ||
      labelSetChanged ||
      (decision !== undefined && note.trim().length > 0) ||
      committedRefresh !== undefined ||
      uncertainWrite ||
      unresolvedConflict ||
      mutationInFlight,
    isDirtyNow: () =>
      committedRefreshRef.current !== undefined ||
      editorDirty ||
      labelSetChanged ||
      (decision !== undefined && note.trim().length > 0) ||
      uncertainWrite ||
      unresolvedConflict ||
      mutationInFlight,
    blockedMessage: navigationBlockedMessage,
    allowDiscardWhenBlocked: committedRefresh !== undefined,
    save: saveBeforeLeaving,
    discard: () => {
      committedRefreshRef.current = undefined;
      setCommittedRefresh(undefined);
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
        {committedRefresh?.kind === "label" && (
          <section
            className="warning-summary"
            aria-label="Saved changes awaiting refresh"
          >
            <p role="status">
              Label saved; refresh its current review before another change.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void refreshCommittedOutcome()}
            >
              {busy ? "Refreshing saved review…" : "Refresh saved label"}
            </button>
          </section>
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
        ) : !cases && error ? (
          <EmptyState
            title="Examples could not be loaded"
            action={
              <button
                type="button"
                onClick={() => setRefreshGeneration((value) => value + 1)}
              >
                Reload examples
              </button>
            }
          >
            The request failed. Reload to try again.
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
              <button
                type="button"
                disabled={busy || !!committedRefresh}
                onClick={() => setEditCase(true)}
              >
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
                    labelEditGeneration.current += 1;
                    setStagedAnswers(answers);
                    setEditorDirty(true);
                  }}
                  onSave={() =>
                    void saveLabel(
                      currentLabel?.status === "disputed" ? "resolve" : "set",
                    )
                  }
                  saving={busy || !!committedRefresh || pendingLabel?.uncertain}
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
                    disabled={
                      busy || !!committedRefresh || pendingLabel?.uncertain
                    }
                    onClick={() => void saveLabel("resolve")}
                  >
                    Resolve dispute with staged set
                  </button>
                )}
                {currentLabel && currentLabel.status !== "disputed" && (
                  <button
                    disabled={
                      busy || !!committedRefresh || pendingLabel?.uncertain
                    }
                    onClick={() => void saveLabel("dispute")}
                  >
                    Dispute label
                  </button>
                )}
                {currentLabel && (
                  <button
                    disabled={
                      busy || !!committedRefresh || pendingLabel?.uncertain
                    }
                    onClick={() => void saveLabel("clear")}
                  >
                    Clear label
                  </button>
                )}
                <label htmlFor="label-note">Provenance note</label>
                <input
                  id="label-note"
                  value={note}
                  disabled={
                    busy || !!committedRefresh || pendingLabel?.uncertain
                  }
                  onChange={(event) => {
                    labelEditGeneration.current += 1;
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
              if (!busy && !committedRefresh && !pendingCase?.uncertain)
                setEditCase(false);
            }}
          >
            <div className="modal-body case-editor">
              {committedRefresh?.kind === "case" && (
                <div
                  className="warning-summary"
                  aria-label="Saved changes awaiting refresh"
                >
                  <p role="status">
                    Case saved; refresh its current review before another
                    change.
                  </p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void refreshCommittedOutcome()}
                  >
                    {busy ? "Refreshing saved review…" : "Refresh saved case"}
                  </button>
                </div>
              )}
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
                      disabled={
                        busy || !!committedRefresh || pendingCase?.uncertain
                      }
                      onChange={() => {
                        caseEditGeneration.current += 1;
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
                readOnly={busy || !!committedRefresh || pendingCase?.uncertain}
                onChange={(value) => {
                  caseEditGeneration.current += 1;
                  setInputSource(value);
                  setEditorDirty(true);
                }}
              />
              <JsonSourceEditor
                label="Metadata source"
                value={metadataSource}
                readOnly={busy || !!committedRefresh || pendingCase?.uncertain}
                onChange={(value) => {
                  caseEditGeneration.current += 1;
                  setMetadataSource(value);
                  setEditorDirty(true);
                }}
              />
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={
                    busy || !!committedRefresh || !!pendingCase?.conflict
                  }
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
                  disabled={
                    busy || !!committedRefresh || pendingCase?.uncertain
                  }
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
