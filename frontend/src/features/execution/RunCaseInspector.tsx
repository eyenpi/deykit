import { useEffect, useRef, useState } from "react";
import { ApiError, safeMessage } from "../../api/client";
import type { ApiOperationData } from "../../api/client";
import { ErrorSummary, LoadingState } from "../../components/States";
import type { ExecutionGateway } from "../../workspace/gateway";
import type { DecisionAuthoringOperations } from "../../workspace/gateway";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { DebuggingGateway } from "../../workspace/gateway";
import type { ExampleAuthoringOperations } from "../../workspace/gateway";
import { AnnotationSheet } from "../debugging/AnnotationSheet";
import { ResultAssessmentControls } from "../debugging/ResultAssessmentControls";
import { CurrentLabelSheet } from "../debugging/CurrentLabelSheet";
import { RegressionSheet } from "../debugging/RegressionSheet";
import type { CaseDetailView, ResultRowView } from "./execution-inspection";
import {
  decodeAssessmentCounts,
  decodeCaseDetail,
  decodeResultContext,
  decodeResultRow,
  sameAssessmentCounts,
  sameResultContext,
} from "./execution-inspection";
import type {
  AssessmentCountsView,
  ResultContextView,
} from "./execution-inspection";

type Run = ApiOperationData<"readRun">;
type EvaluationPage = ApiOperationData<"listEvaluations">;
type Evaluation = ApiOperationData<"readEvaluation">;
type ResultPage = ApiOperationData<"listResults">;
type SnapshotIdentity = {
  scope: string;
  epoch: number;
  resultSnapshotId: string;
  labelSnapshotId: string;
  context: ResultContextView;
  assessmentCounts: AssessmentCountsView;
  assessmentPopulationScope: string;
};

type Reveal = {
  input: boolean;
  request: boolean;
  response: boolean;
  attempts: boolean;
};

export function RunCaseInspector({
  registrationId,
  run,
  execution,
  debugging,
  labelOperations,
  readRevision,
  navigation,
  evaluationId,
  caseId,
}: {
  registrationId: string;
  run: Run;
  execution: ExecutionGateway;
  debugging: DebuggingGateway;
  labelOperations: ExampleAuthoringOperations;
  readRevision: DecisionAuthoringOperations["revision"];
  navigation: WorkspaceNavigation;
  evaluationId?: string;
  caseId?: string;
}) {
  const [evaluations, setEvaluations] = useState<EvaluationPage>();
  const [selectedEvaluation, setSelectedEvaluation] = useState<Evaluation>();
  const [historicalDefinition, setHistoricalDefinition] =
    useState<
      Awaited<ReturnType<DecisionAuthoringOperations["revision"]>>["data"]
    >();
  const [revisionError, setRevisionError] = useState<string>();
  const [rows, setRows] = useState<readonly ResultRowView[]>([]);
  const [resultPage, setResultPage] = useState<ResultPage>();
  const [cursor, setCursor] = useState<string>();
  const [status, setStatus] = useState("");
  const [split, setSplit] = useState("");
  const [tag, setTag] = useState("");
  const [assessmentFilter, setAssessmentFilter] = useState<
    "all" | "inspect" | "incorrect" | "unlabelled"
  >("all");
  const [pageSize, setPageSize] = useState(50);
  const [detail, setDetail] = useState<CaseDetailView>();
  const [reveal, setReveal] = useState<Reveal>({
    input: false,
    request: false,
    response: false,
    attempts: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [currentLabelOpen, setCurrentLabelOpen] = useState(false);
  const [regressionOpen, setRegressionOpen] = useState(false);
  const [evaluationBusy, setEvaluationBusy] = useState(false);
  const [contextChanged, setContextChanged] = useState(false);
  const [reload, setReload] = useState(0);
  const moreController = useRef<AbortController | undefined>(undefined);
  const scopeEpoch = useRef(0);
  const lastResultSource = useRef("");
  const lastReload = useRef(reload);
  const [publishedScope, setPublishedScope] = useState("");
  const [publishedSnapshot, setPublishedSnapshot] =
    useState<SnapshotIdentity>();
  const publishedSnapshotRef = useRef(publishedSnapshot);
  publishedSnapshotRef.current = publishedSnapshot;
  const [detailScope, setDetailScope] = useState("");
  const sourceScope = `${registrationId}|${run.run_id}|${evaluationId ?? ""}`;
  const assessmentPopulationScope = `${sourceScope}|${status}|${split}|${tag}`;
  const resultScope = `${sourceScope}|${status}|${split}|${tag}|${assessmentFilter}|${pageSize}|${reload}`;
  const requestedDetailScope = `${resultScope}|${caseId ?? ""}|${reveal.input}|${reveal.request}|${reveal.response}|${reveal.attempts}`;
  const resultsCurrent =
    publishedScope === resultScope && publishedSnapshot?.scope === resultScope;
  const detailCurrent = detailScope === requestedDetailScope;
  const localScopeLocked =
    annotationOpen || currentLabelOpen || regressionOpen || evaluationBusy || contextChanged;

  function invalidateAfterContextConflict(cause: unknown) {
    if (!(cause instanceof ApiError) || cause.code !== "result_context_changed")
      return;
    setRows([]);
    setCursor(undefined);
    setDetail(undefined);
    setDetailScope("");
    setReveal({ input: false, request: false, response: false, attempts: false });
    setPublishedScope("");
    setContextChanged(true);
  }

  useEffect(() => {
    setAnnotationOpen(false);
    setCurrentLabelOpen(false);
    setRegressionOpen(false);
  }, [caseId]);

  useEffect(() => {
    const revisionId = run.sources.decision_revision_id;
    const controller = new AbortController();
    let active = true;
    setHistoricalDefinition(undefined);
    setRevisionError(undefined);
    void readRevision({
      registrationId,
      decisionId: run.decision_id,
      revisionId,
      signal: controller.signal,
    })
      .then((result) => {
        if (!active || controller.signal.aborted) return;
        const revision = result.data.revision.record;
        if (
          revision.id !== revisionId ||
          revision.decision_id !== run.decision_id
        )
          throw new Error(
            "The saved definition does not match this run's frozen revision.",
          );
        setHistoricalDefinition(result.data);
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted)
          setRevisionError(safeMessage(cause));
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [
    readRevision,
    registrationId,
    run.decision_id,
    run.sources.decision_revision_id,
  ]);

  useEffect(() => {
    const controller = new AbortController();
    moreController.current?.abort();
    moreController.current = undefined;
    let active = true;
    const sourceChanged = lastResultSource.current !== sourceScope;
    const explicitRefresh = lastReload.current !== reload;
    lastResultSource.current = sourceScope;
    lastReload.current = reload;
    const lastSnapshot = publishedSnapshotRef.current;
    const priorSnapshot = sourceChanged || explicitRefresh
      ? undefined
      : lastSnapshot?.scope.startsWith(`${sourceScope}|`)
        ? lastSnapshot
        : undefined;
    setLoading(true);
    setError(undefined);
    if (sourceChanged) {
      setSelectedEvaluation(undefined);
      setEvaluations(undefined);
      setRows([]);
      setPublishedScope("");
      setDetail(undefined);
      setReveal({
        input: false,
        request: false,
        response: false,
        attempts: false,
      });
    }
    setRows([]);
    setDetail(undefined);
    setReveal({
      input: false,
      request: false,
      response: false,
      attempts: false,
    });
    void (async () => {
      try {
        const evaluationPage = await execution.inspection.listEvaluations({
          registrationId,
          runId: run.run_id,
          query: { limit: 50 },
          signal: controller.signal,
        });
        if (!active) return;
        setEvaluations(evaluationPage.data);
        let pinned: Evaluation | undefined;
        if (evaluationId) {
          const read = await execution.inspection.readEvaluation({
            registrationId,
            evaluationId,
            signal: controller.signal,
          });
          if (!active) return;
          if (
            read.data.evaluation_id !== evaluationId ||
            read.data.run_id !== run.run_id
          )
            throw new Error(
              "The selected evaluation does not belong to this run.",
            );
          pinned = read.data;
          setSelectedEvaluation(pinned);
        }
        const result = await execution.inspection.listResults({
          registrationId,
          runId: run.run_id,
          query: {
            limit: pageSize,
            ...(pinned
              ? {
                  expected_result_snapshot_id: pinned.result_snapshot_id,
                  expected_label_snapshot_id: pinned.label_snapshot_id,
                }
              : priorSnapshot
                ? {
                    expected_result_snapshot_id:
                      priorSnapshot.resultSnapshotId,
                    expected_label_snapshot_id:
                      priorSnapshot.labelSnapshotId,
                  }
                : {}),
            ...(pinned ? { evaluation_id: pinned.evaluation_id } : {}),
            assessment_filter: assessmentFilter,
            ...(status ? { status } : {}),
            ...(split
              ? { split: split as "development" | "calibration" | "test" }
              : {}),
            ...(tag ? { tag } : {}),
          },
          signal: controller.signal,
        });
        if (!active) return;
        const context = decodeResultContext(result.data.context);
        const assessmentCounts = decodeAssessmentCounts(
          result.data.assessment_counts,
        );
        if (
          result.data.run_id !== run.run_id ||
          context.runId !== run.run_id ||
          context.resultSnapshotId !== result.data.result_snapshot_id ||
          context.labelSnapshotId !== result.data.label_snapshot_id ||
          context.evaluationId !== result.data.evaluation_id ||
          (priorSnapshot &&
            (!sameResultContext(context, priorSnapshot.context) ||
              (priorSnapshot.assessmentPopulationScope ===
                assessmentPopulationScope &&
                !sameAssessmentCounts(
                  assessmentCounts,
                  priorSnapshot.assessmentCounts,
                )))) ||
          (pinned &&
            (result.data.evaluation_id !== pinned.evaluation_id ||
              result.data.result_snapshot_id !== pinned.result_snapshot_id ||
              result.data.label_snapshot_id !== pinned.label_snapshot_id))
        )
          throw new Error(
            "The service returned results from a different frozen snapshot.",
          );
        setResultPage(result.data);
        setPublishedSnapshot({
          scope: resultScope,
          epoch:
            priorSnapshot?.resultSnapshotId === result.data.result_snapshot_id &&
            priorSnapshot.labelSnapshotId === result.data.label_snapshot_id
              ? priorSnapshot.epoch
              : ++scopeEpoch.current,
          resultSnapshotId: result.data.result_snapshot_id,
          labelSnapshotId: result.data.label_snapshot_id,
          context,
          assessmentCounts,
          assessmentPopulationScope,
        });
        setRows(result.data.items.map((item) => decodeResultRow(item.source)));
        setCursor(result.data.next_cursor ?? undefined);
        setPublishedScope(resultScope);
        setContextChanged(false);
      } catch (cause) {
        if (active && !controller.signal.aborted) {
          invalidateAfterContextConflict(cause);
          setError(safeMessage(cause));
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      controller.abort();
      moreController.current?.abort();
      moreController.current = undefined;
    };
  }, [
    execution,
    registrationId,
    run.run_id,
    evaluationId,
    assessmentFilter,
    status,
    split,
    tag,
    pageSize,
    reload,
    sourceScope,
  ]);

  useEffect(() => {
    if (
      !caseId ||
      !resultPage ||
      publishedScope !== resultScope ||
      publishedSnapshot?.scope !== resultScope
    )
      return;
    const controller = new AbortController();
    moreController.current?.abort();
    moreController.current = controller;
    let active = true;
    setDetail(undefined);
    setError(undefined);
    const flags = reveal;
    void execution.inspection
      .readResult({
        registrationId,
        runId: run.run_id,
        caseId,
        query: {
          ...(evaluationId ? { evaluation_id: evaluationId } : {}),
          expected_result_snapshot_id:
            publishedSnapshot.resultSnapshotId,
          expected_label_snapshot_id: publishedSnapshot.labelSnapshotId,
          include_input: flags.input ? "true" : "false",
          include_request: flags.request ? "true" : "false",
          include_response: flags.response ? "true" : "false",
          include_attempts: flags.attempts ? "true" : "false",
        },
        signal: controller.signal,
      })
      .then((result) => {
        if (!active) return;
        const decoded = decodeCaseDetail(result.data);
        if (
          decoded.runId !== run.run_id ||
          decoded.caseId !== caseId ||
          decoded.evaluationId !== (evaluationId ?? null) ||
          decoded.resultSnapshotId !== publishedSnapshot.resultSnapshotId ||
          decoded.labelSnapshotId !== publishedSnapshot.labelSnapshotId ||
          decoded.context.runId !== run.run_id ||
          decoded.context.resultSnapshotId !==
            publishedSnapshot.resultSnapshotId ||
          decoded.context.labelSnapshotId !==
            publishedSnapshot.labelSnapshotId ||
          !sameResultContext(decoded.context, publishedSnapshot.context) ||
          (selectedEvaluation &&
            (decoded.resultSnapshotId !==
              selectedEvaluation.result_snapshot_id ||
              decoded.labelSnapshotId !== selectedEvaluation.label_snapshot_id))
        )
          throw new Error(
            "The case detail does not match the selected frozen result.",
          );
        setDetail(decoded);
        setDetailScope(requestedDetailScope);
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted) {
          invalidateAfterContextConflict(cause);
          setError(safeMessage(cause));
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [
    execution,
    registrationId,
    run.run_id,
    evaluationId,
    caseId,
    resultPage,
    publishedSnapshot,
    reveal,
    selectedEvaluation,
    resultScope,
    requestedDetailScope,
    publishedScope,
  ]);

  async function loadMore() {
    const capturedSnapshot = publishedSnapshot;
    if (
      !cursor ||
      loading ||
      !capturedSnapshot ||
      capturedSnapshot.scope !== resultScope
    )
      return;
    const controller = new AbortController();
    moreController.current?.abort();
    moreController.current = controller;
    setLoading(true);
    setError(undefined);
    try {
      const result = await execution.inspection.listResults({
        registrationId,
        runId: run.run_id,
        query: {
          cursor,
          limit: pageSize,
          expected_result_snapshot_id: capturedSnapshot.resultSnapshotId,
          expected_label_snapshot_id: capturedSnapshot.labelSnapshotId,
          assessment_filter: assessmentFilter,
          ...(selectedEvaluation
            ? { evaluation_id: selectedEvaluation.evaluation_id }
            : {}),
          ...(status ? { status } : {}),
          ...(split
            ? { split: split as "development" | "calibration" | "test" }
            : {}),
          ...(tag ? { tag } : {}),
        },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const context = decodeResultContext(result.data.context);
      const assessmentCounts = decodeAssessmentCounts(
        result.data.assessment_counts,
      );
      if (
        result.data.run_id !== run.run_id ||
        result.data.result_snapshot_id !== capturedSnapshot.resultSnapshotId ||
        result.data.label_snapshot_id !== capturedSnapshot.labelSnapshotId ||
        context.runId !== run.run_id ||
        context.resultSnapshotId !== capturedSnapshot.resultSnapshotId ||
        context.labelSnapshotId !== capturedSnapshot.labelSnapshotId ||
        !sameResultContext(context, capturedSnapshot.context) ||
        !sameAssessmentCounts(assessmentCounts, capturedSnapshot.assessmentCounts) ||
        (selectedEvaluation &&
          (result.data.evaluation_id !== selectedEvaluation.evaluation_id ||
            result.data.result_snapshot_id !==
              selectedEvaluation.result_snapshot_id ||
            result.data.label_snapshot_id !==
              selectedEvaluation.label_snapshot_id))
      )
        throw new Error(
          "The service returned results from a different frozen snapshot.",
        );
      setRows((current) => {
        const seen = new Set(current.map((row) => row.caseId));
        return [
          ...current,
          ...result.data.items
            .map((item) => decodeResultRow(item.source))
            .filter((row) => !seen.has(row.caseId)),
        ];
      });
      setResultPage(result.data);
      setCursor(result.data.next_cursor ?? undefined);
    } catch (cause) {
      if (!controller.signal.aborted) {
        invalidateAfterContextConflict(cause);
        setError(safeMessage(cause));
      }
    } finally {
      if (moreController.current === controller) {
        moreController.current = undefined;
        setLoading(false);
      }
    }
  }

  function selectEvaluation(value: string) {
    const current = navigation.current;
    if (current.kind !== "run") return;
    void navigation.navigate({
      kind: "run",
      registrationId,
      runId: run.run_id,
      ...(value ? { evaluationId: value } : {}),
      ...(current.kind === "run" && current.returnGroup
        ? { returnGroup: current.returnGroup }
        : {}),
    });
  }

  function selectCase(nextCaseId: string | undefined) {
    const current = navigation.current;
    if (current.kind !== "run") return;
    void navigation.navigate({
      kind: "run",
      registrationId,
      runId: run.run_id,
      ...(evaluationId ? { evaluationId } : {}),
      ...(nextCaseId ? { caseId: nextCaseId } : {}),
      ...(current.kind === "run" && current.returnGroup
        ? { returnGroup: current.returnGroup }
        : {}),
    });
  }

  return (
    <section className="run-inspector" aria-label="Frozen result inspection">
      <div className="document-title-row">
        <h2>Frozen results</h2>
        <button
          type="button"
          disabled={loading || annotationOpen || currentLabelOpen || regressionOpen || evaluationBusy}
          onClick={() => setReload((value) => value + 1)}
        >
          Refresh frozen results
        </button>
      </div>
      {revisionError && <ErrorSummary message={revisionError} />}
      {historicalDefinition && (
        <section aria-label="Frozen decision definition">
          <h3>
            {
              historicalDefinition.revision.record.definition.questions[0]
                ?.instructions
            }
          </h3>
          <p>
            Saved revision {historicalDefinition.revision.record.id}; content
            hash{" "}
            <code>{historicalDefinition.revision.record.content_hash}</code>.
          </p>
          <ul>
            {historicalDefinition.revision.record.definition.questions[0]?.options.map(
              (option) => (
                <li key={option.id}>
                  {option.name} · {option.id}
                </li>
              ),
            )}
          </ul>
        </section>
      )}
      {evaluations && evaluations.items.length > 0 && (
        <label className="field">
          Evaluation snapshot
          <select
            value={evaluationId ?? ""}
            disabled={localScopeLocked}
            onChange={(event) => selectEvaluation(event.currentTarget.value)}
          >
            <option value="">Current results</option>
            {evaluations.items.map((item) => (
              <option key={item.evaluation_id} value={item.evaluation_id}>
                {item.evaluation_id} · {item.mode}
              </option>
            ))}
          </select>
        </label>
      )}
      {resultsCurrent && selectedEvaluation && (
        <p role="status">
          Pinned evaluation {selectedEvaluation.evaluation_id}; result snapshot{" "}
          {selectedEvaluation.result_snapshot_id}, label snapshot{" "}
          {selectedEvaluation.label_snapshot_id}.
        </p>
      )}
      {error && (
        <ErrorSummary
          message={error}
          retry={localScopeLocked ? undefined : () => setReload((value) => value + 1)}
        />
      )}
      {loading && <LoadingState>Refreshing frozen results…</LoadingState>}
      {resultPage && publishedSnapshot && (
        <p role="status" aria-label="Published result snapshot">
          {resultPage.filtered_count} rows in the server result set;{" "}
          {resultPage.selected_count} selected by this frozen run. Result
          snapshot {resultPage.result_snapshot_id}; label snapshot{" "}
          {resultPage.label_snapshot_id}.
        </p>
      )}
      {publishedSnapshot && (
        <section aria-label="Frozen result context">
          <h3>Frozen source context</h3>
          <p>
            Evaluation {publishedSnapshot.context.evaluationId ?? "original run"};{" "}
            mode {publishedSnapshot.context.evaluationMode}; decision{" "}
            {publishedSnapshot.context.decisionId} revision{" "}
            {publishedSnapshot.context.decisionRevisionId}; dataset{" "}
            {publishedSnapshot.context.datasetId} snapshot{" "}
            {publishedSnapshot.context.datasetSnapshotId}.
          </p>
          <p>
            Result content hash <code>{publishedSnapshot.context.resultContentHash}</code>; label content hash{" "}
            <code>{publishedSnapshot.context.labelContentHash}</code>; definition hash{" "}
            <code>{publishedSnapshot.context.decisionDefinitionHash}</code>; dataset hash{" "}
            <code>{publishedSnapshot.context.datasetContentHash}</code>; through event{" "}
            {publishedSnapshot.context.throughEventSequence}.
          </p>
          <dl aria-label="Global assessment counts">
            <dt>All</dt><dd>{publishedSnapshot.assessmentCounts.all}</dd>
            <dt>Needs inspection</dt><dd>{publishedSnapshot.assessmentCounts.inspect}</dd>
            <dt>Incorrect</dt><dd>{publishedSnapshot.assessmentCounts.incorrect}</dd>
            <dt>Unlabelled</dt><dd>{publishedSnapshot.assessmentCounts.unlabelled}</dd>
          </dl>
        </section>
      )}
      {resultPage && publishedSnapshot && (
        <ResultAssessmentControls
          registrationId={registrationId}
          runId={run.run_id}
          resultSnapshotId={resultPage.result_snapshot_id}
          labelSnapshotId={resultPage.label_snapshot_id}
          scopeIdentity={`${registrationId}|${run.run_id}|${publishedSnapshot.epoch}|${publishedSnapshot.resultSnapshotId}|${publishedSnapshot.labelSnapshotId}`}
          isCurrent={resultsCurrent}
          onBusyChange={setEvaluationBusy}
          selectedEvaluation={selectedEvaluation}
          operations={debugging.evaluations}
          navigation={navigation}
        />
      )}
      {resultsCurrent &&
        resultPage &&
        run.latest_result_snapshot_id !== null &&
        run.latest_result_snapshot_id !== resultPage.result_snapshot_id && (
          <p role="status" aria-label="Newer current result available">
            A newer current result snapshot is available:{" "}
            {run.latest_result_snapshot_id}.{" "}
            {evaluationId
              ? "The selected evaluation remains pinned."
              : "Refresh frozen results to inspect it."}
          </p>
        )}
      <div className="actions">
        <label className="field">
          Results per page
          <select
            value={pageSize}
            disabled={localScopeLocked}
            onChange={(event) => setPageSize(Number(event.currentTarget.value))}
          >
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={50}>50</option>
          </select>
        </label>
        <label className="field">
          Assessment
          <select
            value={assessmentFilter}
            disabled={localScopeLocked}
            onChange={(event) => {
              const value = event.currentTarget.value;
              if (
                value === "all" ||
                value === "inspect" ||
                value === "incorrect" ||
                value === "unlabelled"
              )
                setAssessmentFilter(value);
            }}
          >
            <option value="all">All assessments</option>
            <option value="inspect">Needs inspection</option>
            <option value="incorrect">Incorrect</option>
            <option value="unlabelled">Unlabelled</option>
          </select>
        </label>
        <label className="field">
          Status
          <select
            value={status}
            disabled={localScopeLocked}
            onChange={(event) => setStatus(event.currentTarget.value)}
          >
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="input_invalid">Input invalid</option>
            <option value="response_error">Response error</option>
            <option value="unknown">Unknown</option>
            <option value="valid">Valid</option>
          </select>
        </label>
        <label className="field">
          Split
          <select
            value={split}
            disabled={localScopeLocked}
            onChange={(event) => setSplit(event.currentTarget.value)}
          >
            <option value="">All splits</option>
            <option value="development">Development</option>
            <option value="calibration">Calibration</option>
            <option value="test">Test</option>
          </select>
        </label>
        <label className="field">
          Tag{" "}
          <input
            value={tag}
            disabled={localScopeLocked}
            onChange={(event) => setTag(event.currentTarget.value)}
          />
        </label>
      </div>
      {resultsCurrent && rows.length > 0 && (
        <div className="table-region">
          <table>
            <caption>Frozen result rows</caption>
            <thead>
              <tr>
                <th>Case</th>
                <th>Split / tags</th>
                <th>Status</th>
                <th>Answer</th>
                <th>Expectation</th>
                <th>Annotation count</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.caseId}>
                  <td>
                    <button
                      type="button"
                      className="text-button"
                      disabled={localScopeLocked}
                      onClick={() => selectCase(row.caseId)}
                    >
                      {row.caseId}
                    </button>
                  </td>
                  <td>
                    {row.split} · {row.tags.join(", ") || "No tags"}
                  </td>
                  <td>{row.status}</td>
                  <td>
                    {row.answerOptionId
                      ? `${historicalDefinition?.revision.record.definition.questions[0]?.options.find((option) => option.id === row.answerOptionId)?.name ?? "Unavailable"} · ${row.answerOptionId}`
                      : "Unavailable"}
                  </td>
                  <td>
                    {row.expectedOptionIds.join(", ") ||
                      row.exclusionReasons.join(", ") ||
                      "No expectation"}
                    ;{" "}
                    {row.setCorrect === null
                      ? "not assessed"
                      : row.setCorrect
                        ? "correct"
                        : "incorrect"}
                  </td>
                  <td>{row.annotationCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {resultsCurrent && cursor && (
        <button
          type="button"
          disabled={loading || annotationOpen || currentLabelOpen || evaluationBusy}
          onClick={() => void loadMore()}
        >
          Load more results
        </button>
      )}
      {caseId && (
        <section
          className="case-inspector"
          aria-label={`Case ${caseId} inspection`}
        >
          <div className="document-title-row">
            <h3>{caseId}</h3>
            <button type="button" disabled={localScopeLocked} onClick={() => selectCase(undefined)}>
              Close inspection
            </button>
          </div>
          {detailCurrent && detail && (
            <>
              <button
                type="button"
                onClick={() => setAnnotationOpen(true)}
              >
                Add annotation
              </button>
              {historicalDefinition && detail.questionId && (
                <button
                  type="button"
                  onClick={() => setCurrentLabelOpen(true)}
                >
                  Review current label
                </button>
              )}
              {detail.status === "valid" && historicalDefinition && detail.questionId && (
                <button type="button" onClick={() => setRegressionOpen(true)}>
                  Add regression example
                </button>
              )}
              <dl>
                <dt>Answer</dt>
                <dd>{detail.answer?.option_id ?? "Unavailable"}</dd>
                <dt>Question</dt>
                <dd>
                  {detail.answer?.question_id ??
                    detail.questionId ??
                    "Unavailable"}
                </dd>
                <dt>Reported model</dt>
                <dd>{detail.answer?.reported_model ?? "Not reported"}</dd>
                <dt>Expected options</dt>
                <dd>{detail.expectedOptionIds.join(", ") || "None"}</dd>
                <dt>Assessment</dt>
                <dd>
                  {detail.setCorrect === null
                    ? "Not assessed"
                    : detail.setCorrect
                      ? "Correct"
                      : "Incorrect"}{" "}
                  · {detail.exclusionReasons.join(", ") || "No exclusion"}
                </dd>
                <dt>Label provenance</dt>
                <dd>{detail.labelProvenance ?? "Unavailable"}</dd>
                <dt>Frozen case input hash</dt>
                <dd><code>{detail.caseInputHash}</code></dd>
              </dl>
              <section aria-label="Reported probabilities">
                <h4>Reported probabilities</h4>
                {detail.probabilities.length > 0 ? (
                  <ul>
                    {detail.probabilities.map((item) => (
                      <li key={item.optionId}>
                        {item.optionName} · {item.optionId}: {item.probability}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>
                    Unavailable: {detail.probabilitiesUnavailableReason ?? "No probability data was recorded."}
                  </p>
                )}
              </section>
              {detail.annotations.length > 0 && (
                <section>
                  <h4>Annotations</h4>
                  <ul>
                    {detail.annotations.map((item) => (
                      <li key={item.id}>
                        {item.createdAt}: {item.note}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
          {annotationOpen && detailCurrent && detail && (
            <AnnotationSheet
              key={`${registrationId}:${run.run_id}:${caseId}`}
              registrationId={registrationId}
              runId={run.run_id}
              caseId={caseId}
              operations={debugging.annotations}
              navigation={navigation}
              onClose={() => setAnnotationOpen(false)}
            />
          )}
          {currentLabelOpen &&
            detailCurrent &&
            detail &&
            detail.questionId &&
            historicalDefinition && (
              <CurrentLabelSheet
                key={`${registrationId}:${run.run_id}:${detail.context.decisionId}:${detail.context.datasetId}:${caseId}:${detail.caseInputHash}`}
                registrationId={registrationId}
                decisionId={detail.context.decisionId}
                datasetId={detail.context.datasetId}
                caseId={caseId}
                frozenInputHash={detail.caseInputHash}
                frozenQuestionId={detail.questionId}
                frozenOptionIds={
                  historicalDefinition.revision.record.definition.questions
                    .find((question) => question.id === detail.questionId)
                    ?.options.map((option) => option.id) ?? []
                }
                frozenExpectedOptionIds={detail.expectedOptionIds}
                operations={labelOperations}
                navigation={navigation}
                onClose={() => setCurrentLabelOpen(false)}
              />
            )}
          {regressionOpen && detailCurrent && detail && detail.status === "valid" && (
            <RegressionSheet
              key={`${registrationId}:${run.run_id}:${detail.caseId}:${detail.resultSnapshotId}`}
              registrationId={registrationId}
              decisionId={detail.context.decisionId}
              decisionName={detail.context.decisionId}
              runId={run.run_id}
              caseId={detail.caseId}
              resultSnapshotId={detail.resultSnapshotId}
              options={historicalDefinition?.revision.record.definition.questions.find((question) => question.id === detail.questionId)?.options ?? []}
              operations={debugging.regressions}
              navigation={navigation}
              onClose={() => setRegressionOpen(false)}
            />
          )}
          <fieldset>
            <legend>Reveal frozen evidence explicitly</legend>
            {(["input", "request", "response", "attempts"] as const).map(
              (key) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={reveal[key]}
                    disabled={localScopeLocked}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked;
                      setReveal((current) => ({ ...current, [key]: checked }));
                      if (!checked) setDetail(undefined);
                    }}
                  />
                  Include {key}
                </label>
              ),
            )}
          </fieldset>
          {(!detailCurrent || !detail) && (
            <LoadingState>Loading selected case…</LoadingState>
          )}
          {detailCurrent &&
            detail?.inputSource !== null &&
            detail?.inputSource !== undefined && (
              <section>
                <h4>Sanitized saved input</h4>
                <pre className="source-editor">{detail.inputSource}</pre>
              </section>
            )}
          {detailCurrent &&
            detail?.attempts.map((attempt) => (
              <section key={attempt.attemptId}>
                <h4>
                  Attempt {attempt.number} · {attempt.kind} · {attempt.state}
                </h4>
                <p>
                  Request body hash <code>{attempt.requestBodyHash}</code>;{" "}
                  {attempt.errorCode ?? "No error code"}{" "}
                  {attempt.errorReason ?? ""}
                </p>
                {attempt.requestBodySource !== null && (
                  <>
                    <h5>Sanitized request</h5>
                    <pre className="source-editor">
                      {attempt.requestBodySource}
                    </pre>
                  </>
                )}
                {attempt.responseSource !== null && (
                  <>
                    <h5>Sanitized response</h5>
                    <pre className="source-editor">
                      {attempt.responseSource}
                    </pre>
                  </>
                )}
              </section>
            ))}
        </section>
      )}
    </section>
  );
}
