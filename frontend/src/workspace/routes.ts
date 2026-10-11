/** Stable, non-sensitive routes for the local workspace. User source never belongs here. */
export type WorkspaceRoute =
  | { kind: "start" }
  | { kind: "overview"; registrationId: string }
  | { kind: "runs"; registrationId: string }
  | {
      kind: "run";
      registrationId: string;
      runId: string;
      evaluationId?: string;
      caseId?: string;
      returnGroup?: { kind: "diagnostic" | "check"; groupId: string };
    }
  | { kind: "decision"; registrationId: string; decisionId: string }
  | {
      kind: "decision-history";
      registrationId: string;
      decisionId: string;
    }
  | {
      kind: "examples";
      registrationId: string;
      decisionId: string | null;
      datasetId?: string;
      caseId?: string;
    }
  | { kind: "providers"; registrationId: string }
  | { kind: "fixtures"; registrationId: string }
  | { kind: "comparisons"; registrationId: string }
  | {
      kind: "comparison";
      registrationId: string;
      comparisonId: string;
    }
  | { kind: "regressions"; registrationId: string; decisionId: string }
  | { kind: "reports"; registrationId: string }
  | { kind: "report"; registrationId: string; reportId: string }
  | {
      kind: "diagnostic";
      registrationId: string;
      groupId: string;
      snapshotId?: string;
    }
  | {
      kind: "check";
      registrationId: string;
      groupId: string;
      snapshotId?: string;
    };

const RESOURCE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const EXAMPLE_QUERY_KEYS = new Set(["dataset", "case"]);
const RUN_QUERY_KEYS = new Set([
  "evaluation",
  "case",
  "group_kind",
  "group_id",
]);

function validId(value: string | null | undefined): value is string {
  return value !== null && value !== undefined && RESOURCE_ID.test(value);
}

export function isValidWorkspaceRoute(route: WorkspaceRoute): boolean {
  switch (route.kind) {
    case "start":
      return true;
    case "overview":
    case "runs":
    case "providers":
    case "fixtures":
    case "comparisons":
    case "reports":
      return validId(route.registrationId);
    case "comparison":
      return validId(route.registrationId) && validId(route.comparisonId);
    case "regressions":
      return validId(route.registrationId) && validId(route.decisionId);
    case "report":
      return validId(route.registrationId) && validId(route.reportId);
    case "diagnostic":
    case "check":
      return (
        validId(route.registrationId) &&
        validId(route.groupId) &&
        (route.snapshotId === undefined || validId(route.snapshotId))
      );
    case "decision":
    case "decision-history":
      return validId(route.registrationId) && validId(route.decisionId);
    case "examples":
      return (
        validId(route.registrationId) &&
        (route.decisionId === null || validId(route.decisionId)) &&
        (route.datasetId === undefined || validId(route.datasetId)) &&
        (route.caseId === undefined || validId(route.caseId)) &&
        (route.caseId === undefined || route.datasetId !== undefined)
      );
    case "run":
      return (
        validId(route.registrationId) &&
        validId(route.runId) &&
        (route.evaluationId === undefined || validId(route.evaluationId)) &&
        (route.caseId === undefined || validId(route.caseId)) &&
        (route.returnGroup === undefined ||
          ((route.returnGroup.kind === "diagnostic" ||
            route.returnGroup.kind === "check") &&
            validId(route.returnGroup.groupId)))
      );
  }
}

export function routeToHash(route: WorkspaceRoute): string {
  if (!isValidWorkspaceRoute(route)) {
    throw new TypeError("Workspace route contains an invalid resource ID.");
  }
  switch (route.kind) {
    case "start":
      return "#/";
    case "overview":
      return `#/p/${route.registrationId}`;
    case "runs":
      return `#/p/${route.registrationId}/runs`;
    case "run": {
      const query = new URLSearchParams();
      if (route.evaluationId) query.set("evaluation", route.evaluationId);
      if (route.caseId) query.set("case", route.caseId);
      if (route.returnGroup) {
        query.set("group_kind", route.returnGroup.kind);
        query.set("group_id", route.returnGroup.groupId);
      }
      const encoded = query.toString();
      return `#/p/${route.registrationId}/runs/${route.runId}${encoded ? `?${encoded}` : ""}`;
    }
    case "decision":
      return `#/p/${route.registrationId}/d/${route.decisionId}`;
    case "decision-history":
      return `#/p/${route.registrationId}/d/${route.decisionId}/history`;
    case "providers":
      return `#/p/${route.registrationId}/providers`;
    case "fixtures":
      return `#/p/${route.registrationId}/fixtures`;
    case "comparisons":
      return `#/p/${route.registrationId}/comparisons`;
    case "comparison":
      return `#/p/${route.registrationId}/comparisons/${route.comparisonId}`;
    case "regressions":
      return `#/p/${route.registrationId}/d/${route.decisionId}/regressions`;
    case "reports":
      return `#/p/${route.registrationId}/reports`;
    case "report":
      return `#/p/${route.registrationId}/reports/${route.reportId}`;
    case "diagnostic":
    case "check":
      return `#/p/${route.registrationId}/${route.kind === "diagnostic" ? "diagnostics" : "checks"}/${route.groupId}${route.snapshotId ? `/snapshots/${route.snapshotId}` : ""}`;
    case "examples": {
      const base = route.decisionId
        ? `#/p/${route.registrationId}/d/${route.decisionId}/examples`
        : `#/p/${route.registrationId}/examples`;
      const query = new URLSearchParams();
      if (route.datasetId) query.set("dataset", route.datasetId);
      if (route.caseId) query.set("case", route.caseId);
      const encoded = query.toString();
      return encoded ? `${base}?${encoded}` : base;
    }
  }
}

/** Returns null for unknown paths, IDs, duplicated keys, or undeclared query data. */
export function routeFromHash(hash: string): WorkspaceRoute | null {
  if (!hash.startsWith("#/")) return null;
  const separator = hash.indexOf("?");
  const path = separator < 0 ? hash.slice(1) : hash.slice(1, separator);
  const queryText = separator < 0 ? "" : hash.slice(separator + 1);
  let segments: string[];
  try {
    segments = path
      .split("/")
      .filter(Boolean)
      .map((segment) => decodeURIComponent(segment));
  } catch {
    return null;
  }
  const query = new URLSearchParams(queryText);
  const keys = [...query.keys()];
  if (new Set(keys).size !== keys.length) return null;

  let route: WorkspaceRoute | null = null;
  if (segments.length === 0) {
    if (keys.length === 0) route = { kind: "start" };
  } else if (segments[0] === "p" && validId(segments[1])) {
    const registrationId = segments[1];
    if (segments.length === 3 && segments[2] === "runs") {
      if (keys.length === 0) route = { kind: "runs", registrationId };
    } else if (
      segments.length === 4 &&
      segments[2] === "runs" &&
      validId(segments[3])
    ) {
      if (keys.some((key) => !RUN_QUERY_KEYS.has(key))) return null;
      const evaluationId = query.get("evaluation") ?? undefined;
      const runCaseId = query.get("case") ?? undefined;
      const groupKind = query.get("group_kind");
      const groupId = query.get("group_id");
      if (
        (evaluationId !== undefined && !validId(evaluationId)) ||
        (runCaseId !== undefined && !validId(runCaseId)) ||
        ((groupKind === null) !== (groupId === null)) ||
        (groupKind !== null && groupKind !== "diagnostic" && groupKind !== "check") ||
        (groupId !== null && !validId(groupId))
      )
        return null;
      route = {
        kind: "run",
        registrationId,
        runId: segments[3],
        ...(evaluationId ? { evaluationId } : {}),
        ...(runCaseId ? { caseId: runCaseId } : {}),
        ...(groupKind && groupId
          ? { returnGroup: { kind: groupKind, groupId } }
          : {}),
      };
    } else if (segments.length === 2 && keys.length === 0) {
      route = { kind: "overview", registrationId };
    } else if (
      segments[2] === "providers" &&
      segments.length === 3 &&
      keys.length === 0
    ) {
      route = { kind: "providers", registrationId };
    } else if (
      segments[2] === "fixtures" &&
      segments.length === 3 &&
      keys.length === 0
    ) {
      route = { kind: "fixtures", registrationId };
    } else if (
      segments[2] === "comparisons" &&
      segments.length === 3 &&
      keys.length === 0
    ) {
      route = { kind: "comparisons", registrationId };
    } else if (
      segments[2] === "comparisons" &&
      segments.length === 4 &&
      validId(segments[3]) &&
      keys.length === 0
    ) {
      route = {
        kind: "comparison",
        registrationId,
        comparisonId: segments[3],
      };
    } else if (
      segments[2] === "reports" &&
      segments.length === 3 &&
      keys.length === 0
    ) {
      route = { kind: "reports", registrationId };
    } else if (
      segments[2] === "reports" &&
      segments.length === 4 &&
      validId(segments[3]) &&
      keys.length === 0
    ) {
      route = { kind: "report", registrationId, reportId: segments[3] };
    } else if (
      (segments[2] === "diagnostics" || segments[2] === "checks") &&
      segments.length === 4 &&
      validId(segments[3]) &&
      keys.length === 0
    ) {
      route = {
        kind: segments[2] === "diagnostics" ? "diagnostic" : "check",
        registrationId,
        groupId: segments[3],
      };
    } else if (
      (segments[2] === "diagnostics" || segments[2] === "checks") &&
      segments.length === 6 &&
      validId(segments[3]) &&
      segments[4] === "snapshots" &&
      validId(segments[5]) &&
      keys.length === 0
    ) {
      route = {
        kind: segments[2] === "diagnostics" ? "diagnostic" : "check",
        registrationId,
        groupId: segments[3],
        snapshotId: segments[5],
      };
    } else if (segments[2] === "examples" && segments.length === 3) {
      if (keys.some((key) => !EXAMPLE_QUERY_KEYS.has(key))) return null;
      const datasetId = query.get("dataset") ?? undefined;
      const caseId = query.get("case") ?? undefined;
      if (
        (datasetId !== undefined && !validId(datasetId)) ||
        (caseId !== undefined && !validId(caseId))
      )
        return null;
      route = {
        kind: "examples",
        registrationId,
        decisionId: null,
        ...(datasetId ? { datasetId } : {}),
        ...(caseId ? { caseId } : {}),
      };
    } else if (segments[2] === "d" && validId(segments[3])) {
      const decisionId = segments[3];
      if (segments.length === 4 && keys.length === 0) {
        route = { kind: "decision", registrationId, decisionId };
      } else if (
        segments[4] === "history" &&
        segments.length === 5 &&
        keys.length === 0
      ) {
        route = { kind: "decision-history", registrationId, decisionId };
      } else if (
        segments[4] === "regressions" &&
        segments.length === 5 &&
        keys.length === 0
      ) {
        route = { kind: "regressions", registrationId, decisionId };
      } else if (segments[4] === "examples" && segments.length === 5) {
        if (keys.some((key) => !EXAMPLE_QUERY_KEYS.has(key))) return null;
        const datasetId = query.get("dataset") ?? undefined;
        const caseId = query.get("case") ?? undefined;
        if (
          (datasetId !== undefined && !validId(datasetId)) ||
          (caseId !== undefined && !validId(caseId))
        )
          return null;
        route = {
          kind: "examples",
          registrationId,
          decisionId,
          ...(datasetId ? { datasetId } : {}),
          ...(caseId ? { caseId } : {}),
        };
      }
    }
  }
  return route && isValidWorkspaceRoute(route) ? route : null;
}
