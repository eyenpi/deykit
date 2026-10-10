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
  StagedOwner,
} from "./examples-admission";

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
  const [selectionNeedsReview, setSelectionNeedsReview] = useState(false);
  const [pendingLabel, setPendingLabel] = useState<{
    body: LabelMutationBody;
    scope: SelectionScope;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [pendingCase, setPendingCase] = useState<{
    body: CaseEditBody;
    scope: SelectionScope;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [pendingAdd, setPendingAdd] = useState<{
    body: AddCaseBody;
    scope: DatasetScope;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [pendingRemove, setPendingRemove] = useState<{
    body: RemoveCaseBody;
    scope: SelectionScope;
    uncertain: boolean;
    conflict: boolean;
  }>();
  const [committedRefresh, setCommittedRefresh] = useState<CommittedRefresh>();
  const committedRefreshRef = useRef<CommittedRefresh | undefined>(undefined);
  const datasetAdmissionRef = useRef<DatasetAdmission | undefined>(undefined);
  const selectionAdmissionRef = useRef<SelectionAdmission | undefined>(
    undefined,
  );
  const previousSelectionAdmissionRef = useRef<
    SelectionAdmission | undefined
  >(undefined);
  const datasetReadEpochRef = useRef(0);
  const selectionReadEpochRef = useRef(0);
  const navigationEpochRef = useRef(0);
  const caseStageOwnerRef = useRef<StagedOwner | undefined>(undefined);
  const labelStageOwnerRef = useRef<StagedOwner | undefined>(undefined);
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
    return liveSelectionRouteMatches(navigation.current, context, {
      datasetId: datasetFromRoute,
      caseId: caseFromRoute,
    });
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
  function ownsSelectionStage(owner: StagedOwner | undefined): boolean {
    const admission = currentSelectionAdmission();
    return (
      !!admission &&
      owner?.readEpoch === admission.readEpoch &&
      owner.navigationEpoch === admission.navigationEpoch
    );
  }
  function ownerFor(admission: SelectionAdmission): StagedOwner {
    return {
      readEpoch: admission.readEpoch,
      navigationEpoch: admission.navigationEpoch,
    };
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

    const datasetAdmission: DatasetAdmission = Object.freeze({
      registrationId: context.registrationId,
      datasetId: context.datasetId,
      refreshGeneration: context.refreshGeneration,
      refreshToken: context.refreshToken,
      epoch: ++datasetReadEpochRef.current,
      read: datasetRead,
    });
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
          selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
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
        if (reviewChanged) {
          setPendingLabel({
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
          setNote("");
          setEditorDirty(false);
          setPendingLabel(undefined);
          setNotice(undefined);
          labelStageOwnerRef.current = ownerFor(refreshedAdmission);
          setSelectionNeedsReview(false);
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
        setPendingCase({
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
        setEditorDirty(false);
        setEditCase(false);
        setPendingCase(undefined);
        setNotice(undefined);
        caseStageOwnerRef.current = ownerFor(refreshedAdmission);
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
        setSelectionNeedsReview(true);
        setNotice(
          "Case saved. The current label review changed; review it before making another label change.",
        );
      } else {
        labelStageOwnerRef.current = ownerFor(refreshedAdmission);
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
      datasetReadEpochRef.current += 1;
      selectionReadEpochRef.current += 1;
      datasetAdmissionRef.current = undefined;
      previousSelectionAdmissionRef.current =
        selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
      selectionAdmissionRef.current = undefined;
      setDataset(undefined);
      setCases(undefined);
      setLabels(undefined);
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
    previousSelectionAdmissionRef.current =
      selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
    datasetAdmissionRef.current = undefined;
    selectionAdmissionRef.current = undefined;
    selectionReadEpochRef.current += 1;
    setLoading(true);
    setError(undefined);
    setCases(undefined);
    setLabels(undefined);
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
      setDataset(datasetResult.data);

      const casePage = await operations.listCases({
        registrationId: capturedRegistrationId,
        datasetId: capturedDatasetId,
        query: { limit: "50" },
        signal: controller.signal,
      });
      if (!isCurrentDatasetRead()) return;
      const capturedDecisionId = decision?.id;
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
      setCases(casePage.data);
      setCaseCursor(casePage.data.next_cursor ?? undefined);
      if (
        labelPage &&
        currentReadContext.current.decisionId === capturedDecisionId &&
        navigation.current.kind === "examples" &&
        navigation.current.registrationId === capturedRegistrationId &&
        (navigation.current.datasetId ?? datasetFromRoute ?? "") ===
          capturedDatasetId &&
        (navigation.current.decisionId ?? decision?.id) === capturedDecisionId
      ) {
        setLabels(labelPage.data);
        setLabelCursor(labelPage.data.next_cursor ?? undefined);
      }
    }
    void loadExamples()
      .catch((cause: unknown) => {
        if (isCurrentDatasetRead()) setError(safeMessage(cause));
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
    if (!datasetId || !selectedCaseId) {
      selectionReadEpochRef.current += 1;
      previousSelectionAdmissionRef.current =
        selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
      selectionAdmissionRef.current = undefined;
      setSelectionLoading(false);
      setCaseRead(undefined);
      setLabelView(undefined);
      setStagedAnswers([]);
      return;
    }
    const requestedDatasetId = datasetId;
    const requestedCaseId = selectedCaseId;
    const requestedDecisionId = decision?.id;
    const datasetAdmission = currentDatasetAdmission();
    if (!datasetAdmission) return;
    if (
      !liveRouteMatchesSelection({
        registrationId,
        datasetId: requestedDatasetId,
        decisionId: requestedDecisionId,
        caseId: requestedCaseId,
      })
    )
      return;
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
        datasetAdmissionRef.current === datasetAdmission &&
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
          dataset: datasetAdmission.read,
          caseRead: caseResult.data,
          labelView: labelResult?.data,
        })
      )
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
        datasetAdmission,
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
      const caseOwner = caseStageOwnerRef.current;
      const labelOwner = labelStageOwnerRef.current;
      const caseOwnedByPrevious =
        !!previous &&
        !!caseOwner &&
        caseOwner.readEpoch === previous.readEpoch &&
        caseOwner.navigationEpoch === previous.navigationEpoch;
      const labelOwnedByPrevious =
        !!previous &&
        !!labelOwner &&
        labelOwner.readEpoch === previous.readEpoch &&
        labelOwner.navigationEpoch === previous.navigationEpoch;
      const caseStageChanged =
        !!previous &&
        caseOwnedByPrevious &&
        (inputKind !== previous.caseRead.case.record.input_kind ||
          inputSource !== previous.caseRead.case.record.input_source ||
          metadataSource !==
            (previous.caseRead.case.record.metadata_source ?? "{}"));
      const labelStageChanged =
        !!previous &&
        labelOwnedByPrevious &&
        ((note.trim().length > 0) ||
          [...stagedAnswers].sort().join("\0") !==
            [
              ...(previous.labelView?.label?.acceptable_option_ids ?? []),
            ]
              .sort()
              .join("\0"));
      const caseReviewChanged =
        previous !== undefined &&
        caseOwnedByPrevious &&
          (previous.caseRead.case.etag !== caseResult.data.case.etag ||
            previous.datasetAdmission.read.etag !==
              datasetAdmission.read.etag ||
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
        if (preserveCaseStage) caseStageOwnerRef.current = ownerFor(admission);
        if (preserveLabelStage) labelStageOwnerRef.current = ownerFor(admission);
      }
      if (!preserveCaseStage) {
        setInputKind(caseRecord.input_kind);
        setInputSource(caseRecord.input_source);
        setMetadataSource(caseRecord.metadata_source ?? "{}");
        caseStageOwnerRef.current = ownerFor(admission);
      }
      if (!preserveLabelStage) {
        setStagedAnswers(
          labelResult?.data.label?.acceptable_option_ids ?? [],
        );
        setNote("");
        labelStageOwnerRef.current = ownerFor(admission);
      }
      if (stageNeedsReview) {
        setSelectionNeedsReview(true);
        setNotice(
          "The current example or review changed while edits were staged. Review it before reapplying those edits.",
        );
      } else if (!editorDirty || !sameSelection) {
        setSelectionNeedsReview(false);
        setEditorDirty(false);
        setNotice(undefined);
      }
      setCaseRead(caseResult.data);
      setLabelView(labelResult?.data);
      setSelectionLoading(false);
    }
    void loadSelectedCase().catch((cause: unknown) => {
      if (isCurrentSelectionRead()) {
        setError(safeMessage(cause));
        setSelectionLoading(false);
      }
    });
    return () => controller.abort();
  }, [
    dataset,
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

  async function loadMoreCases() {
    const admission = captureDatasetAdmission();
    if (!admission || !caseCursor || busy) return;
    const context = currentReadContext.current;
    setBusy(true);
    try {
      const result = await operations.listCases({
        registrationId,
        datasetId,
        query: { cursor: caseCursor, limit: "50" },
      });
      if (
        !isCurrentContext(context) ||
        currentDatasetAdmission() !== admission
      )
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
      if (
        isCurrentContext(context) &&
        currentDatasetAdmission() === admission
      )
        setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function loadMoreLabels() {
    const admission = captureDatasetAdmission();
    if (!admission || !decision || !labelCursor || busy) return;
    const context = currentReadContext.current;
    setBusy(true);
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
      if (
        isCurrentContext(context) &&
        currentDatasetAdmission() === admission
      )
        setError(safeMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function selectCase(caseId: string) {
    if (caseId === selectedCaseId || !currentDatasetAdmission()) return;
    const moved = await onDatasetChange(datasetId, caseId);
    if (!moved) return;
    setSelectedCaseId(caseId);
  }

  function reviewCurrentSelection() {
    const admission = captureSelectionAdmission();
    if (!admission) return;
    const owner = ownerFor(admission);
    caseStageOwnerRef.current = owner;
    labelStageOwnerRef.current = owner;
    setSelectionNeedsReview(false);
    setNotice(
      "Current example and label review acknowledged. Your staged changes remain available to reapply deliberately.",
    );
  }

  async function saveLabel(
    action: "set" | "resolve" | "dispute" | "clear",
  ): Promise<boolean> {
    const admission = captureSelectionAdmission();
    const review = admission?.labelView;
    if (
      committedRefreshRef.current ||
      !admission ||
      !review ||
      !admission.decisionId ||
      selectionNeedsReview ||
      !ownsSelectionStage(labelStageOwnerRef.current) ||
      (stagedAnswers.length === 0 && action !== "clear" && action !== "dispute")
    )
      return false;
    if (
      pendingLabel?.uncertain &&
      !matchesSelectionScope(pendingLabel.scope, admission)
    )
      return false;
    if (pendingLabel?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const context = { ...currentReadContext.current };
    const decisionId = admission.decisionId;
    const caseId = admission.caseId;
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
        setPendingLabel({
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
        setPendingLabel({
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
      readEpoch: admission.readEpoch,
      navigationEpoch: admission.navigationEpoch,
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
    const admission = captureSelectionAdmission();
    if (
      committedRefreshRef.current ||
      !admission?.decisionId ||
      !admission.labelView
    )
      return;
    const context = currentReadContext.current;
    setBusy(true);
    setError(undefined);
    try {
      const refreshedDataset = await datasetOperations.read({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
      });
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
        return;
      const refreshedCase = await operations.readCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
      });
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
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
      labelStageOwnerRef.current = ownerFor(reviewedAdmission);
      if (caseStillCurrent) caseStageOwnerRef.current = ownerFor(reviewedAdmission);
      setPendingLabel(undefined);
      setSelectionNeedsReview(!caseStillCurrent);
      setNotice(
        caseStillCurrent
          ? undefined
          : "The case changed while reviewing its label. Review the current selection before another change.",
      );
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
    const admission = captureSelectionAdmission();
    const data = currentDatasetAdmission();
    if (
      committedRefreshRef.current ||
      !admission ||
      !data ||
      admission.datasetAdmission !== data ||
      selectionNeedsReview ||
      !ownsSelectionStage(caseStageOwnerRef.current)
    )
      return false;
    if (
      pendingCase?.uncertain &&
      !matchesSelectionScope(pendingCase.scope, admission)
    )
      return false;
    if (pendingCase?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const context = { ...currentReadContext.current };
    const caseId = admission.caseId;
    const decisionId = admission.decisionId;
    const stagedGeneration = caseEditGeneration.current;
    const inputKindAtSubmit = inputKind;
    const inputSourceAtSubmit = inputSource;
    const metadataSourceAtSubmit = metadataSource;
    const record = admission.caseRead.case.record;
    const body: CaseEditBody = pendingCase?.uncertain
      ? pendingCase.body
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
        setPendingCase({
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
        setPendingCase({
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
      readEpoch: admission.readEpoch,
      navigationEpoch: admission.navigationEpoch,
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
    const admission = captureSelectionAdmission();
    if (committedRefreshRef.current || !admission) return;
    const context = currentReadContext.current;
    setBusy(true);
    setError(undefined);
    try {
      const currentDataset = await datasetOperations.read({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
      });
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
        return;
      const currentCase = await operations.readCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
      });
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
        return;
      const currentLabel = admission.decisionId
        ? await operations.readLabel({
            registrationId: admission.registrationId,
            decisionId: admission.decisionId,
            datasetId: admission.datasetId,
            caseId: admission.caseId,
          })
        : undefined;
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
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
      caseStageOwnerRef.current = ownerFor(reviewed);
      if (labelUnchanged) labelStageOwnerRef.current = ownerFor(reviewed);
      setSelectionNeedsReview(!labelUnchanged);
      setPendingCase(undefined);
      setCaseConflictReviewed(true);
      setNotice(
        labelUnchanged
          ? "Current case and dataset versions reviewed. Your edited source is retained; reapply it deliberately."
          : "Current case and dataset versions reviewed. Review the changed label context before another label change.",
      );
    } catch (cause) {
      if (isCurrentContext(context)) setError(safeMessage(cause));
    } finally {
      if (isCurrentContext(context)) setBusy(false);
    }
  }

  async function addCase(): Promise<boolean> {
    const admission = captureDatasetAdmission();
    if (committedRefreshRef.current || !admission) return false;
    if (pendingAdd?.uncertain && !matchesDatasetScope(pendingAdd.scope, admission))
      return false;
    if (pendingAdd?.conflict) return false;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
      const body: AddCaseBody = pendingAdd?.uncertain
        ? pendingAdd.body
        : {
            schema_version: 1,
            operation_id: opId(),
            expected_dataset_etag: admission.read.etag,
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
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
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
        setPendingAdd({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
          },
          uncertain: true,
          conflict: false,
        });
      else if (cause instanceof ApiError && cause.status === 409) {
        setPendingAdd({
          body,
          scope: {
            registrationId: admission.registrationId,
            datasetId: admission.datasetId,
          },
          uncertain: false,
          conflict: true,
        });
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
    const admission = captureDatasetAdmission();
    if (committedRefreshRef.current || !admission) return;
    const context = currentReadContext.current;
    setBusy(true);
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
      const reviewedDataset: DatasetAdmission = Object.freeze({
        ...admission,
        epoch: ++datasetReadEpochRef.current,
        read: currentDataset.data,
      });
      datasetAdmissionRef.current = reviewedDataset;
      selectionReadEpochRef.current += 1;
      previousSelectionAdmissionRef.current =
        selectionAdmissionRef.current ?? previousSelectionAdmissionRef.current;
      selectionAdmissionRef.current = undefined;
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
    const admission = captureSelectionAdmission();
    const data = currentDatasetAdmission();
    if (
      committedRefreshRef.current ||
      !admission ||
      !data ||
      admission.datasetAdmission !== data ||
      selectionNeedsReview ||
      !ownsSelectionStage(labelStageOwnerRef.current)
    )
      return;
    if (
      pendingRemove?.uncertain &&
      !matchesSelectionScope(pendingRemove.scope, admission)
    )
      return;
    if (pendingRemove?.conflict) return;
    setBusy(true);
    setMutationInFlight(true);
    setError(undefined);
    const body: RemoveCaseBody = pendingRemove?.uncertain
      ? pendingRemove.body
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
        setPendingRemove({
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
        setPendingRemove({
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
      } else setPendingRemove(undefined);
      setError(safeMessage(cause));
    } finally {
      setBusy(false);
      setMutationInFlight(false);
    }
  }

  async function reviewRemoveConflict() {
    const admission = captureSelectionAdmission();
    if (committedRefreshRef.current || !admission) return;
    const context = currentReadContext.current;
    setBusy(true);
    setError(undefined);
    try {
      const currentDataset = await datasetOperations.read({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
      });
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
        return;
      const currentCase = await operations.readCase({
        registrationId: admission.registrationId,
        datasetId: admission.datasetId,
        caseId: admission.caseId,
      });
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
        return;
      const currentLabel = admission.decisionId
        ? await operations.readLabel({
            registrationId: admission.registrationId,
            decisionId: admission.decisionId,
            datasetId: admission.datasetId,
            caseId: admission.caseId,
          })
        : undefined;
      if (!isCurrentContext(context) || currentSelectionAdmission() !== admission)
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
      caseStageOwnerRef.current = ownerFor(reviewed);
      labelStageOwnerRef.current = ownerFor(reviewed);
      setSelectionNeedsReview(false);
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
  const writableDataset = captureDatasetAdmission();
  const writableSelection = captureSelectionAdmission();
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
    ownsSelectionStage(caseStageOwnerRef.current);
  const labelEditable =
    selectionReady &&
    writableSelection?.labelView !== undefined &&
    !selectionNeedsReview &&
    ownsSelectionStage(labelStageOwnerRef.current);
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
  function launchImport() {
    if (!committedRefreshRef.current && captureDatasetAdmission()) onImport();
  }
  function launchSplit() {
    if (!committedRefreshRef.current && captureDatasetAdmission()) onSplit();
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
            <button
              type="button"
              onClick={launchImport}
              disabled={!datasetReady || !!committedRefresh}
            >
              Import examples
            </button>
            <button
              type="button"
              onClick={launchSplit}
              disabled={!datasetReady || !!committedRefresh}
            >
              Split dataset
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => {
                if (
                  !committedRefreshRef.current &&
                  captureDatasetAdmission()
                )
                  setAddCaseOpen(true);
              }}
              disabled={!datasetReady || !!committedRefresh}
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
          <section className="warning-summary" aria-label="Selected review status">
            <p role="status">
              {selectionLoading
                ? "Loading selected example…"
                : "The selected example is not ready for changes. Reload its current review."}
            </p>
            <button
              type="button"
              disabled={!datasetReady || selectionLoading || !!committedRefresh}
              onClick={() => setSelectionReloadGeneration((value) => value + 1)}
            >
              Reload selected review
            </button>
          </section>
        )}
        {selectionNeedsReview && (
          <section className="warning-summary" aria-label="Review selected context">
            <p role="status">
              The current example or label context changed. Review it before making another change.
            </p>
            <button
              type="button"
              disabled={!selectionReady || busy || !!committedRefresh}
              onClick={reviewCurrentSelection}
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
                  disabled={!datasetReady || busy || !!committedRefresh}
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
                    disabled={!datasetReady || busy || !!committedRefresh}
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
                disabled={!caseEditable || busy || !!committedRefresh}
                onClick={() => {
                  if (!caseEditable) return;
                  const admission = captureSelectionAdmission();
                  if (!admission) return;
                  caseStageOwnerRef.current = ownerFor(admission);
                  setEditCase(true);
                }}
              >
                Edit input
              </button>
              <button
                type="button"
                disabled={!caseEditable || !!committedRefresh}
                onClick={() => {
                  if (!committedRefreshRef.current && caseEditable)
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
                  onChange={(answers) => {
                    if (!labelEditable) return;
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
                      disabled={
                        !pendingLabelMatchesSelection ||
                        busy ||
                        !!committedRefresh
                      }
                      onClick={() => void reviewLabelConflict()}
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
                    onClick={() => void saveLabel("resolve")}
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
                    onClick={() => void saveLabel("dispute")}
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
                    !labelEditable ||
                    busy ||
                    !!committedRefresh ||
                    pendingLabel?.uncertain
                  }
                  onChange={(event) => {
                    if (!labelEditable) return;
                    labelEditGeneration.current += 1;
                    setNote(event.target.value);
                    setEditorDirty(true);
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
              if (!busy && !committedRefresh && !pendingCase?.uncertain)
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
                    onClick={() => void refreshCommittedOutcome()}
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
                      !pendingCaseMatchesSelection ||
                      busy ||
                      !!committedRefresh
                    }
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
                    disabled={
                      !pendingCaseMatchesSelection ||
                      busy ||
                      !!committedRefresh
                    }
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
                        !caseEditable ||
                        busy ||
                        !!committedRefresh ||
                        pendingCase?.uncertain
                      }
                      onChange={() => {
                        if (!caseEditable) return;
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
                readOnly={
                  !caseEditable ||
                  busy ||
                  !!committedRefresh ||
                  pendingCase?.uncertain
                }
                onChange={(value) => {
                  if (!caseEditable) return;
                  caseEditGeneration.current += 1;
                  setInputSource(value);
                  setEditorDirty(true);
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
                  if (!caseEditable) return;
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
                    !caseEditable ||
                    busy ||
                    !!committedRefresh ||
                    !!pendingCase?.conflict
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
                    !caseEditable ||
                    busy ||
                    !!committedRefresh ||
                    pendingCase?.uncertain
                  }
                  onClick={() => setEditCase(false)}
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
              if (!busy && !committedRefresh && !pendingAdd?.uncertain)
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
                      !pendingAddMatchesDataset ||
                      busy ||
                      !!committedRefresh
                    }
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
                    disabled={
                      !pendingAddMatchesDataset ||
                      busy ||
                      !!committedRefresh
                    }
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
                      disabled={
                        !datasetReady ||
                        busy ||
                        !!committedRefresh ||
                        pendingAdd?.uncertain
                      }
                      onChange={() => {
                        if (!captureDatasetAdmission()) return;
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
                readOnly={
                  !datasetReady ||
                  busy ||
                  !!committedRefresh ||
                  pendingAdd?.uncertain
                }
                onChange={(value) => {
                  if (!captureDatasetAdmission()) return;
                  setNewInputSource(value);
                  setEditorDirty(true);
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
                  if (!captureDatasetAdmission()) return;
                  setNewMetadataSource(value);
                  setEditorDirty(true);
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
                  disabled={busy || !!committedRefresh || pendingAdd?.uncertain}
                  onClick={() => {
                    if (pendingAdd?.uncertain) return;
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
              if (!busy && !committedRefresh && !pendingRemove?.uncertain)
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
                    disabled={
                      !pendingRemoveMatchesSelection ||
                      busy ||
                      !!committedRefresh
                    }
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
                  disabled={
                    !caseEditable ||
                    busy ||
                    !!committedRefresh ||
                    !!pendingRemove?.conflict
                  }
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
                  disabled={
                    busy || !!committedRefresh || pendingRemove?.uncertain
                  }
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
