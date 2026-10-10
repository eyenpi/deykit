/** Stable, non-sensitive routes for the local workspace. User source never belongs here. */
export type WorkspaceRoute =
  | { kind: "start" }
  | { kind: "overview"; registrationId: string }
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
  | { kind: "fixtures"; registrationId: string };

const RESOURCE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const EXAMPLE_QUERY_KEYS = new Set(["dataset", "case"]);

function validId(value: string | null | undefined): value is string {
  return value !== null && value !== undefined && RESOURCE_ID.test(value);
}

export function isValidWorkspaceRoute(route: WorkspaceRoute): boolean {
  switch (route.kind) {
    case "start":
      return true;
    case "overview":
    case "providers":
    case "fixtures":
      return validId(route.registrationId);
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
    case "decision":
      return `#/p/${route.registrationId}/d/${route.decisionId}`;
    case "decision-history":
      return `#/p/${route.registrationId}/d/${route.decisionId}/history`;
    case "providers":
      return `#/p/${route.registrationId}/providers`;
    case "fixtures":
      return `#/p/${route.registrationId}/fixtures`;
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
  if (
    keys.some((key) => !EXAMPLE_QUERY_KEYS.has(key)) ||
    new Set(keys).size !== keys.length
  )
    return null;
  const datasetId = query.get("dataset") ?? undefined;
  const caseId = query.get("case") ?? undefined;
  if (
    (datasetId !== undefined && !validId(datasetId)) ||
    (caseId !== undefined && !validId(caseId))
  )
    return null;

  let route: WorkspaceRoute | null = null;
  if (segments.length === 0) {
    if (keys.length === 0) route = { kind: "start" };
  } else if (segments[0] === "p" && validId(segments[1])) {
    const registrationId = segments[1];
    if (segments.length === 2 && keys.length === 0) {
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
    } else if (segments[2] === "examples" && segments.length === 3) {
      route = { kind: "examples", registrationId, decisionId: null };
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
      } else if (segments[4] === "examples" && segments.length === 5) {
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
