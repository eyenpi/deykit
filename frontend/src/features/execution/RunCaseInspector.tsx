import { useEffect, useRef, useState } from "react";
import { safeMessage } from "../../api/client";
import type { ApiOperationData } from "../../api/client";
import { ErrorSummary, LoadingState } from "../../components/States";
import type { ExecutionGateway } from "../../workspace/gateway";
import type { DecisionAuthoringOperations } from "../../workspace/gateway";
import type { WorkspaceNavigation } from "../../workspace/navigation";
import type { CaseDetailView, ResultRowView } from "./execution-inspection";
import { decodeCaseDetail, decodeResultRow } from "./execution-inspection";

type Run = ApiOperationData<"readRun">;
type EvaluationPage = ApiOperationData<"listEvaluations">;
type Evaluation = ApiOperationData<"readEvaluation">;
type ResultPage = ApiOperationData<"listResults">;

type Reveal = { input: boolean; request: boolean; response: boolean; attempts: boolean };

export function RunCaseInspector({
  registrationId,
  run,
  execution,
  readRevision,
  navigation,
  evaluationId,
  caseId,
}: {
  registrationId: string;
  run: Run;
  execution: ExecutionGateway;
  readRevision: DecisionAuthoringOperations["revision"];
  navigation: WorkspaceNavigation;
  evaluationId?: string;
  caseId?: string;
}) {
  const [evaluations, setEvaluations] = useState<EvaluationPage>();
  const [selectedEvaluation, setSelectedEvaluation] = useState<Evaluation>();
  const [historicalDefinition, setHistoricalDefinition] = useState<Awaited<ReturnType<DecisionAuthoringOperations["revision"]>>["data"]>();
  const [revisionError, setRevisionError] = useState<string>();
  const [rows, setRows] = useState<readonly ResultRowView[]>([]);
  const [resultPage, setResultPage] = useState<ResultPage>();
  const [cursor, setCursor] = useState<string>();
  const [status, setStatus] = useState("");
  const [split, setSplit] = useState("");
  const [tag, setTag] = useState("");
  const [detail, setDetail] = useState<CaseDetailView>();
  const [reveal, setReveal] = useState<Reveal>({ input: false, request: false, response: false, attempts: false });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [reload, setReload] = useState(0);
  const moreController = useRef<AbortController | undefined>(undefined);
  const [publishedScope, setPublishedScope] = useState("");
  const [detailScope, setDetailScope] = useState("");
  const resultScope = `${registrationId}|${run.run_id}|${evaluationId ?? ""}|${status}|${split}|${tag}|${reload}`;
  const requestedDetailScope = `${resultScope}|${caseId ?? ""}|${reveal.input}|${reveal.request}|${reveal.response}|${reveal.attempts}`;
  const resultsCurrent = publishedScope === resultScope;
  const detailCurrent = detailScope === requestedDetailScope;

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
    }).then((result) => {
      if (!active || controller.signal.aborted) return;
      const revision = result.data.revision.record;
      if (revision.id !== revisionId || revision.decision_id !== run.decision_id)
        throw new Error("The saved definition does not match this run's frozen revision.");
      setHistoricalDefinition(result.data);
    }).catch((cause: unknown) => {
      if (active && !controller.signal.aborted) setRevisionError(safeMessage(cause));
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [readRevision, registrationId, run.decision_id, run.sources.decision_revision_id]);

  useEffect(() => {
    const controller = new AbortController();
    moreController.current?.abort();
    moreController.current = undefined;
    let active = true;
    setLoading(true);
    setError(undefined);
    setSelectedEvaluation(undefined);
    setEvaluations(undefined);
    setRows([]);
    setResultPage(undefined);
    setDetail(undefined);
    setReveal({ input: false, request: false, response: false, attempts: false });
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
            throw new Error("The selected evaluation does not belong to this run.");
          pinned = read.data;
          setSelectedEvaluation(pinned);
        }
        const result = await execution.inspection.listResults({
          registrationId,
          runId: run.run_id,
          query: {
            limit: 50,
            ...(pinned ? { evaluation_id: pinned.evaluation_id } : {}),
            ...(status ? { status } : {}),
            ...(split ? { split: split as "development" | "calibration" | "test" } : {}),
            ...(tag ? { tag } : {}),
          },
          signal: controller.signal,
        });
        if (!active) return;
        if (
          result.data.run_id !== run.run_id ||
          (pinned &&
            (result.data.evaluation_id !== pinned.evaluation_id ||
              result.data.result_snapshot_id !== pinned.result_snapshot_id ||
              result.data.label_snapshot_id !== pinned.label_snapshot_id))
        )
          throw new Error("The service returned results from a different frozen snapshot.");
        setResultPage(result.data);
        setRows(result.data.items.map((item) => decodeResultRow(item.source)));
        setCursor(result.data.next_cursor ?? undefined);
        setPublishedScope(resultScope);
      } catch (cause) {
        if (active && !controller.signal.aborted) setError(safeMessage(cause));
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
  }, [execution, registrationId, run.run_id, evaluationId, status, split, tag, reload]);

  useEffect(() => {
    if (!caseId || !resultPage || publishedScope !== resultScope) return;
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
          evaluation_id: evaluationId ?? null,
          include_input: flags.input ? "true" : "false",
          include_request: flags.request ? "true" : "false",
          include_response: flags.response ? "true" : "false",
          include_attempts: flags.attempts ? "true" : "false",
        },
        signal: controller.signal,
      })
      .then((result) => {
        if (!active) return;
        const decoded = decodeCaseDetail(result.data.source);
        if (
          decoded.runId !== run.run_id ||
          decoded.caseId !== caseId ||
          decoded.evaluationId !== (evaluationId ?? null) ||
          decoded.resultSnapshotId !== resultPage.result_snapshot_id ||
          decoded.labelSnapshotId !== resultPage.label_snapshot_id ||
          (selectedEvaluation &&
            (decoded.resultSnapshotId !== selectedEvaluation.result_snapshot_id ||
              decoded.labelSnapshotId !== selectedEvaluation.label_snapshot_id))
        )
          throw new Error("The case detail does not match the selected frozen result.");
        setDetail(decoded);
        setDetailScope(requestedDetailScope);
      })
      .catch((cause: unknown) => {
        if (active && !controller.signal.aborted) setError(safeMessage(cause));
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [execution, registrationId, run.run_id, evaluationId, caseId, resultPage, reveal, selectedEvaluation, resultScope, requestedDetailScope, publishedScope]);

  async function loadMore() {
    if (!cursor || loading) return;
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
          limit: 50,
          ...(selectedEvaluation ? { evaluation_id: selectedEvaluation.evaluation_id } : {}),
          ...(status ? { status } : {}),
          ...(split ? { split: split as "development" | "calibration" | "test" } : {}),
          ...(tag ? { tag } : {}),
        },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (
        result.data.run_id !== run.run_id ||
        (selectedEvaluation &&
          (result.data.evaluation_id !== selectedEvaluation.evaluation_id ||
            result.data.result_snapshot_id !== selectedEvaluation.result_snapshot_id ||
            result.data.label_snapshot_id !== selectedEvaluation.label_snapshot_id))
      )
        throw new Error("The service returned results from a different frozen snapshot.");
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
      if (!controller.signal.aborted) setError(safeMessage(cause));
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
    });
  }

  return (
    <section className="run-inspector" aria-label="Frozen result inspection">
      <h2>Frozen results</h2>
      {revisionError && <ErrorSummary message={revisionError} />}
      {historicalDefinition && <section aria-label="Frozen decision definition">
        <h3>{historicalDefinition.revision.record.definition.questions[0]?.instructions}</h3>
        <p>Saved revision {historicalDefinition.revision.record.id}; content hash <code>{historicalDefinition.revision.record.content_hash}</code>.</p>
        <ul>{historicalDefinition.revision.record.definition.questions[0]?.options.map((option) => <li key={option.id}>{option.name} · {option.id}</li>)}</ul>
      </section>}
      {evaluations && evaluations.items.length > 0 && (
        <label className="field">
          Evaluation snapshot
          <select value={evaluationId ?? ""} onChange={(event) => selectEvaluation(event.currentTarget.value)}>
            <option value="">Current results</option>
            {evaluations.items.map((item) => <option key={item.evaluation_id} value={item.evaluation_id}>{item.evaluation_id} · {item.mode}</option>)}
          </select>
        </label>
      )}
      {resultsCurrent && selectedEvaluation && <p role="status">Pinned evaluation {selectedEvaluation.evaluation_id}; result snapshot {selectedEvaluation.result_snapshot_id}, label snapshot {selectedEvaluation.label_snapshot_id}.</p>}
      {error && <ErrorSummary message={error} retry={() => setReload((value) => value + 1)} />}
      {loading && <LoadingState>Refreshing frozen results…</LoadingState>}
      {resultsCurrent && resultPage && <p role="status">{resultPage.filtered_count} rows in the server result set; {resultPage.selected_count} selected by this frozen run.</p>}
      <div className="actions">
        <label className="field">Status
          <select value={status} onChange={(event) => setStatus(event.currentTarget.value)}>
            <option value="">All</option><option value="pending">Pending</option><option value="input_invalid">Input invalid</option><option value="response_error">Response error</option><option value="unknown">Unknown</option><option value="valid">Valid</option>
          </select>
        </label>
        <label className="field">Split
          <select value={split} onChange={(event) => setSplit(event.currentTarget.value)}>
            <option value="">All splits</option><option value="development">Development</option><option value="calibration">Calibration</option><option value="test">Test</option>
          </select>
        </label>
        <label className="field">Tag <input value={tag} onChange={(event) => setTag(event.currentTarget.value)} /></label>
      </div>
      {resultsCurrent && rows.length > 0 && (
        <div className="table-region">
          <table>
            <caption>Frozen result rows</caption>
            <thead><tr><th>Case</th><th>Split / tags</th><th>Status</th><th>Answer</th><th>Expectation</th><th>Annotation count</th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.caseId}>
              <td><button type="button" className="text-button" onClick={() => selectCase(row.caseId)}>{row.caseId}</button></td>
              <td>{row.split} · {row.tags.join(", ") || "No tags"}</td>
              <td>{row.status}</td>
              <td>{row.answerOptionId ? `${historicalDefinition?.revision.record.definition.questions[0]?.options.find((option) => option.id === row.answerOptionId)?.name ?? "Unavailable"} · ${row.answerOptionId}` : "Unavailable"}</td>
              <td>{row.expectedOptionIds.join(", ") || row.exclusionReasons.join(", ") || "No expectation"}; {row.setCorrect === null ? "not assessed" : row.setCorrect ? "correct" : "incorrect"}</td>
              <td>{row.annotationCount}</td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
      {resultsCurrent && cursor && <button type="button" disabled={loading} onClick={() => void loadMore()}>Load more results</button>}
      {caseId && (
        <section className="case-inspector" aria-label={`Case ${caseId} inspection`}>
          <div className="document-title-row"><h3>{caseId}</h3><button type="button" onClick={() => selectCase(undefined)}>Close inspection</button></div>
          {detailCurrent && detail && <>
            <dl>
              <dt>Answer</dt><dd>{detail.answer?.option_id ?? "Unavailable"}</dd>
              <dt>Question</dt><dd>{detail.answer?.question_id ?? detail.questionId ?? "Unavailable"}</dd>
              <dt>Reported model</dt><dd>{detail.answer?.reported_model ?? "Not reported"}</dd>
              <dt>Expected options</dt><dd>{detail.expectedOptionIds.join(", ") || "None"}</dd>
              <dt>Assessment</dt><dd>{detail.setCorrect === null ? "Not assessed" : detail.setCorrect ? "Correct" : "Incorrect"} · {detail.exclusionReasons.join(", ") || "No exclusion"}</dd>
              <dt>Label provenance</dt><dd>{detail.labelProvenance ?? "Unavailable"}</dd>
            </dl>
            {detail.annotations.length > 0 && <section><h4>Annotations</h4><ul>{detail.annotations.map((item) => <li key={item.id}>{item.createdAt}: {item.note}</li>)}</ul></section>}
          </>}
          <fieldset>
            <legend>Reveal frozen evidence explicitly</legend>
            {(["input", "request", "response", "attempts"] as const).map((key) => (
              <label key={key}>
                <input type="checkbox" checked={reveal[key]} onChange={(event) => {
                  setReveal((current) => ({ ...current, [key]: event.currentTarget.checked }));
                  if (!event.currentTarget.checked) setDetail(undefined);
                }} />
                Include {key}
              </label>
            ))}
          </fieldset>
          {(!detailCurrent || !detail) && <LoadingState>Loading selected case…</LoadingState>}
          {detailCurrent && detail?.inputSource !== null && detail?.inputSource !== undefined && <section><h4>Sanitized saved input</h4><pre className="source-editor">{detail.inputSource}</pre></section>}
          {detailCurrent && detail?.attempts.map((attempt) => <section key={attempt.attemptId}>
            <h4>Attempt {attempt.number} · {attempt.kind} · {attempt.state}</h4>
            <p>Request body hash <code>{attempt.requestBodyHash}</code>; {attempt.errorCode ?? "No error code"} {attempt.errorReason ?? ""}</p>
            {attempt.requestBodySource !== null && <><h5>Sanitized request</h5><pre className="source-editor">{attempt.requestBodySource}</pre></>}
            {attempt.responseSource !== null && <><h5>Sanitized response</h5><pre className="source-editor">{attempt.responseSource}</pre></>}
          </section>)}
        </section>
      )}
    </section>
  );
}
