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
import {
  liveDatasetRouteMatches,
  liveSelectionRouteMatches,
  matchesDatasetScope,
  matchesSelectionScope,
  sameCaseSource,
  sameLabelRecord,
  sameLabelReview,
  selectionPairMatches,
} from "./examples-admission";
import type {
  CasePage,
  CaseRead,
  DatasetAdmission,
  DatasetRead,
  DatasetScope,
  LabelPage,
  LabelView,
  ReadContext,
  SelectionAdmission,
  SelectionScope,
} from "./examples-admission";

type CaseStageSnapshot = {
  owner: SelectionAdmission;
  generation: number;
  inputKind: "text" | "json";
  inputSource: string;
  metadataSource: string;
};
type LabelStageSnapshot = {
  owner: SelectionAdmission;
  generation: number;
  answers: readonly string[];
  note: string;
};
type DatasetStageSnapshot = {
  owner: DatasetAdmission;
  generation: number;
  inputKind: "text" | "json";
  inputSource: string;
  metadataSource: string;
};
type CaseWriteSnapshot = {
  admission: SelectionAdmission;
  stage: CaseStageSnapshot;
};
type LabelWriteSnapshot = {
  admission: SelectionAdmission;
  stage: LabelStageSnapshot;
  action: "set" | "resolve" | "dispute" | "clear";
};
type DatasetWriteSnapshot = {
  admission: DatasetAdmission;
  stage: DatasetStageSnapshot;
};

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
type PendingLabelMutation = {
  body: LabelMutationBody;
  scope: SelectionScope;
  uncertain: boolean;
  conflict: boolean;
};
type PendingCaseMutation = {
  body: CaseEditBody;
  scope: SelectionScope;
  uncertain: boolean;
  conflict: boolean;
};
type PendingAddMutation = {
  body: AddCaseBody;
  scope: DatasetScope;
  uncertain: boolean;
  conflict: boolean;
};
type PendingRemoveMutation = {
  body: RemoveCaseBody;
  scope: SelectionScope;
  uncertain: boolean;
  conflict: boolean;
};

type CommittedRefresh =
  | {
      kind: "label";
      context: ReadContext;
      decisionId: string;
      caseId: string;
      readEpoch: number;
      navigationEpoch: number;
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
      readEpoch: number;
      navigationEpoch: number;
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
  const [labelsLoading, setLabelsLoading] = useState(Boolean(decision?.id));
  const [labelsError, setLabelsError] = useState<string>();
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
  const [selectionReloadGeneration, setSelectionReloadGeneration] = useState(0);
  const [navigationEpoch, setNavigationEpoch] = useState(0);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [editorDirty, setEditorDirty] = useState(false);
  const editorDirtyRef = useRef(false);
  const noteRef = useRef("");
  const [selectionNeedsReview, setSelectionNeedsReview] = useState(false);
  const [pendingLabel, setPendingLabel] = useState<PendingLabelMutation>();
  const [pendingCase, setPendingCase] = useState<PendingCaseMutation>();
  const [pendingAdd, setPendingAdd] = useState<PendingAddMutation>();
  const [pendingRemove, setPendingRemove] = useState<PendingRemoveMutation>();
  const [committedRefresh, setCommittedRefresh] = useState<CommittedRefresh>();
  const committedRefreshRef = useRef<CommittedRefresh | undefined>(undefined);
  // The ref fences duplicate event callbacks before React publishes busy state.
  const mutationLockRef = useRef(false);
  const busyRef = useRef(false);
  const selectionReloadActionRef = useRef<symbol | undefined>(undefined);
  const selectionReloadOwnerRef = useRef<symbol | undefined>(undefined);
  const selectionNeedsReviewRef = useRef(false);
  const pendingLabelUncertainRef = useRef(false);
  const pendingCaseUncertainRef = useRef(false);
  const pendingLabelRef = useRef<PendingLabelMutation | undefined>(undefined);
  const pendingCaseRef = useRef<PendingCaseMutation | undefined>(undefined);
  const pendingAddRef = useRef<PendingAddMutation | undefined>(undefined);
  const pendingRemoveRef = useRef<PendingRemoveMutation | undefined>(undefined);
  const caseStageRef = useRef<CaseStageSnapshot | undefined>(undefined);
  const labelStageRef = useRef<LabelStageSnapshot | undefined>(undefined);
  const datasetStageRef = useRef<DatasetStageSnapshot | undefined>(undefined);
  const datasetEditGeneration = useRef(0);
  const datasetAdmissionRef = useRef<DatasetAdmission | undefined>(undefined);
  const selectionAdmissionRef = useRef<SelectionAdmission | undefined>(
    undefined,
  );
  const previousSelectionAdmissionRef = useRef<SelectionAdmission | undefined>(
    undefined,
  );
  const datasetReadEpochRef = useRef(0);
  const labelListReadEpochRef = useRef<number | undefined>(undefined);
  const selectionReadEpochRef = useRef(0);
  const navigationEpochRef = useRef(0);
  const caseEditGeneration = useRef(0);
  const labelEditGeneration = useRef(0);
  function updateBusy(nextBusy: boolean) {
    busyRef.current = nextBusy;
    setBusy(nextBusy);
  }
  function updateEditorDirty(nextDirty: boolean) {
    editorDirtyRef.current = nextDirty;
    setEditorDirty(nextDirty);
  }
  function updateNote(nextNote: string) {
    noteRef.current = nextNote;
    setNote(nextNote);
  }
  function canStartBusyAction(): boolean {
    return !busyRef.current && !mutationLockRef.current;
  }
  function beginBusyAction(): boolean {
    if (!canStartBusyAction()) return false;
    updateBusy(true);
    return true;
  }
  function finishSelectionReload(token: symbol | undefined) {
    if (!token || selectionReloadOwnerRef.current !== token) return;
    selectionReloadOwnerRef.current = undefined;
    updateBusy(false);
  }
  function updateSelectionNeedsReview(needsReview: boolean) {
    selectionNeedsReviewRef.current = needsReview;
    setSelectionNeedsReview(needsReview);
  }
  function updatePendingLabel(next: PendingLabelMutation | undefined) {
    pendingLabelUncertainRef.current = next?.uncertain ?? false;
    pendingLabelRef.current = next;
    setPendingLabel(next);
  }
  function updatePendingCase(next: PendingCaseMutation | undefined) {
    pendingCaseUncertainRef.current = next?.uncertain ?? false;
    pendingCaseRef.current = next;
    setPendingCase(next);
  }
  function updatePendingAdd(next: PendingAddMutation | undefined) {
    pendingAddRef.current = next;
    setPendingAdd(next);
  }
  function updatePendingRemove(next: PendingRemoveMutation | undefined) {
    pendingRemoveRef.current = next;
    setPendingRemove(next);
  }
  function acquireMutationLock(): boolean {
    if (!canStartBusyAction()) return false;
    mutationLockRef.current = true;
    return true;
  }
  function releaseMutationLock() {
    mutationLockRef.current = false;
  }
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
  function liveRouteMatchesDataset(context: {
    registrationId: string;
    datasetId: string;
  }): boolean {
    return liveDatasetRouteMatches(
      navigation.current,
      context,
      datasetFromRoute,
    );
  }
  function liveRouteMatchesSelection(context: {
    registrationId: string;
    datasetId: string;
    decisionId?: string;
    caseId?: string;
  }): boolean {
    const caseId = context.caseId;
    if (!caseId) return false;
    return liveSelectionRouteMatches(
      navigation.current,
      { ...context, caseId },
      { datasetId: datasetFromRoute, caseId: caseFromRoute },
    );
  }
  function currentDatasetAdmission(): DatasetAdmission | undefined {
    const admission = datasetAdmissionRef.current;
    const context = currentReadContext.current;
    if (
      !admission ||
      admission.registrationId !== context.registrationId ||
      admission.datasetId !== context.datasetId ||
      admission.refreshGeneration !== context.refreshGeneration ||
      admission.refreshToken !== context.refreshToken ||
      !liveRouteMatchesDataset(admission)
    )
      return undefined;
    return admission;
  }
  function markLabelListUnavailable(message: string) {
    labelListReadEpochRef.current = undefined;
    setLabels(undefined);
    setLabelCursor(undefined);
    setLabelsLoading(false);
    setLabelsError(message);
  }
  function revokePendingLabelList(epoch: number, message: string) {
    if (labelListReadEpochRef.current !== epoch) return;
    markLabelListUnavailable(message);
  }
  const datasetScopeReady = currentDatasetAdmission() !== undefined;
  function currentSelectionAdmission(): SelectionAdmission | undefined {
    const admission = selectionAdmissionRef.current;
    const context = currentReadContext.current;
    const currentDataset = currentDatasetAdmission();
    if (
      !admission ||
      !currentDataset ||
      admission.datasetAdmission !== currentDataset ||
      admission.registrationId !== context.registrationId ||
      admission.datasetId !== context.datasetId ||
      admission.decisionId !== context.decisionId ||
      admission.caseId !== context.selectedCaseId ||
      admission.navigationEpoch !== navigationEpochRef.current ||
      admission.navigationEpoch !== navigationEpoch ||
      !liveRouteMatchesSelection({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        decisionId: admission.decisionId,
        caseId: admission.caseId,
      })
    )
      return undefined;
    return admission;
  }
  function captureDatasetAdmission(): DatasetAdmission | undefined {
    return currentDatasetAdmission();
  }
  function captureSelectionAdmission(): SelectionAdmission | undefined {
    return currentSelectionAdmission();
  }
  function captureRenderedDataset(
    rendered: DatasetAdmission | undefined,
  ): DatasetAdmission | undefined {
    return rendered && rendered === currentDatasetAdmission()
      ? rendered
      : undefined;
  }
  function captureRenderedSelection(
    rendered: SelectionAdmission | undefined,
  ): SelectionAdmission | undefined {
    return rendered && rendered === currentSelectionAdmission()
      ? rendered
      : undefined;
  }
  function ownsSelectionStage(
    stage: CaseStageSnapshot | LabelStageSnapshot | undefined,
    admission: SelectionAdmission,
  ): boolean {
    return stage?.owner === admission;
  }
  function mayEditCaseStageNow(
    rendered: SelectionAdmission | undefined,
  ): rendered is SelectionAdmission {
    const admission = captureRenderedSelection(rendered);
    const stage = caseStageRef.current;
    return (
      !!admission &&
      ownsSelectionStage(stage, admission) &&
      !selectionNeedsReviewRef.current &&
      !pendingCaseUncertainRef.current &&
      !pendingLabelUncertainRef.current &&
      !pendingAddRef.current?.uncertain &&
      !pendingRemoveRef.current?.uncertain &&
      !committedRefreshRef.current &&
      !busyRef.current &&
      !mutationLockRef.current
    );
  }
  function mayEditLabelStageNow(
    rendered: SelectionAdmission | undefined,
  ): rendered is SelectionAdmission {
    const admission = captureRenderedSelection(rendered);
    const stage = labelStageRef.current;
    return (
      !!admission?.labelView &&
      ownsSelectionStage(stage, admission) &&
      !selectionNeedsReviewRef.current &&
      !pendingLabelUncertainRef.current &&
      !pendingCaseUncertainRef.current &&
      !pendingAddRef.current?.uncertain &&
      !pendingRemoveRef.current?.uncertain &&
      !committedRefreshRef.current &&
      !busyRef.current &&
      !mutationLockRef.current
    );
  }
  function mayEditDatasetStageNow(
    rendered: DatasetAdmission | undefined,
  ): rendered is DatasetAdmission {
    return (
      !!captureRenderedDataset(rendered) &&
      !pendingLabelUncertainRef.current &&
      !pendingCaseUncertainRef.current &&
      !pendingAddRef.current?.uncertain &&
      !pendingRemoveRef.current?.uncertain &&
      !committedRefreshRef.current &&
      !busyRef.current &&
      !mutationLockRef.current
    );
  }
  function captureInteractiveCase(
    rendered: SelectionAdmission | undefined,
  ): CaseWriteSnapshot | undefined {
    const admission = captureRenderedSelection(rendered);
    const stage = caseStageRef.current;
    if (
      !admission ||
      !stage ||
      stage.owner !== admission ||
      selectionNeedsReviewRef.current ||
      pendingCaseRef.current?.conflict ||
      (pendingCaseRef.current?.uncertain &&
        !matchesSelectionScope(pendingCaseRef.current.scope, admission)) ||
      (pendingCaseUncertainRef.current && !pendingCaseRef.current?.uncertain) ||
      pendingLabelUncertainRef.current ||
      pendingAddRef.current?.uncertain ||
      pendingRemoveRef.current?.uncertain ||
      committedRefreshRef.current ||
      busyRef.current ||
      mutationLockRef.current
    )
      return undefined;
    return { admission, stage: { ...stage } };
  }
  function captureInteractiveLabel(
    rendered: SelectionAdmission | undefined,
    action: LabelWriteSnapshot["action"],
  ): LabelWriteSnapshot | undefined {
    const admission = captureRenderedSelection(rendered);
    const stage = labelStageRef.current;
    const pending = pendingLabelRef.current;
    if (
      !admission?.labelView ||
      !stage ||
      stage.owner !== admission ||
      selectionNeedsReviewRef.current ||
      pending?.conflict ||
      (pending?.uncertain &&
        !matchesSelectionScope(pending.scope, admission)) ||
      pendingCaseUncertainRef.current ||
      (pendingLabelUncertainRef.current &&
        !pendingLabelRef.current?.uncertain) ||
      pendingAddRef.current?.uncertain ||
      pendingRemoveRef.current?.uncertain ||
      committedRefreshRef.current ||
      busyRef.current ||
      mutationLockRef.current ||
      (!pending?.uncertain &&
        stage.answers.length === 0 &&
        action !== "clear" &&
        action !== "dispute")
    )
      return undefined;
    return {
      admission,
      stage: { ...stage, answers: [...stage.answers] },
      action,
    };
  }
  function captureInteractiveDataset(
    rendered: DatasetAdmission | undefined,
  ): DatasetWriteSnapshot | undefined {
    const admission = captureRenderedDataset(rendered);
    const stage = datasetStageRef.current;
    if (
      !admission ||
      !stage ||
      stage.owner !== admission ||
      pendingLabelUncertainRef.current ||
      pendingCaseUncertainRef.current ||
      (pendingAddRef.current?.uncertain &&
        !matchesDatasetScope(pendingAddRef.current.scope, admission)) ||
      pendingRemoveRef.current?.uncertain ||
      committedRefreshRef.current ||
      busyRef.current ||
      mutationLockRef.current
    )
      return undefined;
    return { admission, stage: { ...stage } };
  }
  function captureGuardDataset(
    expected: DatasetScope,
  ): DatasetWriteSnapshot | undefined {
    const admission = currentDatasetAdmission();
    const stage = datasetStageRef.current;
    if (
      !admission ||
      !matchesDatasetScope(expected, admission) ||
      !stage ||
      stage.owner !== admission ||
      !liveRouteMatchesDataset(admission) ||
      committedRefreshRef.current ||
      pendingAddRef.current?.uncertain ||
      pendingAddRef.current?.conflict ||
      pendingRemoveRef.current?.uncertain ||
      mutationLockRef.current
    )
      return undefined;
    return { admission, stage: { ...stage } };
  }
  function captureGuardCase(
    expected: SelectionScope,
  ): CaseWriteSnapshot | undefined {
    const admission = currentSelectionAdmission();
    const stage = caseStageRef.current;
    if (
      !admission ||
      !matchesSelectionScope(expected, admission) ||
      !stage ||
      stage.owner !== admission ||
      !liveRouteMatchesSelection(admission) ||
      selectionNeedsReviewRef.current ||
      committedRefreshRef.current ||
      pendingCaseRef.current?.uncertain ||
      pendingCaseRef.current?.conflict ||
      pendingLabelRef.current?.uncertain ||
      pendingLabelRef.current?.conflict ||
      pendingAddRef.current?.uncertain ||
      pendingRemoveRef.current?.uncertain ||
      busyRef.current ||
      mutationLockRef.current
    )
      return undefined;
    return { admission, stage: { ...stage } };
  }
  function captureGuardLabel(
    expected: SelectionScope,
    action: LabelWriteSnapshot["action"],
  ): LabelWriteSnapshot | undefined {
    const admission = currentSelectionAdmission();
    const stage = labelStageRef.current;
    if (
      !admission?.labelView ||
      !matchesSelectionScope(expected, admission) ||
      !stage ||
      stage.owner !== admission ||
      !liveRouteMatchesSelection(admission) ||
      selectionNeedsReviewRef.current ||
      committedRefreshRef.current ||
      pendingLabelRef.current?.uncertain ||
      pendingLabelRef.current?.conflict ||
      pendingCaseRef.current?.uncertain ||
      pendingCaseRef.current?.conflict ||
      pendingAddRef.current?.uncertain ||
      pendingRemoveRef.current?.uncertain ||
      (stage.answers.length === 0 &&
        action !== "clear" &&
        action !== "dispute") ||
      busyRef.current ||
      mutationLockRef.current
    )
      return undefined;
    return {
      admission,
      stage: { ...stage, answers: [...stage.answers] },
      action,
    };
  }
  function patchCaseStage(
    rendered: SelectionAdmission | undefined,
    patch: Partial<
      Pick<CaseStageSnapshot, "inputKind" | "inputSource" | "metadataSource">
    >,
  ): boolean {
    if (!mayEditCaseStageNow(rendered)) return false;
    const current = caseStageRef.current;
    if (!current || current.owner !== rendered) return false;
    const next: CaseStageSnapshot = {
      ...current,
      ...patch,
      generation: ++caseEditGeneration.current,
    };
    caseStageRef.current = next;
    if (patch.inputKind !== undefined) setInputKind(next.inputKind);
    if (patch.inputSource !== undefined) setInputSource(next.inputSource);
    if (patch.metadataSource !== undefined)
      setMetadataSource(next.metadataSource);
    updateEditorDirty(true);
    return true;
  }
  function patchLabelAnswers(
    rendered: SelectionAdmission | undefined,
    answers: readonly string[],
  ): boolean {
    if (!mayEditLabelStageNow(rendered)) return false;
    const current = labelStageRef.current;
    if (!current || current.owner !== rendered) return false;
    const next: LabelStageSnapshot = {
      ...current,
      answers: [...answers],
      generation: ++labelEditGeneration.current,
    };
    labelStageRef.current = next;
    setStagedAnswers(next.answers);
    updateEditorDirty(true);
    return true;
  }
  function toggleLabelAnswer(
    rendered: SelectionAdmission | undefined,
    optionId: string,
    checked: boolean,
  ): boolean {
    if (!mayEditLabelStageNow(rendered)) return false;
    const current = labelStageRef.current;
    if (!current || current.owner !== rendered) return false;
    const answers = checked
      ? current.answers.includes(optionId)
        ? current.answers
        : [...current.answers, optionId]
      : current.answers.filter((id) => id !== optionId);
    return patchLabelAnswers(rendered, answers);
  }
  function patchLabelNote(
    rendered: SelectionAdmission | undefined,
    value: string,
  ): boolean {
    if (!mayEditLabelStageNow(rendered)) return false;
    const current = labelStageRef.current;
    if (!current || current.owner !== rendered) return false;
    const next: LabelStageSnapshot = {
      ...current,
      note: value,
      generation: ++labelEditGeneration.current,
    };
    labelStageRef.current = next;
    updateNote(value);
    updateEditorDirty(true);
    return true;
  }
  function patchDatasetStage(
    rendered: DatasetAdmission | undefined,
    patch: Partial<
      Pick<DatasetStageSnapshot, "inputKind" | "inputSource" | "metadataSource">
    >,
  ): boolean {
    if (!mayEditDatasetStageNow(rendered)) return false;
    const current = datasetStageRef.current;
    if (!current || current.owner !== rendered) return false;
    const next: DatasetStageSnapshot = {
      ...current,
      ...patch,
      generation: ++datasetEditGeneration.current,
    };
    datasetStageRef.current = next;
    if (patch.inputKind !== undefined) setNewInputKind(next.inputKind);
    if (patch.inputSource !== undefined) setNewInputSource(next.inputSource);
    if (patch.metadataSource !== undefined)
      setNewMetadataSource(next.metadataSource);
    updateEditorDirty(true);
    return true;
  }
  function publishReviewedPair(
    context: ReadContext,
    datasetRead: DatasetRead,
    caseResult: CaseRead,
    labelResult: LabelView | undefined,
    expectedSelectionEpoch: number,
    expectedNavigationEpoch: number,
  ): SelectionAdmission | undefined {
    const caseId = context.selectedCaseId;
    if (
      !caseId ||
      !isCurrentContext(context) ||
      selectionReadEpochRef.current !== expectedSelectionEpoch ||
      navigationEpochRef.current !== expectedNavigationEpoch ||
      !liveRouteMatchesSelection({
        registrationId: context.registrationId,
        datasetId: context.datasetId,
        decisionId: context.decisionId,
        caseId,
      }) ||
      !selectionPairMatches({
        datasetId: context.datasetId,
        decisionId: context.decisionId,
        caseId,
        dataset: datasetRead,
        caseRead: caseResult,
        labelView: labelResult,
      })
    )
      return undefined;

    const supersededDatasetEpoch = datasetReadEpochRef.current;
    const priorDatasetAdmission = datasetAdmissionRef.current;
    const datasetAdmission: DatasetAdmission = Object.freeze({
      registrationId: context.registrationId,
      datasetId: context.datasetId,
      refreshGeneration: context.refreshGeneration,
      refreshToken: context.refreshToken,
      epoch: ++datasetReadEpochRef.current,
      read: datasetRead,
    });
    if (
      priorDatasetAdmission?.read.etag !== datasetRead.etag ||
      labelListReadEpochRef.current === supersededDatasetEpoch
    )
      markLabelListUnavailable(
        "The label list is out of date. Reload examples to refresh it.",
      );
    const admission: SelectionAdmission = Object.freeze({
      registrationId: context.registrationId,
      datasetId: context.datasetId,
      decisionId: context.decisionId,
      caseId,
      readEpoch: ++selectionReadEpochRef.current,
      navigationEpoch: navigationEpochRef.current,
      datasetAdmission,
      caseRead: caseResult,
      labelView: labelResult,
    });
    datasetAdmissionRef.current = datasetAdmission;
    selectionAdmissionRef.current = admission;
    const currentDatasetStage = datasetStageRef.current;
    if (currentDatasetStage?.owner.datasetId === context.datasetId)
      datasetStageRef.current = {
        ...currentDatasetStage,
        owner: datasetAdmission,
      };
    setDataset(datasetRead);
    setCaseRead(caseResult);
    setLabelView(labelResult);
    setLoading(false);
    return admission;
  }
  useEffect(
    () =>
      navigation.subscribe((route) => {
        navigationEpochRef.current += 1;
        selectionReadEpochRef.current += 1;
        previousSelectionAdmissionRef.current =
          selectionAdmissionRef.current ??
          previousSelectionAdmissionRef.current;
        selectionAdmissionRef.current = undefined;
        if (
          route.kind !== "examples" ||
          route.registrationId !== registrationId ||
          (route.datasetId !== undefined &&
            route.datasetId !== datasetAdmissionRef.current?.datasetId)
        )
          datasetAdmissionRef.current = undefined;
        setNavigationEpoch(navigationEpochRef.current);
      }),
    [navigation, registrationId],
  );
  function isCommittedRefreshCurrent(pending: CommittedRefresh) {
    return (
      committedRefreshRef.current === pending &&
      isCurrentContext(pending.context) &&
      currentSelectionAdmission()?.readEpoch === pending.readEpoch &&
      navigationEpochRef.current === pending.navigationEpoch &&
      liveRouteMatchesSelection({
        registrationId: pending.context.registrationId,
        datasetId: pending.context.datasetId,
        decisionId: pending.context.decisionId,
        caseId: pending.caseId,
      }) &&
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
        const receiptChange = pending.receipt.changes.find(
          (change) =>
            change.operation_id === pending.body.operation_id &&
            change.case_id === pending.caseId &&
            change.dataset_id === pending.context.datasetId &&
            change.decision_id === pending.decisionId,
        );
        if (!receiptChange)
          throw new Error("The saved label receipt did not match this review.");
        const refreshedDataset = await datasetOperations.read({
          registrationId: pending.context.registrationId,
          datasetId: pending.context.datasetId,
        });
        if (!isCommittedRefreshCurrent(pending)) return false;
        const refreshedCase = await operations.readCase({
          registrationId: pending.context.registrationId,
          datasetId: pending.context.datasetId,
          caseId: pending.caseId,
        });
        if (!isCommittedRefreshCurrent(pending)) return false;
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
          review.decision_id !== pending.decisionId ||
          refreshedCase.data.case.record.id !== pending.caseId ||
          refreshedCase.data.case.record.dataset_id !==
            pending.context.datasetId ||
          refreshedDataset.data.record.id !== pending.context.datasetId ||
          refreshedCase.data.dataset_etag !== refreshedDataset.data.etag ||
          !sameCaseSource(
            refreshedCase.data.case.record,
            refreshedLabel.data.case,
          )
        )
          throw new Error("The refreshed label belongs to a different review.");

        const reviewChanged =
          review.decision_etag !== submitted.review.decision_etag ||
          review.draft_etag !== submitted.review.draft_etag ||
          review.input_hash !== submitted.review.input_hash ||
          !sameLabelRecord(receiptChange.label, refreshedLabel.data.label);
        const refreshedAdmission = publishReviewedPair(
          pending.context,
          refreshedDataset.data,
          refreshedCase.data,
          refreshedLabel.data,
          pending.readEpoch,
          pending.navigationEpoch,
        );
        if (!refreshedAdmission)
          throw new Error("The refreshed label belongs to a different review.");
        setLabels(page.data);
        setLabelCursor(page.data.next_cursor ?? undefined);
        setLabelsLoading(false);
        setLabelsError(undefined);
        labelListReadEpochRef.current = undefined;
        if (reviewChanged) {
          updatePendingLabel({
            body: pending.body,
            scope: {
              registrationId: pending.context.registrationId,
              datasetId: pending.context.datasetId,
              decisionId: pending.decisionId,
              caseId: pending.caseId,
            },
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
          updateNote("");
          updateEditorDirty(false);
          updatePendingLabel(undefined);
          setNotice(undefined);
          const refreshedStage = labelStageRef.current;
          if (refreshedStage)
            labelStageRef.current = {
              ...refreshedStage,
              owner: refreshedAdmission,
              generation: labelEditGeneration.current,
              answers: refreshedLabel.data.label?.acceptable_option_ids ?? [],
              note: "",
            };
          else
            labelStageRef.current = {
              owner: refreshedAdmission,
              generation: labelEditGeneration.current,
              answers: refreshedLabel.data.label?.acceptable_option_ids ?? [],
              note: "",
            };
          updateSelectionNeedsReview(false);
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
        refreshedCase.data.dataset_etag !== refreshedDataset.data.etag ||
        (refreshedLabel &&
          (refreshedLabel.data.review.case_id !== pending.caseId ||
            refreshedLabel.data.review.dataset_id !==
              pending.context.datasetId ||
            refreshedLabel.data.review.decision_id !== pending.decisionId ||
            !sameCaseSource(
              refreshedCase.data.case.record,
              refreshedLabel.data.case,
            )))
      )
        throw new Error("The refreshed case belongs to a different review.");

      const priorAdmission = currentSelectionAdmission();
      const currentCaseChanged =
        receiptCase.etag !== refreshedCase.data.case.etag ||
        pending.receipt.dataset.etag !== refreshedDataset.data.etag;
      const refreshedAdmission = publishReviewedPair(
        pending.context,
        refreshedDataset.data,
        refreshedCase.data,
        refreshedLabel?.data,
        pending.readEpoch,
        pending.navigationEpoch,
      );
      if (!refreshedAdmission)
        throw new Error("The refreshed case belongs to a different review.");
      setCases(page.data);
      setCaseCursor(page.data.next_cursor ?? undefined);
      if (currentCaseChanged) {
        updatePendingCase({
          body: pending.body,
          scope: {
            registrationId: pending.context.registrationId,
            datasetId: pending.context.datasetId,
            decisionId: pending.decisionId,
            caseId: pending.caseId,
          },
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
        updateEditorDirty(false);
        setEditCase(false);
        updatePendingCase(undefined);
        setNotice(undefined);
        caseStageRef.current = {
          owner: refreshedAdmission,
          generation: caseEditGeneration.current,
          inputKind: refreshedCase.data.case.record.input_kind,
          inputSource: refreshedCase.data.case.record.input_source,
          metadataSource:
            refreshedCase.data.case.record.metadata_source ?? "{}",
        };
      }
      if (
        refreshedLabel &&
        priorAdmission?.labelView &&
        (priorAdmission.labelView.review.decision_etag !==
          refreshedLabel.data.review.decision_etag ||
          priorAdmission.labelView.review.draft_etag !==
            refreshedLabel.data.review.draft_etag ||
          priorAdmission.labelView.review.input_hash !==
            refreshedLabel.data.review.input_hash ||
          !sameLabelRecord(
            priorAdmission.labelView.label ?? null,
            refreshedLabel.data.label ?? null,
          ))
      ) {
        updateSelectionNeedsReview(true);
        setNotice(
          "Case saved. The current label review changed; review it before making another label change.",
        );
      } else {
        const labelStage = labelStageRef.current;
        if (labelStage)
          labelStageRef.current = { ...labelStage, owner: refreshedAdmission };
      }
      clearCommittedRefresh(pending);
      setError(undefined);
      return true;
    } catch (cause) {
      if (isCommittedRefreshCurrent(pending)) setError(safeMessage(cause));
      return false;
    }
  }
  async function refreshCommittedOutcome(
    rendered: CommittedRefresh | undefined,
  ) {
    const pending = rendered;
    if (!pending || committedRefreshRef.current !== pending) return;
    if (!pending || !beginBusyAction()) return;
    setError(undefined);
    await refreshCommittedView(pending);
    updateBusy(false);
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
      datasetReadEpochRef.current += 1;
      labelListReadEpochRef.current = undefined;
      selectionReadEpochRef.current += 1;
      datasetAdmissionRef.current = undefined;
      previousSelectionAdmissionRef.current =
        selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
      selectionAdmissionRef.current = undefined;
      setDataset(undefined);
      setCases(undefined);
      setLabels(undefined);
      setLabelCursor(undefined);
      setLabelsLoading(false);
      setLabelsError(undefined);
      setCaseRead(undefined);
      setLabelView(undefined);
      return;
    }
    const controller = new AbortController();
    const readEpoch = ++datasetReadEpochRef.current;
    const capturedRegistrationId = registrationId;
    const capturedDatasetId = datasetId;
    const capturedRefreshGeneration = refreshGeneration;
    const capturedRefreshToken = refreshToken;
    const capturedDecisionId = decision?.id;
    previousSelectionAdmissionRef.current =
      selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
    datasetAdmissionRef.current = undefined;
    selectionAdmissionRef.current = undefined;
    selectionReadEpochRef.current += 1;
    setLoading(true);
    setError(undefined);
    setCases(undefined);
    setLabels(undefined);
    setCaseCursor(undefined);
    setLabelCursor(undefined);
    setLabelsLoading(Boolean(capturedDecisionId));
    setLabelsError(undefined);
    labelListReadEpochRef.current = capturedDecisionId ? readEpoch : undefined;
    let casePagePublished = false;
    const isCurrentDatasetRead = () => {
      const current = currentReadContext.current;
      return (
        !controller.signal.aborted &&
        readEpoch === datasetReadEpochRef.current &&
        current.registrationId === capturedRegistrationId &&
        current.datasetId === capturedDatasetId &&
        current.refreshGeneration === capturedRefreshGeneration &&
        current.refreshToken === capturedRefreshToken &&
        liveRouteMatchesDataset({
          registrationId: capturedRegistrationId,
          datasetId: capturedDatasetId,
        })
      );
    };
    async function loadExamples() {
      const datasetResult = await datasetOperations.read({
        registrationId: capturedRegistrationId,
        datasetId: capturedDatasetId,
        signal: controller.signal,
      });
      if (!isCurrentDatasetRead()) return;
      if (datasetResult.data.record.id !== capturedDatasetId)
        throw new Error("The loaded dataset does not match this selection.");
      const datasetAdmission: DatasetAdmission = Object.freeze({
        registrationId: capturedRegistrationId,
        datasetId: capturedDatasetId,
        refreshGeneration: capturedRefreshGeneration,
        refreshToken: capturedRefreshToken,
        epoch: readEpoch,
        read: datasetResult.data,
      });
      datasetAdmissionRef.current = datasetAdmission;
      const previousDatasetStage = datasetStageRef.current;
      if (previousDatasetStage?.owner.datasetId === capturedDatasetId) {
        datasetStageRef.current = {
          ...previousDatasetStage,
          owner: datasetAdmission,
        };
      } else {
        const nextDatasetStage: DatasetStageSnapshot = {
          owner: datasetAdmission,
          generation: datasetEditGeneration.current,
          inputKind: "text",
          inputSource: "",
          metadataSource: "{}",
        };
        datasetStageRef.current = nextDatasetStage;
        setNewInputKind(nextDatasetStage.inputKind);
        setNewInputSource(nextDatasetStage.inputSource);
        setNewMetadataSource(nextDatasetStage.metadataSource);
      }
      setDataset(datasetResult.data);

      const casePage = await operations.listCases({
        registrationId: capturedRegistrationId,
        datasetId: capturedDatasetId,
        query: { limit: "50" },
        signal: controller.signal,
      });
      if (!isCurrentDatasetRead()) return;
      if (casePage.data.dataset_etag !== datasetResult.data.etag)
        throw new Error(
          "The examples changed while loading. Reload the current review.",
        );
      setCases(casePage.data);
      setCaseCursor(casePage.data.next_cursor ?? undefined);
      setLoading(false);
      casePagePublished = true;
      const labelPage = capturedDecisionId
        ? await operations.listLabels({
            registrationId: capturedRegistrationId,
            decisionId: capturedDecisionId,
            datasetId: capturedDatasetId,
            query: { limit: "50" },
            signal: controller.signal,
          })
        : undefined;
      if (!isCurrentDatasetRead()) return;
      if (
        labelPage &&
        labelListReadEpochRef.current === readEpoch &&
        currentReadContext.current.decisionId === capturedDecisionId &&
        navigation.current.kind === "examples" &&
        navigation.current.registrationId === capturedRegistrationId &&
        (navigation.current.datasetId ?? datasetFromRoute ?? "") ===
          capturedDatasetId &&
        (navigation.current.decisionId ?? decision?.id) === capturedDecisionId
      ) {
        setLabels(labelPage.data);
        setLabelCursor(labelPage.data.next_cursor ?? undefined);
        setLabelsError(undefined);
        setLabelsLoading(false);
        if (labelListReadEpochRef.current === readEpoch)
          labelListReadEpochRef.current = undefined;
      } else if (!capturedDecisionId) {
        setLabels(undefined);
        setLabelCursor(undefined);
        setLabelsError(undefined);
        setLabelsLoading(false);
      }
    }
    void loadExamples()
      .catch((cause: unknown) => {
        if (isCurrentDatasetRead()) {
          const message = safeMessage(cause);
          if (!casePagePublished) setError(message);
          revokePendingLabelList(readEpoch, message);
        }
      })
      .finally(() => {
        if (isCurrentDatasetRead()) setLoading(false);
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
    datasetFromRoute,
  ]);

  useEffect(() => {
    const selectionReloadToken = selectionReloadActionRef.current;
    if (selectionReloadToken) {
      selectionReloadActionRef.current = undefined;
      selectionReloadOwnerRef.current = selectionReloadToken;
    }
    if (!datasetId || !selectedCaseId) {
      selectionReadEpochRef.current += 1;
      previousSelectionAdmissionRef.current =
        selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
      selectionAdmissionRef.current = undefined;
      setSelectionLoading(false);
      setCaseRead(undefined);
      setLabelView(undefined);
      setStagedAnswers([]);
      finishSelectionReload(selectionReloadToken);
      return;
    }
    const requestedDatasetId = datasetId;
    const requestedCaseId = selectedCaseId;
    const requestedDecisionId = decision?.id;
    const admittedDataset = currentDatasetAdmission();
    if (!admittedDataset) {
      finishSelectionReload(selectionReloadToken);
      return;
    }
    if (
      !liveRouteMatchesSelection({
        registrationId,
        datasetId: requestedDatasetId,
        decisionId: requestedDecisionId,
        caseId: requestedCaseId,
      })
    ) {
      finishSelectionReload(selectionReloadToken);
      return;
    }
    const controller = new AbortController();
    const readEpoch = ++selectionReadEpochRef.current;
    const requestedNavigationEpoch = navigationEpochRef.current;
    const requestedContext = { ...currentReadContext.current };
    previousSelectionAdmissionRef.current =
      selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
    selectionAdmissionRef.current = undefined;
    setSelectionLoading(true);
    setError(undefined);
    const isCurrentSelectionRead = () => {
      const current = currentReadContext.current;
      return (
        !controller.signal.aborted &&
        readEpoch === selectionReadEpochRef.current &&
        requestedNavigationEpoch === navigationEpochRef.current &&
        current.registrationId === requestedContext.registrationId &&
        current.datasetId === requestedDatasetId &&
        current.decisionId === requestedDecisionId &&
        current.selectedCaseId === requestedCaseId &&
        current.refreshGeneration === requestedContext.refreshGeneration &&
        current.refreshToken === requestedContext.refreshToken &&
        liveRouteMatchesSelection({
          registrationId,
          datasetId: requestedDatasetId,
          decisionId: requestedDecisionId,
          caseId: requestedCaseId,
        })
      );
    };
    async function loadSelectedCase() {
      const caseResult = await operations.readCase({
        registrationId,
        datasetId: requestedDatasetId,
        caseId: requestedCaseId,
        signal: controller.signal,
      });
      if (!isCurrentSelectionRead()) return;
      const cachedDatasetAdmission = currentDatasetAdmission();
      if (!cachedDatasetAdmission) return;
      let selectedDatasetRead = cachedDatasetAdmission.read;
      let selectedCasePage: CasePage | undefined;
      let freshDatasetRead: DatasetRead | undefined;
      const requiresFreshDataset =
        selectionReloadToken !== undefined ||
        caseResult.data.dataset_etag !== cachedDatasetAdmission.read.etag;
      if (requiresFreshDataset) {
        const refreshedDataset = await datasetOperations.read({
          registrationId: requestedContext.registrationId,
          datasetId: requestedDatasetId,
          signal: controller.signal,
        });
        if (!isCurrentSelectionRead()) return;
        if (refreshedDataset.data.record.id !== requestedDatasetId)
          throw new Error("The loaded dataset does not match this selection.");
        if (caseResult.data.dataset_etag !== refreshedDataset.data.etag)
          throw new Error(
            "The example changed while loading. Reload its current review.",
          );
        freshDatasetRead = refreshedDataset.data;
        selectedDatasetRead = refreshedDataset.data;
        if (refreshedDataset.data.etag !== cachedDatasetAdmission.read.etag) {
          const currentCases = await operations.listCases({
            registrationId: requestedContext.registrationId,
            datasetId: requestedDatasetId,
            query: { limit: "50" },
            signal: controller.signal,
          });
          if (!isCurrentSelectionRead()) return;
          if (currentCases.data.dataset_etag !== refreshedDataset.data.etag)
            throw new Error(
              "The examples changed while loading. Reload the current review.",
            );
          selectedCasePage = currentCases.data;
        }
      }
      const labelResult = requestedDecisionId
        ? await operations.readLabel({
            registrationId,
            decisionId: requestedDecisionId,
            datasetId: requestedDatasetId,
            caseId: requestedCaseId,
            signal: controller.signal,
          })
        : undefined;
      if (!isCurrentSelectionRead()) return;
      const caseRecord = caseResult.data.case.record;
      if (
        !selectionPairMatches({
          datasetId: requestedDatasetId,
          decisionId: requestedDecisionId,
          caseId: requestedCaseId,
          dataset: selectedDatasetRead,
          caseRead: caseResult.data,
          labelView: labelResult?.data,
        })
      )
        throw new Error(
          "The example changed while loading. Reload its current review.",
        );
      let pairedDatasetAdmission = currentDatasetAdmission();
      if (!pairedDatasetAdmission) return;
      const selectedDatasetEpoch = selectedCasePage
        ? ++datasetReadEpochRef.current
        : undefined;
      if (pairedDatasetAdmission.read.etag !== selectedDatasetRead.etag) {
        if (
          !freshDatasetRead ||
          freshDatasetRead.etag !== selectedDatasetRead.etag ||
          !selectedCasePage
        )
          throw new Error(
            "The example changed while loading. Reload its current review.",
          );
        pairedDatasetAdmission = Object.freeze({
          registrationId: requestedContext.registrationId,
          datasetId: requestedDatasetId,
          refreshGeneration: requestedContext.refreshGeneration,
          refreshToken: requestedContext.refreshToken,
          epoch: selectedDatasetEpoch ?? ++datasetReadEpochRef.current,
          read: freshDatasetRead,
        });
        datasetAdmissionRef.current = pairedDatasetAdmission;
      }
      if (selectedCasePage) {
        markLabelListUnavailable(
          "The label list is out of date. Reload examples to refresh it.",
        );
        setDataset(selectedDatasetRead);
        setCases(selectedCasePage);
        setCaseCursor(selectedCasePage.next_cursor ?? undefined);
        setLoading(false);
      }
      if (caseResult.data.dataset_etag !== pairedDatasetAdmission.read.etag)
        throw new Error(
          "The example changed while loading. Reload its current review.",
        );
      const admission: SelectionAdmission = Object.freeze({
        registrationId,
        datasetId: requestedDatasetId,
        decisionId: requestedDecisionId,
        caseId: requestedCaseId,
        readEpoch,
        navigationEpoch: requestedNavigationEpoch,
        datasetAdmission: pairedDatasetAdmission,
        caseRead: caseResult.data,
        labelView: labelResult?.data,
      });
      const previous = previousSelectionAdmissionRef.current;
      const sameSelection =
        !!previous &&
        previous.registrationId === admission.registrationId &&
        previous.datasetId === admission.datasetId &&
        previous.decisionId === admission.decisionId &&
        previous.caseId === admission.caseId;
      const caseStage = caseStageRef.current;
      const labelStage = labelStageRef.current;
      const caseOwnedByPrevious = !!previous && caseStage?.owner === previous;
      const labelOwnedByPrevious = !!previous && labelStage?.owner === previous;
      const caseStageChanged =
        !!previous &&
        caseStage !== undefined &&
        caseStage.owner === previous &&
        (caseStage.inputKind !== previous.caseRead.case.record.input_kind ||
          caseStage.inputSource !==
            previous.caseRead.case.record.input_source ||
          caseStage.metadataSource !==
            (previous.caseRead.case.record.metadata_source ?? "{}"));
      const labelStageChanged =
        !!previous &&
        labelStage !== undefined &&
        labelStage.owner === previous &&
        (labelStage.note.trim().length > 0 ||
          [...labelStage.answers].sort().join("\0") !==
            [...(previous.labelView?.label?.acceptable_option_ids ?? [])]
              .sort()
              .join("\0"));
      const caseReviewChanged =
        previous !== undefined &&
        caseOwnedByPrevious &&
        (previous.caseRead.case.etag !== caseResult.data.case.etag ||
          previous.datasetAdmission.read.etag !==
            admission.datasetAdmission.read.etag ||
          !sameCaseSource(
            previous.caseRead.case.record,
            caseResult.data.case.record,
          ));
      const labelReviewChanged =
        previous !== undefined &&
        labelOwnedByPrevious &&
        (previous.labelView === undefined
          ? labelResult !== undefined
          : labelResult === undefined ||
            !sameLabelReview(previous.labelView, labelResult.data));
      const stageNeedsReview =
        sameSelection &&
        ((caseStageChanged && caseReviewChanged) ||
          (labelStageChanged && labelReviewChanged));
      const preserveCaseStage =
        caseStageChanged && sameSelection && caseOwnedByPrevious;
      const preserveLabelStage =
        labelStageChanged && sameSelection && labelOwnedByPrevious;
      selectionAdmissionRef.current = admission;
      if (!stageNeedsReview) {
        if (preserveCaseStage && caseStage)
          caseStageRef.current = { ...caseStage, owner: admission };
        if (preserveLabelStage && labelStage)
          labelStageRef.current = { ...labelStage, owner: admission };
      }
      if (!preserveCaseStage) {
        const nextCaseStage: CaseStageSnapshot = {
          owner: admission,
          generation: caseEditGeneration.current,
          inputKind: caseRecord.input_kind,
          inputSource: caseRecord.input_source,
          metadataSource: caseRecord.metadata_source ?? "{}",
        };
        caseStageRef.current = nextCaseStage;
        setInputKind(nextCaseStage.inputKind);
        setInputSource(nextCaseStage.inputSource);
        setMetadataSource(nextCaseStage.metadataSource);
      }
      if (!preserveLabelStage) {
        const nextLabelStage: LabelStageSnapshot = {
          owner: admission,
          generation: labelEditGeneration.current,
          answers: labelResult?.data.label?.acceptable_option_ids ?? [],
          note: "",
        };
        labelStageRef.current = nextLabelStage;
        setStagedAnswers(nextLabelStage.answers);
        updateNote(nextLabelStage.note);
      }
      if (stageNeedsReview) {
        updateSelectionNeedsReview(true);
        setNotice(
          "The current example or review changed while edits were staged. Review it before reapplying those edits.",
        );
      } else if (!editorDirty || !sameSelection) {
        updateSelectionNeedsReview(false);
        updateEditorDirty(false);
        setNotice(undefined);
      }
      setCaseRead(caseResult.data);
      setLabelView(labelResult?.data);
      setSelectionLoading(false);
    }
    void loadSelectedCase()
      .catch((cause: unknown) => {
        if (isCurrentSelectionRead()) {
          setError(safeMessage(cause));
          setSelectionLoading(false);
        }
      })
      .finally(() => finishSelectionReload(selectionReloadToken));
    return () => controller.abort();
  }, [
    datasetScopeReady,
    datasetOperations,
    decision,
    datasetId,
    navigationEpoch,
    operations,
    registrationId,
    refreshGeneration,
    refreshToken,
    selectedCaseId,
    selectionReloadGeneration,
  ]);

  async function loadMoreCases(rendered: DatasetAdmission | undefined) {
    const admission = captureRenderedDataset(rendered);
    if (!admission || !caseCursor || !beginBusyAction()) return;
    const context = currentReadContext.current;
    try {
      const result = await operations.listCases({
        registrationId,
        datasetId,
        query: { cursor: caseCursor, limit: "50" },
      });
      if (!isCurrentContext(context) || currentDatasetAdmission() !== admission)
        return;
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
      if (isCurrentContext(context) && currentDatasetAdmission() === admission)
        setError(safeMessage(cause));
    } finally {
      updateBusy(false);
    }
  }

  async function loadMoreLabels(
    rendered: DatasetAdmission | undefined,
    renderedDecisionId: string | undefined,
  ) {
    const admission = captureRenderedDataset(rendered);
    if (
      !admission ||
      !decision ||
      decision.id !== renderedDecisionId ||
      !labelCursor ||
      !beginBusyAction()
    )
      return;
    const context = currentReadContext.current;
    try {
      const result = await operations.listLabels({
        registrationId,
        decisionId: decision.id,
        datasetId,
        query: { cursor: labelCursor, limit: "50" },
      });
      if (
        !isCurrentContext(context) ||
        currentDatasetAdmission() !== admission ||
        currentReadContext.current.decisionId !== decision.id
      )
        return;
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
      if (isCurrentContext(context) && currentDatasetAdmission() === admission)
        setError(safeMessage(cause));
    } finally {
      updateBusy(false);
    }
  }

  async function selectCase(
    rendered: DatasetAdmission | undefined,
    renderedDecisionId: string | undefined,
    caseId: string,
  ) {
    const admission = captureRenderedDataset(rendered);
    if (
      !admission ||
      currentReadContext.current.decisionId !== renderedDecisionId ||
      caseId === selectedCaseId
    )
      return;
    const moved = await onDatasetChange(admission.datasetId, caseId);
    if (
      !moved ||
      captureRenderedDataset(admission) !== admission ||
      currentReadContext.current.decisionId !== renderedDecisionId
    )
      return;
    setSelectedCaseId(caseId);
  }
  async function selectDataset(
    rendered: {
      context: ReadContext;
      navigationEpoch: number;
      datasetAdmission?: DatasetAdmission;
    },
    nextDatasetId: string,
  ) {
    if (
      !isCurrentContext(rendered.context) ||
      rendered.navigationEpoch !== navigationEpochRef.current ||
      currentDatasetAdmission() !== rendered.datasetAdmission
    )
      return;
    const priorRegistrationId = rendered.context.registrationId;
    const moved = await onDatasetChange(nextDatasetId || undefined, undefined);
    if (
      moved &&
      liveRouteMatchesDataset({
        registrationId: priorRegistrationId,
        datasetId: nextDatasetId,
      })
    ) {
      setDatasetId(nextDatasetId);
      setSelectedCaseId(undefined);
    }
  }

  function reloadSelectedReview(rendered: {
    context: ReadContext;
    navigationEpoch: number;
    datasetAdmission?: DatasetAdmission;
  }) {
    if (
      !isCurrentContext(rendered.context) ||
      rendered.navigationEpoch !== navigationEpochRef.current ||
      currentDatasetAdmission() !== rendered.datasetAdmission ||
      !liveRouteMatchesDataset({
        registrationId: rendered.context.registrationId,
        datasetId: rendered.context.datasetId,
      })
    )
      return;
    if (!beginBusyAction()) return;
    selectionReloadActionRef.current = Symbol("selected-review-reload");
    setSelectionReloadGeneration((value) => value + 1);
  }
  function reloadExamples(rendered: {
    context: ReadContext;
    navigationEpoch: number;
    datasetAdmission?: DatasetAdmission;
  }) {
    if (
      !canStartBusyAction() ||
      !isCurrentContext(rendered.context) ||
      rendered.navigationEpoch !== navigationEpochRef.current ||
      currentDatasetAdmission() !== rendered.datasetAdmission ||
      committedRefreshRef.current
    )
      return;
    setRefreshGeneration((value) => value + 1);
  }

  function reviewCurrentSelection(rendered: SelectionAdmission | undefined) {
    if (!canStartBusyAction()) return;
    const admission = captureRenderedSelection(rendered);
    if (!admission) return;
    if (caseStageRef.current)
      caseStageRef.current = { ...caseStageRef.current, owner: admission };
    if (labelStageRef.current)
      labelStageRef.current = { ...labelStageRef.current, owner: admission };
    updateSelectionNeedsReview(false);
    setNotice(
      "Current example and label review acknowledged. Your staged changes remain available to reapply deliberately.",
    );
  }

  async function saveLabel(
    rendered: SelectionAdmission | undefined,
    action: "set" | "resolve" | "dispute" | "clear",
  ): Promise<boolean> {
    const snapshot = captureInteractiveLabel(rendered, action);
    if (!snapshot) return false;
    return executeLabelWrite(snapshot);
  }

  async function executeLabelWrite(
    snapshot: LabelWriteSnapshot,
  ): Promise<boolean> {
    if (captureRenderedSelection(snapshot.admission) !== snapshot.admission)
      return false;
    if (!acquireMutationLock()) return false;
    try {
      return await saveLabelWithLock(snapshot);
    } finally {
      releaseMutationLock();
    }
  }

  async function saveLabelWithLock(
    snapshot: LabelWriteSnapshot,
  ): Promise<boolean> {
    const { admission, stage, action } = snapshot;
    const review = admission?.labelView;
    const pending = pendingLabelRef.current;
    if (
      committedRefreshRef.current ||
      !admission ||
      !review ||
      !admission.decisionId ||
      selectionNeedsReviewRef.current ||
      !ownsSelectionStage(labelStageRef.current, admission) ||
      (stage.answers.length === 0 && action !== "clear" && action !== "dispute")
    )
      return false;
    if (pending?.uncertain && !matchesSelectionScope(pending.scope, admission))
      return false;
    if (pending?.conflict) return false;
    if (pendingLabelUncertainRef.current && !pending?.uncertain) return false;
    updateBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const context = { ...currentReadContext.current };
    const decisionId = admission.decisionId;
    const caseId = admission.caseId;
    const stagedGeneration = stage.generation;
    const stagedAnswersAtSubmit = [...stage.answers];
    const noteAtSubmit = stage.note;
    const body: LabelMutationBody = pending?.uncertain
      ? pending.body
      : {
          schema_version: 1,
          operation_id: opId(),
          edits: [
            {
              review: review.review,
              action,
              ...(action === "set" || action === "resolve"
                ? { acceptable_option_ids: stagedAnswersAtSubmit }
                : {}),
              ...(action === "set" || action === "resolve"
                ? { provenance: "human" as const }
                : {}),
              ...(action !== "clear" && noteAtSubmit
                ? { note: noteAtSubmit }
                : {}),
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
        updatePendingLabel({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
            decisionId: admission.decisionId,
            caseId: admission.caseId,
          },
          uncertain: true,
          conflict: false,
        });
      else if (cause instanceof ApiError && cause.status === 409)
        updatePendingLabel({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
            decisionId: admission.decisionId,
            caseId: admission.caseId,
          },
          uncertain: false,
          conflict: true,
        });
      else updatePendingLabel(undefined);
      setError(safeMessage(cause));
      updateBusy(false);
      setMutationInFlight(false);
      return false;
    }

    const committedRefresh: CommittedRefresh = {
      kind: "label",
      context,
      decisionId,
      caseId,
      readEpoch: admission.readEpoch,
      navigationEpoch: admission.navigationEpoch,
      receipt,
      body,
      stagedGeneration,
      stagedAnswers: stagedAnswersAtSubmit,
      note: noteAtSubmit,
    };
    committedRefreshRef.current = committedRefresh;
    setCommittedRefresh(committedRefresh);
    updatePendingLabel(undefined);
    setNotice(undefined);
    setMutationInFlight(false);
    await refreshCommittedView(committedRefresh);
    updateBusy(false);
    return true;
  }

  async function reviewLabelConflict(
    rendered: SelectionAdmission | undefined,
  ): Promise<void> {
    if (!canStartBusyAction()) return;
    const admission = captureRenderedSelection(rendered);
    if (
      committedRefreshRef.current ||
      !admission?.decisionId ||
      !admission.labelView
    )
      return;
    const context = currentReadContext.current;
    if (!beginBusyAction()) return;
    setError(undefined);
    try {
      const refreshedDataset = await datasetOperations.read({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
      });
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const refreshedCase = await operations.readCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
      });
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const refreshed = await operations.readLabel({
        registrationId: admission.registrationId,
        decisionId: admission.decisionId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
      });
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission ||
        refreshed.data.review.case_id !== admission.caseId ||
        refreshed.data.review.dataset_id !== admission.datasetId ||
        refreshed.data.review.decision_id !== admission.decisionId ||
        refreshedCase.data.case.record.id !== admission.caseId ||
        refreshedCase.data.case.record.dataset_id !== admission.datasetId ||
        refreshedCase.data.dataset_etag !== refreshedDataset.data.etag ||
        !sameCaseSource(refreshedCase.data.case.record, refreshed.data.case)
      )
        return;
      const reviewedAdmission = publishReviewedPair(
        context,
        refreshedDataset.data,
        refreshedCase.data,
        refreshed.data,
        admission.readEpoch,
        admission.navigationEpoch,
      );
      if (!reviewedAdmission) return;
      const caseStillCurrent =
        admission.caseRead.case.etag === refreshedCase.data.case.etag &&
        sameCaseSource(
          admission.caseRead.case.record,
          refreshedCase.data.case.record,
        );
      // Keep the user's staged answer intact. A new deliberate save will use
      // this reviewed server context and a fresh operation ID.
      if (labelStageRef.current)
        labelStageRef.current = {
          ...labelStageRef.current,
          owner: reviewedAdmission,
        };
      if (caseStillCurrent && caseStageRef.current)
        caseStageRef.current = {
          ...caseStageRef.current,
          owner: reviewedAdmission,
        };
      updatePendingLabel(undefined);
      updateSelectionNeedsReview(!caseStillCurrent);
      setNotice(
        caseStillCurrent
          ? undefined
          : "The case changed while reviewing its label. Review the current selection before another change.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      updateBusy(false);
    }
  }

  function retryUnknownLabel(rendered: SelectionAdmission | undefined) {
    const pending = pendingLabelRef.current;
    const action = pending?.body.edits[0]?.action;
    if (pending?.uncertain && action) void saveLabel(rendered, action);
  }

  async function saveCase(
    rendered: SelectionAdmission | undefined,
  ): Promise<boolean> {
    const snapshot = captureInteractiveCase(rendered);
    if (!snapshot) return false;
    return executeCaseWrite(snapshot);
  }

  async function executeCaseWrite(
    snapshot: CaseWriteSnapshot,
  ): Promise<boolean> {
    if (captureRenderedSelection(snapshot.admission) !== snapshot.admission)
      return false;
    if (!acquireMutationLock()) return false;
    try {
      return await saveCaseWithLock(snapshot);
    } finally {
      releaseMutationLock();
    }
  }

  async function saveCaseWithLock(
    snapshot: CaseWriteSnapshot,
  ): Promise<boolean> {
    const { admission, stage } = snapshot;
    const data = currentDatasetAdmission();
    const pending = pendingCaseRef.current;
    if (
      committedRefreshRef.current ||
      !admission ||
      !data ||
      admission.datasetAdmission !== data ||
      selectionNeedsReviewRef.current ||
      !ownsSelectionStage(caseStageRef.current, admission)
    )
      return false;
    if (pending?.uncertain && !matchesSelectionScope(pending.scope, admission))
      return false;
    if (pending?.conflict) return false;
    if (pendingCaseUncertainRef.current && !pending?.uncertain) return false;
    updateBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const context = { ...currentReadContext.current };
    const caseId = admission.caseId;
    const decisionId = admission.decisionId;
    const stagedGeneration = stage.generation;
    const inputKindAtSubmit = stage.inputKind;
    const inputSourceAtSubmit = stage.inputSource;
    const metadataSourceAtSubmit = stage.metadataSource;
    const record = admission.caseRead.case.record;
    const body: CaseEditBody = pending?.uncertain
      ? pending.body
      : {
          schema_version: 1,
          operation_id: opId(),
          expected_case_etag: admission.caseRead.case.etag,
          expected_dataset_etag: data.read.etag,
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
        updatePendingCase({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
            decisionId: admission.decisionId,
            caseId: admission.caseId,
          },
          uncertain: true,
          conflict: false,
        });
      else if (cause instanceof ApiError && cause.status === 409) {
        updatePendingCase({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
            decisionId: admission.decisionId,
            caseId: admission.caseId,
          },
          uncertain: false,
          conflict: true,
        });
        setCaseConflictReviewed(false);
      } else updatePendingCase(undefined);
      setError(safeMessage(cause));
      updateBusy(false);
      setMutationInFlight(false);
      return false;
    }

    const committedRefresh: CommittedRefresh = {
      kind: "case",
      context,
      caseId,
      decisionId,
      readEpoch: admission.readEpoch,
      navigationEpoch: admission.navigationEpoch,
      receipt,
      body,
      stagedGeneration,
      inputKind: inputKindAtSubmit,
      inputSource: inputSourceAtSubmit,
      metadataSource: metadataSourceAtSubmit,
    };
    committedRefreshRef.current = committedRefresh;
    setCommittedRefresh(committedRefresh);
    updatePendingCase(undefined);
    setNotice(undefined);
    setMutationInFlight(false);
    await refreshCommittedView(committedRefresh);
    updateBusy(false);
    return true;
  }

  async function reviewCaseConflict(rendered: SelectionAdmission | undefined) {
    if (!canStartBusyAction()) return;
    const admission = captureRenderedSelection(rendered);
    if (committedRefreshRef.current || !admission) return;
    const context = currentReadContext.current;
    if (!beginBusyAction()) return;
    setError(undefined);
    try {
      const currentDataset = await datasetOperations.read({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
      });
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const currentCase = await operations.readCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
      });
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const currentLabel = admission.decisionId
        ? await operations.readLabel({
            registrationId: admission.registrationId,
            decisionId: admission.decisionId,
            datasetId: admission.datasetId,
            caseId: admission.caseId,
          })
        : undefined;
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const reviewed = publishReviewedPair(
        context,
        currentDataset.data,
        currentCase.data,
        currentLabel?.data,
        admission.readEpoch,
        admission.navigationEpoch,
      );
      if (!reviewed) return;
      const labelUnchanged =
        admission.labelView === undefined
          ? currentLabel === undefined
          : currentLabel !== undefined &&
            admission.labelView.review.decision_etag ===
              currentLabel.data.review.decision_etag &&
            admission.labelView.review.draft_etag ===
              currentLabel.data.review.draft_etag &&
            admission.labelView.review.input_hash ===
              currentLabel.data.review.input_hash &&
            sameLabelRecord(
              admission.labelView.label ?? null,
              currentLabel.data.label ?? null,
            );
      if (caseStageRef.current)
        caseStageRef.current = { ...caseStageRef.current, owner: reviewed };
      if (labelUnchanged && labelStageRef.current)
        labelStageRef.current = {
          ...labelStageRef.current,
          owner: reviewed,
        };
      updateSelectionNeedsReview(!labelUnchanged);
      updatePendingCase(undefined);
      setCaseConflictReviewed(true);
      setNotice(
        labelUnchanged
          ? "Current case and dataset versions reviewed. Your edited source is retained; reapply it deliberately."
          : "Current case and dataset versions reviewed. Review the changed label context before another label change.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      updateBusy(false);
    }
  }

  async function addCase(
    rendered: DatasetAdmission | undefined,
  ): Promise<boolean> {
    const snapshot = captureInteractiveDataset(rendered);
    if (!snapshot) return false;
    return executeAddCase(snapshot);
  }

  async function executeAddCase(
    snapshot: DatasetWriteSnapshot,
  ): Promise<boolean> {
    if (captureRenderedDataset(snapshot.admission) !== snapshot.admission)
      return false;
    if (!acquireMutationLock()) return false;
    try {
      return await addCaseWithLock(snapshot);
    } finally {
      releaseMutationLock();
    }
  }

  async function addCaseWithLock(
    snapshot: DatasetWriteSnapshot,
  ): Promise<boolean> {
    const { admission, stage } = snapshot;
    const pending = pendingAddRef.current;
    if (committedRefreshRef.current || !admission) return false;
    if (pending?.uncertain && !matchesDatasetScope(pending.scope, admission))
      return false;
    if (pending?.conflict) return false;
    updateBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const body: AddCaseBody = pending?.uncertain
      ? pending.body
      : {
          schema_version: 1,
          operation_id: opId(),
          expected_dataset_etag: admission.read.etag,
          input_kind: stage.inputKind,
          input_source: stage.inputSource,
          metadata_source: stage.metadataSource,
          tags: [],
          split: "development",
          group_id: null,
          derived_from: [],
        };
    try {
      const result = await operations.addCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        body,
      });
      updatePendingAdd(undefined);
      setAddConflictReviewed(false);
      const createdId = result.data.case?.record.id;
      setAddCaseOpen(false);
      updateEditorDirty(false);
      setNewInputSource("");
      setNewInputKind("text");
      setNewMetadataSource("{}");
      datasetStageRef.current = {
        owner: admission,
        generation: ++datasetEditGeneration.current,
        inputKind: "text",
        inputSource: "",
        metadataSource: "{}",
      };
      setRefreshGeneration((value) => value + 1);
      if (createdId) {
        setNotice("Example added. Select it from the cases list when ready.");
      }
    } catch (cause) {
      if (isOutcomeUnknown(cause))
        updatePendingAdd({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
          },
          uncertain: true,
          conflict: false,
        });
      else if (cause instanceof ApiError && cause.status === 409) {
        updatePendingAdd({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
          },
          uncertain: false,
          conflict: true,
        });
        setAddConflictReviewed(false);
      } else updatePendingAdd(undefined);
      setError(safeMessage(cause));
      return false;
    } finally {
      updateBusy(false);
      setMutationInFlight(false);
    }
    return true;
  }

  async function reviewAddConflict(rendered: DatasetAdmission | undefined) {
    if (!canStartBusyAction()) return;
    const admission = captureRenderedDataset(rendered);
    if (committedRefreshRef.current || !admission) return;
    const context = currentReadContext.current;
    if (!beginBusyAction()) return;
    setError(undefined);
    try {
      const currentDataset = await datasetOperations.read({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
      });
      if (
        !isCurrentContext(context) ||
        currentDatasetAdmission() !== admission ||
        currentDataset.data.record.id !== admission.datasetId
      )
        return;
      const currentCases = await operations.listCases({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        query: { limit: "50" },
      });
      if (!isCurrentContext(context) || currentDatasetAdmission() !== admission)
        return;
      if (currentCases.data.dataset_etag !== currentDataset.data.etag)
        throw new Error(
          "The examples changed while loading. Reload the current review.",
        );
      const previousDatasetEpoch = datasetReadEpochRef.current;
      const reviewedDataset: DatasetAdmission = Object.freeze({
        ...admission,
        epoch: ++datasetReadEpochRef.current,
        read: currentDataset.data,
      });
      if (
        admission.read.etag !== currentDataset.data.etag ||
        labelListReadEpochRef.current === previousDatasetEpoch
      )
        markLabelListUnavailable(
          "The label list is out of date. Reload examples to refresh it.",
        );
      datasetAdmissionRef.current = reviewedDataset;
      if (datasetStageRef.current)
        datasetStageRef.current = {
          ...datasetStageRef.current,
          owner: reviewedDataset,
        };
      selectionReadEpochRef.current += 1;
      previousSelectionAdmissionRef.current =
        selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
      selectionAdmissionRef.current = undefined;
      setDataset(currentDataset.data);
      setCases(currentCases.data);
      setCaseCursor(currentCases.data.next_cursor ?? undefined);
      updatePendingAdd(undefined);
      setAddConflictReviewed(true);
      setNotice(
        "Current dataset and cases reviewed. Your new example source is retained; reapply it deliberately.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      updateBusy(false);
    }
  }

  async function removeSelectedCase(rendered: SelectionAdmission | undefined) {
    const admission = captureRenderedSelection(rendered);
    if (
      !admission ||
      !ownsSelectionStage(labelStageRef.current, admission) ||
      !ownsSelectionStage(caseStageRef.current, admission) ||
      selectionNeedsReviewRef.current ||
      pendingLabelUncertainRef.current ||
      pendingCaseUncertainRef.current ||
      pendingAddRef.current?.uncertain ||
      (pendingRemoveRef.current?.uncertain &&
        !matchesSelectionScope(pendingRemoveRef.current.scope, admission)) ||
      pendingRemoveRef.current?.conflict ||
      committedRefreshRef.current ||
      busyRef.current ||
      mutationLockRef.current
    )
      return;
    if (!acquireMutationLock()) return;
    try {
      await removeSelectedCaseWithLock(admission);
    } finally {
      releaseMutationLock();
    }
  }

  async function removeSelectedCaseWithLock(admission: SelectionAdmission) {
    const data = currentDatasetAdmission();
    const pending = pendingRemoveRef.current;
    if (
      committedRefreshRef.current ||
      !admission ||
      !data ||
      admission.datasetAdmission !== data ||
      selectionNeedsReviewRef.current ||
      !ownsSelectionStage(labelStageRef.current, admission) ||
      !ownsSelectionStage(caseStageRef.current, admission)
    )
      return;
    if (pending?.uncertain && !matchesSelectionScope(pending.scope, admission))
      return;
    if (pending?.conflict) return;
    updateBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const body: RemoveCaseBody = pending?.uncertain
      ? pending.body
      : {
          schema_version: 1,
          operation_id: opId(),
          expected_case_etag: admission.caseRead.case.etag,
          expected_dataset_etag: data.read.etag,
        };
    try {
      const result = await operations.removeCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
        body,
      });
      updatePendingRemove(undefined);
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
        updatePendingRemove({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
            decisionId: admission.decisionId,
            caseId: admission.caseId,
          },
          uncertain: true,
          conflict: false,
        });
      else if (cause instanceof ApiError && cause.status === 409) {
        updatePendingRemove({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
            decisionId: admission.decisionId,
            caseId: admission.caseId,
          },
          uncertain: false,
          conflict: true,
        });
        setRemoveConflictReviewed(false);
      } else updatePendingRemove(undefined);
      setError(safeMessage(cause));
    } finally {
      updateBusy(false);
      setMutationInFlight(false);
    }
  }

  async function reviewRemoveConflict(
    rendered: SelectionAdmission | undefined,
  ) {
    if (!canStartBusyAction()) return;
    const admission = captureRenderedSelection(rendered);
    if (committedRefreshRef.current || !admission) return;
    const context = currentReadContext.current;
    if (!beginBusyAction()) return;
    setError(undefined);
    try {
      const currentDataset = await datasetOperations.read({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
      });
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const currentCase = await operations.readCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
      });
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const currentLabel = admission.decisionId
        ? await operations.readLabel({
            registrationId: admission.registrationId,
            decisionId: admission.decisionId,
            datasetId: admission.datasetId,
            caseId: admission.caseId,
          })
        : undefined;
      if (
        !isCurrentContext(context) ||
        currentSelectionAdmission() !== admission
      )
        return;
      const reviewed = publishReviewedPair(
        context,
        currentDataset.data,
        currentCase.data,
        currentLabel?.data,
        admission.readEpoch,
        admission.navigationEpoch,
      );
      if (!reviewed) return;
      if (caseStageRef.current)
        caseStageRef.current = { ...caseStageRef.current, owner: reviewed };
      if (labelStageRef.current)
        labelStageRef.current = { ...labelStageRef.current, owner: reviewed };
      updateSelectionNeedsReview(false);
      updatePendingRemove(undefined);
      setRemoveConflictReviewed(true);
      setNotice(
        "Current case and dataset versions reviewed. Reapply removal deliberately if the case is still present.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      updateBusy(false);
    }
  }

  const currentCase = caseRead?.case.record;
  const currentLabel = labelView?.label;
  const writableDataset = captureDatasetAdmission();
  const writableSelection = captureSelectionAdmission();
  const renderedReadScope = {
    context: { ...currentReadContext.current },
    navigationEpoch: navigationEpochRef.current,
    datasetAdmission: writableDataset,
  };
  const datasetReady = writableDataset !== undefined;
  const selectionReady = writableSelection !== undefined;
  const pendingLabelMatchesSelection =
    !!pendingLabel &&
    !!writableSelection &&
    matchesSelectionScope(pendingLabel.scope, writableSelection);
  const pendingCaseMatchesSelection =
    !!pendingCase &&
    !!writableSelection &&
    matchesSelectionScope(pendingCase.scope, writableSelection);
  const pendingRemoveMatchesSelection =
    !!pendingRemove &&
    !!writableSelection &&
    matchesSelectionScope(pendingRemove.scope, writableSelection);
  const pendingAddMatchesDataset =
    !!pendingAdd &&
    !!writableDataset &&
    matchesDatasetScope(pendingAdd.scope, writableDataset);
  const caseEditable =
    selectionReady &&
    !selectionNeedsReview &&
    !pendingCase?.uncertain &&
    !pendingLabel?.uncertain &&
    !pendingAdd?.uncertain &&
    !pendingRemove?.uncertain &&
    !!writableSelection &&
    ownsSelectionStage(caseStageRef.current, writableSelection);
  const labelEditable =
    selectionReady &&
    writableSelection?.labelView !== undefined &&
    !selectionNeedsReview &&
    !pendingLabel?.uncertain &&
    !pendingCase?.uncertain &&
    !pendingAdd?.uncertain &&
    !pendingRemove?.uncertain &&
    !!writableSelection &&
    ownsSelectionStage(labelStageRef.current, writableSelection);
  function hasCurrentLabelEdits(): boolean {
    const admission = currentSelectionAdmission();
    const stage = labelStageRef.current;
    return (
      !!admission?.labelView &&
      !!stage &&
      stage.owner === admission &&
      ([...stage.answers].sort().join("\0") !==
        [...(admission.labelView.label?.acceptable_option_ids ?? [])]
          .sort()
          .join("\0") ||
        stage.note.trim().length > 0)
    );
  }
  async function saveBeforeLeaving() {
    if (mutationLockRef.current)
      throw new Error(
        "An examples write is still in progress. Keep this page open until it finishes.",
      );
    if (committedRefreshRef.current) {
      const kind = committedRefreshRef.current.kind;
      throw new Error(
        kind === "label"
          ? "The label was saved. Refresh its current review before leaving or starting another change."
          : "The case was saved. Refresh its current review before leaving or starting another change.",
      );
    }
    if (
      pendingLabelRef.current?.uncertain ||
      pendingCaseRef.current?.uncertain ||
      pendingAddRef.current?.uncertain ||
      pendingRemoveRef.current?.uncertain
    )
      throw new Error(
        "A write may have completed. Retry its original request before leaving this examples page.",
      );
    if (
      pendingLabelRef.current?.conflict ||
      pendingCaseRef.current?.conflict ||
      pendingAddRef.current?.conflict ||
      pendingRemoveRef.current?.conflict
    )
      throw new Error(
        "Review the current server state before reapplying or explicitly discarding this conflicted change.",
      );
    const initialDataset = currentDatasetAdmission();
    const expectedDataset: DatasetScope | undefined = initialDataset
      ? {
          registrationId: initialDataset.registrationId,
          datasetId: initialDataset.datasetId,
        }
      : undefined;
    const initialSelection = currentSelectionAdmission();
    const expectedSelection: SelectionScope | undefined = initialSelection
      ? {
          registrationId: initialSelection.registrationId,
          datasetId: initialSelection.datasetId,
          decisionId: initialSelection.decisionId,
          caseId: initialSelection.caseId,
        }
      : undefined;
    if (addCaseOpen) {
      const snapshot = expectedDataset
        ? captureGuardDataset(expectedDataset)
        : undefined;
      if (!snapshot || !(await executeAddCase(snapshot)))
        throw new Error(
          "The new example did not save. Its source is still available for review.",
        );
    }
    const hadCaseEdit = editCase;
    if (hadCaseEdit) {
      const snapshot = expectedSelection
        ? captureGuardCase(expectedSelection)
        : undefined;
      if (!snapshot || !(await executeCaseWrite(snapshot)))
        throw new Error(
          "The case edit did not save. Its source is still available for review.",
        );
    }
    if (committedRefreshRef.current) {
      throw new Error(
        "The case was saved. Refresh its current review before saving another change or leaving.",
      );
    }
    const afterCaseAdmission = currentSelectionAdmission();
    const afterCaseStage = labelStageRef.current;
    const labelChanged =
      !!afterCaseAdmission?.labelView &&
      !!afterCaseStage &&
      afterCaseStage.owner === afterCaseAdmission &&
      ([...afterCaseStage.answers].sort().join("\0") !==
        [...(afterCaseAdmission.labelView.label?.acceptable_option_ids ?? [])]
          .sort()
          .join("\0") ||
        afterCaseStage.note.trim().length > 0);
    if (afterCaseAdmission?.decisionId && labelChanged) {
      if (afterCaseStage.answers.length === 0)
        throw new Error(
          "Choose an answer or explicitly clear this label before leaving.",
        );
      const action =
        afterCaseAdmission.labelView?.label?.status === "disputed"
          ? "resolve"
          : "set";
      const scope: SelectionScope = {
        registrationId: afterCaseAdmission.registrationId,
        datasetId: afterCaseAdmission.datasetId,
        decisionId: afterCaseAdmission.decisionId,
        caseId: afterCaseAdmission.caseId,
      };
      const snapshot = captureGuardLabel(scope, action);
      if (!snapshot || !(await executeLabelWrite(snapshot)))
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
  function launchImport(rendered: DatasetAdmission | undefined) {
    if (
      canStartBusyAction() &&
      !committedRefreshRef.current &&
      captureRenderedDataset(rendered)
    )
      onImport();
  }
  function launchSplit(rendered: DatasetAdmission | undefined) {
    if (
      canStartBusyAction() &&
      !committedRefreshRef.current &&
      captureRenderedDataset(rendered)
    )
      onSplit();
  }
  function openAddCase(rendered: DatasetAdmission | undefined) {
    const admission = captureRenderedDataset(rendered);
    if (!admission || !canStartBusyAction() || committedRefreshRef.current)
      return;
    const stage = datasetStageRef.current;
    if (!stage || stage.owner !== admission) {
      datasetStageRef.current = {
        owner: admission,
        generation: ++datasetEditGeneration.current,
        inputKind: newInputKind,
        inputSource: newInputSource,
        metadataSource: newMetadataSource,
      };
    }
    setAddCaseOpen(true);
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
      hasCurrentLabelEdits() ||
      committedRefresh !== undefined ||
      uncertainWrite ||
      unresolvedConflict ||
      mutationInFlight,
    isDirtyNow: () =>
      mutationLockRef.current ||
      committedRefreshRef.current !== undefined ||
      pendingLabelRef.current?.uncertain === true ||
      pendingCaseRef.current?.uncertain === true ||
      pendingAddRef.current?.uncertain === true ||
      pendingRemoveRef.current?.uncertain === true ||
      pendingLabelRef.current?.conflict === true ||
      pendingCaseRef.current?.conflict === true ||
      pendingAddRef.current?.conflict === true ||
      pendingRemoveRef.current?.conflict === true ||
      editorDirtyRef.current ||
      hasCurrentLabelEdits(),
    blockedMessage: navigationBlockedMessage,
    allowDiscardWhenBlocked: committedRefresh !== undefined,
    save: saveBeforeLeaving,
    discard: () => {
      committedRefreshRef.current = undefined;
      setCommittedRefresh(undefined);
      updateEditorDirty(false);
      updateNote("");
      if (currentCase) {
        setInputKind(currentCase.input_kind);
        setInputSource(currentCase.input_source);
        setMetadataSource(currentCase.metadata_source ?? "{}");
        const admission = currentSelectionAdmission();
        if (admission) {
          caseStageRef.current = {
            owner: admission,
            generation: ++caseEditGeneration.current,
            inputKind: currentCase.input_kind,
            inputSource: currentCase.input_source,
            metadataSource: currentCase.metadata_source ?? "{}",
          };
        }
      }
      setStagedAnswers(currentLabel?.acceptable_option_ids ?? []);
      updateNote("");
      const selection = currentSelectionAdmission();
      if (selection)
        labelStageRef.current = {
          owner: selection,
          generation: ++labelEditGeneration.current,
          answers: currentLabel?.acceptable_option_ids ?? [],
          note: "",
        };
      const datasetAdmission = currentDatasetAdmission();
      if (datasetAdmission) {
        datasetStageRef.current = {
          owner: datasetAdmission,
          generation: ++datasetEditGeneration.current,
          inputKind: "text",
          inputSource: "",
          metadataSource: "{}",
        };
      }
      setNewInputKind("text");
      setNewInputSource("");
      setNewMetadataSource("{}");
      setEditCase(false);
      setAddCaseOpen(false);
      setDeleteCaseOpen(false);
      if (pendingLabel?.conflict) updatePendingLabel(undefined);
      if (pendingCase?.conflict) updatePendingCase(undefined);
      if (pendingAdd?.conflict) updatePendingAdd(undefined);
      if (pendingRemove?.conflict) updatePendingRemove(undefined);
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
            <button
              type="button"
              onClick={() => launchImport(writableDataset)}
              disabled={!datasetReady || busy || !!committedRefresh}
            >
              Import examples
            </button>
            <button
              type="button"
              onClick={() => launchSplit(writableDataset)}
              disabled={!datasetReady || busy || !!committedRefresh}
            >
              Split dataset
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => {
                openAddCase(writableDataset);
              }}
              disabled={!datasetReady || busy || !!committedRefresh}
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
        {selectedCaseId && !selectionReady && (
          <section
            className="warning-summary"
            aria-label="Selected review status"
          >
            <p role="status">
              {selectionLoading
                ? "Loading selected example…"
                : "The selected example is not ready for changes. Reload its current review."}
            </p>
            <button
              type="button"
              disabled={
                !datasetReady || selectionLoading || busy || !!committedRefresh
              }
              onClick={() => reloadSelectedReview(renderedReadScope)}
            >
              Reload selected review
            </button>
          </section>
        )}
        {selectionNeedsReview && (
          <section
            className="warning-summary"
            aria-label="Review selected context"
          >
            <p role="status">
              The current example or label context changed. Review it before
              making another change.
            </p>
            <button
              type="button"
              disabled={!selectionReady || busy || !!committedRefresh}
              onClick={() => reviewCurrentSelection(writableSelection)}
            >
              Review current selection
            </button>
          </section>
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
              onClick={() => void refreshCommittedOutcome(committedRefresh)}
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
              void selectDataset(renderedReadScope, nextDatasetId);
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
                onClick={() => reloadExamples(renderedReadScope)}
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
                        onClick={() =>
                          selectCase(
                            writableDataset,
                            decision?.id,
                            item.record.id,
                          )
                        }
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
                  disabled={!datasetReady || busy || !!committedRefresh}
                  onClick={() => void loadMoreCases(writableDataset)}
                >
                  {busy ? "Loading…" : "Load more cases"}
                </button>
              )}
            </section>
            {decision && (
              <section aria-labelledby="label-list-heading">
                <h2 id="label-list-heading">Labels for {decision.name}</h2>
                {labelsLoading ? (
                  <p role="status" className="muted">
                    Loading labels…
                  </p>
                ) : labelsError ? (
                  <div className="warning-summary" role="region" aria-label="Labels unavailable">
                    <p role="status">{labelsError}</p>
                    <button
                      type="button"
                      disabled={!datasetReady || busy || !!committedRefresh}
                      onClick={() => reloadExamples(renderedReadScope)}
                    >
                      Reload labels
                    </button>
                  </div>
                ) : labels?.items.length ? (
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
                            onClick={() =>
                              selectCase(
                                writableDataset,
                                decision?.id,
                                item.case.id,
                              )
                            }
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
                ) : labels ? (
                  <p className="muted">
                    No labels are recorded for this decision and dataset.
                  </p>
                ) : null}
                {labelCursor && (
                  <button
                    type="button"
                    disabled={!datasetReady || busy || !!committedRefresh}
                    onClick={() =>
                      void loadMoreLabels(writableDataset, decision?.id)
                    }
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
                disabled={!caseEditable || busy || !!committedRefresh}
                onClick={() => {
                  if (!mayEditCaseStageNow(writableSelection)) return;
                  setEditCase(true);
                }}
              >
                Edit input
              </button>
              <button
                type="button"
                disabled={!caseEditable || busy || !!committedRefresh}
                onClick={() => {
                  if (mayEditCaseStageNow(writableSelection))
                    setDeleteCaseOpen(true);
                }}
              >
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
                  onChange={(answers) =>
                    patchLabelAnswers(writableSelection, answers)
                  }
                  onToggle={(optionId, checked) =>
                    toggleLabelAnswer(writableSelection, optionId, checked)
                  }
                  onSave={() =>
                    void saveLabel(
                      writableSelection,
                      currentLabel?.status === "disputed" ? "resolve" : "set",
                    )
                  }
                  saving={busy || !!committedRefresh || pendingLabel?.uncertain}
                  disabled={!labelEditable}
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
                      disabled={
                        !pendingLabelMatchesSelection ||
                        busy ||
                        !!committedRefresh
                      }
                      onClick={() => retryUnknownLabel(writableSelection)}
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
                      disabled={
                        !pendingLabelMatchesSelection ||
                        busy ||
                        !!committedRefresh
                      }
                      onClick={() =>
                        void reviewLabelConflict(writableSelection)
                      }
                    >
                      Review current label
                    </button>
                  </div>
                )}
                {currentLabel?.status === "disputed" && (
                  <button
                    disabled={
                      !labelEditable ||
                      busy ||
                      !!committedRefresh ||
                      pendingLabel?.uncertain
                    }
                    onClick={() => void saveLabel(writableSelection, "resolve")}
                  >
                    Resolve dispute with staged set
                  </button>
                )}
                {currentLabel && currentLabel.status !== "disputed" && (
                  <button
                    disabled={
                      !labelEditable ||
                      busy ||
                      !!committedRefresh ||
                      pendingLabel?.uncertain
                    }
                    onClick={() => void saveLabel(writableSelection, "dispute")}
                  >
                    Dispute label
                  </button>
                )}
                {currentLabel && (
                  <button
                    disabled={
                      !labelEditable ||
                      busy ||
                      !!committedRefresh ||
                      pendingLabel?.uncertain
                    }
                    onClick={() => void saveLabel(writableSelection, "clear")}
                  >
                    Clear label
                  </button>
                )}
                <label htmlFor="label-note">Provenance note</label>
                <input
                  id="label-note"
                  value={note}
                  disabled={
                    !labelEditable ||
                    busy ||
                    !!committedRefresh ||
                    pendingLabel?.uncertain
                  }
                  onChange={(event) => {
                    patchLabelNote(
                      writableSelection,
                      event.currentTarget.value,
                    );
                  }}
                />
                <p className="muted">A note is required to dispute a label.</p>
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
              if (
                captureRenderedSelection(writableSelection) ===
                  writableSelection &&
                !busyRef.current &&
                !committedRefreshRef.current &&
                !pendingCaseRef.current?.uncertain &&
                !mutationLockRef.current
              )
                setEditCase(false);
            }}
          >
            <div className="modal-body case-editor">
              {committedRefresh?.kind === "case" && (
                <section
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
                    onClick={() =>
                      void refreshCommittedOutcome(committedRefresh)
                    }
                  >
                    {busy ? "Refreshing saved review…" : "Refresh saved case"}
                  </button>
                </section>
              )}
              {pendingCase?.uncertain && (
                <div className="warning-summary">
                  <p>
                    The case edit outcome may be unknown. The exact request is
                    retained; retry it before closing or changing the source.
                  </p>
                  <button
                    type="button"
                    disabled={
                      !pendingCaseMatchesSelection || busy || !!committedRefresh
                    }
                    onClick={() => void saveCase(writableSelection)}
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
                    disabled={
                      !pendingCaseMatchesSelection || busy || !!committedRefresh
                    }
                    onClick={() => void reviewCaseConflict(writableSelection)}
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
                        !caseEditable ||
                        busy ||
                        !!committedRefresh ||
                        pendingCase?.uncertain
                      }
                      onChange={() => {
                        patchCaseStage(writableSelection, { inputKind: kind });
                      }}
                    />
                    {kind.toUpperCase()}
                  </label>
                ))}
              </fieldset>
              <JsonSourceEditor
                label="Input source"
                value={inputSource}
                readOnly={
                  !caseEditable ||
                  busy ||
                  !!committedRefresh ||
                  pendingCase?.uncertain
                }
                onChange={(value) => {
                  patchCaseStage(writableSelection, { inputSource: value });
                }}
              />
              <JsonSourceEditor
                label="Metadata source"
                value={metadataSource}
                readOnly={
                  !caseEditable ||
                  busy ||
                  !!committedRefresh ||
                  pendingCase?.uncertain
                }
                onChange={(value) => {
                  patchCaseStage(writableSelection, {
                    metadataSource: value,
                  });
                }}
              />
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={
                    !caseEditable ||
                    busy ||
                    !!committedRefresh ||
                    !!pendingCase?.conflict
                  }
                  onClick={() => void saveCase(writableSelection)}
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
                    !caseEditable ||
                    busy ||
                    !!committedRefresh ||
                    pendingCase?.uncertain
                  }
                  onClick={() => {
                    if (
                      captureRenderedSelection(writableSelection) ===
                        writableSelection &&
                      !busyRef.current &&
                      !committedRefreshRef.current &&
                      !pendingCaseRef.current?.uncertain &&
                      !mutationLockRef.current
                    )
                      setEditCase(false);
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          </Modal>
        )}
        {addCaseOpen && dataset && datasetReady && (
          <Modal
            title="Add example"
            onDismiss={() => {
              if (
                captureRenderedDataset(writableDataset) === writableDataset &&
                !busyRef.current &&
                !committedRefreshRef.current &&
                !pendingAddRef.current?.uncertain &&
                !mutationLockRef.current
              )
                setAddCaseOpen(false);
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
                    disabled={
                      !pendingAddMatchesDataset || busy || !!committedRefresh
                    }
                    onClick={() => void addCase(writableDataset)}
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
                    disabled={
                      !pendingAddMatchesDataset || busy || !!committedRefresh
                    }
                    onClick={() => void reviewAddConflict(writableDataset)}
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
                      disabled={
                        !datasetReady ||
                        busy ||
                        !!committedRefresh ||
                        pendingAdd?.uncertain
                      }
                      onChange={() => {
                        patchDatasetStage(writableDataset, { inputKind: kind });
                      }}
                    />
                    {kind.toUpperCase()}
                  </label>
                ))}
              </fieldset>
              <JsonSourceEditor
                label="Input source"
                value={newInputSource}
                readOnly={
                  !datasetReady ||
                  busy ||
                  !!committedRefresh ||
                  pendingAdd?.uncertain
                }
                onChange={(value) => {
                  patchDatasetStage(writableDataset, { inputSource: value });
                }}
              />
              <JsonSourceEditor
                label="Metadata source"
                value={newMetadataSource}
                readOnly={
                  !datasetReady ||
                  busy ||
                  !!committedRefresh ||
                  pendingAdd?.uncertain
                }
                onChange={(value) => {
                  patchDatasetStage(writableDataset, {
                    metadataSource: value,
                  });
                }}
              />
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={
                    !datasetReady ||
                    busy ||
                    !!committedRefresh ||
                    !!pendingAdd?.conflict
                  }
                  onClick={() => void addCase(writableDataset)}
                >
                  {busy
                    ? "Adding…"
                    : addConflictReviewed
                      ? "Reapply reviewed example"
                      : "Add example"}
                </button>
                <button
                  type="button"
                  disabled={busy || !!committedRefresh || pendingAdd?.uncertain}
                  onClick={() => {
                    if (
                      captureRenderedDataset(writableDataset) !==
                        writableDataset ||
                      pendingAddRef.current?.uncertain ||
                      busyRef.current ||
                      committedRefreshRef.current ||
                      mutationLockRef.current
                    )
                      return;
                    setAddCaseOpen(false);
                  }}
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
              if (
                captureRenderedSelection(writableSelection) ===
                  writableSelection &&
                !busyRef.current &&
                !committedRefreshRef.current &&
                !pendingRemoveRef.current?.uncertain &&
                !mutationLockRef.current
              )
                setDeleteCaseOpen(false);
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
                    disabled={
                      !pendingRemoveMatchesSelection ||
                      busy ||
                      !!committedRefresh
                    }
                    onClick={() => void removeSelectedCase(writableSelection)}
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
                    disabled={
                      !pendingRemoveMatchesSelection ||
                      busy ||
                      !!committedRefresh
                    }
                    onClick={() => void reviewRemoveConflict(writableSelection)}
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
                  disabled={
                    !caseEditable ||
                    busy ||
                    !!committedRefresh ||
                    !!pendingRemove?.conflict
                  }
                  onClick={() => void removeSelectedCase(writableSelection)}
                >
                  {busy
                    ? "Removing…"
                    : removeConflictReviewed
                      ? "Reapply reviewed removal"
                      : "Remove case"}
                </button>
                <button
                  type="button"
                  disabled={
                    busy || !!committedRefresh || pendingRemove?.uncertain
                  }
                  onClick={() => {
                    if (
                      captureRenderedSelection(writableSelection) ===
                        writableSelection &&
                      !busyRef.current &&
                      !committedRefreshRef.current &&
                      !pendingRemoveRef.current?.uncertain &&
                      !mutationLockRef.current
                    )
                      setDeleteCaseOpen(false);
                  }}
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
