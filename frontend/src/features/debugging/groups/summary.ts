/** Narrow, exact presentation for the diagnostics summary's JSON boundary. */
export interface PresentedDiagnosticSummary {
  independentCases: string;
  orders: string;
  expandedResults: string;
  fullyObservedCases: string;
  disagreement: {
    numerator: string;
    denominator: string;
    value: string | null;
    reason: string | null;
  };
  cases: readonly {
    caseId: string;
    options: readonly (string | null)[];
    statuses: readonly string[];
    disagreed: boolean;
    fullyObserved: boolean;
  }[];
}

function record(value: unknown): Record<string, unknown> | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    return undefined;
  return Object.fromEntries(Object.entries(value));
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  return (
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function countText(value: unknown): value is string {
  return typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value);
}

const CASE_STATUSES = new Set([
  "pending",
  "input_invalid",
  "response_error",
  "unknown",
  "valid",
]);

function optionIds(value: unknown): value is (string | null)[] {
  return Array.isArray(value) && value.every(
    (option): option is string | null =>
      option === null || typeof option === "string",
  );
}

function caseStatuses(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(
    (status): status is string =>
      typeof status === "string" && CASE_STATUSES.has(status),
  );
}

export function presentDiagnosticSummary(
  input: unknown,
): PresentedDiagnosticSummary | undefined {
  const value = record(input);
  if (
    !value ||
    !exactKeys(value, [
      "independent_case_count",
      "order_count",
      "expanded_result_count",
      "fully_observed_case_count",
      "disagreement",
      "cases",
      "interpretation",
    ]) ||
    value.interpretation !== "observed_request_order_sensitivity" ||
    !countText(value.independent_case_count) ||
    !countText(value.order_count) ||
    !countText(value.expanded_result_count) ||
    !countText(value.fully_observed_case_count) ||
    !Array.isArray(value.cases)
  )
    return undefined;

  const disagreement = record(value.disagreement);
  if (
    !disagreement ||
    !exactKeys(disagreement, ["numerator", "denominator", "value", "reason"]) ||
    !countText(disagreement.numerator) ||
    !countText(disagreement.denominator) ||
    (disagreement.value !== null &&
      (typeof disagreement.value !== "string" ||
        !/^(?:0\.\d{6}|1\.000000)$/.test(disagreement.value))) ||
    (disagreement.reason !== null && typeof disagreement.reason !== "string")
  )
    return undefined;

  const cases: PresentedDiagnosticSummary["cases"][number][] = [];
  for (const item of value.cases) {
    const sensitivity = record(item);
    if (
      !sensitivity ||
      !exactKeys(sensitivity, [
        "case_id",
        "option_ids",
        "statuses",
        "observed_disagreement",
        "fully_observed",
      ]) ||
      typeof sensitivity.case_id !== "string" ||
      !optionIds(sensitivity.option_ids) ||
      !caseStatuses(sensitivity.statuses) ||
      typeof sensitivity.observed_disagreement !== "boolean" ||
      typeof sensitivity.fully_observed !== "boolean"
    )
      return undefined;
    cases.push({
      caseId: sensitivity.case_id,
      options: sensitivity.option_ids,
      statuses: sensitivity.statuses,
      disagreed: sensitivity.observed_disagreement,
      fullyObserved: sensitivity.fully_observed,
    });
  }

  return {
    independentCases: value.independent_case_count,
    orders: value.order_count,
    expandedResults: value.expanded_result_count,
    fullyObservedCases: value.fully_observed_case_count,
    disagreement: {
      numerator: disagreement.numerator,
      denominator: disagreement.denominator,
      value: disagreement.value,
      reason: disagreement.reason,
    },
    cases,
  };
}
