import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { RegressionList } from "./RegressionList";

type Regression = ApiOperationData<"listRegressions">["items"][number];

function savedRegression(removed = false): Regression {
  return {
    schema_version: 1,
    regression_id: "regression-1",
    decision_id: "decision-1",
    dataset_id: "dataset-1",
    case_id: "case-1",
    question_id: "question-1",
    input_hash: "frozen-input-hash",
    acceptable_option_ids: ["option-2"],
    provenance: "human",
    reason: "The source supports this answer.",
    source_run_id: "run-1",
    source_result_snapshot_id: "result-1",
    original_split: "test",
    executable: true,
    removed,
    unavailable_reason: null,
  };
}

it("keeps a known removal receipt when list recovery fails and refreshes without another removal", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/regressions");
  const navigation = new WorkspaceNavigation(window);
  const removeRequests: Parameters<typeof disconnectedWorkspace.debugging.regressions.remove>[0][] = [];
  let listCalls = 0;
  const operations = {
    ...disconnectedWorkspace.debugging.regressions,
    list: async () => {
      listCalls += 1;
      if (listCalls === 2) throw new ApiError("read_unavailable", "list refresh unavailable", 503);
      return { data: { items: [savedRegression(listCalls > 2)] }, warnings: [] };
    },
    remove: async (request: Parameters<typeof disconnectedWorkspace.debugging.regressions.remove>[0]) => {
      removeRequests.push(request);
      return { data: savedRegression(true), warnings: [] };
    },
  };
  const tree = render(
    <RegressionList
      registrationId="registration-1"
      decisionId="decision-1"
      decisionName="Decision"
      operations={operations}
      navigation={navigation}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.click(await screen.findByRole("button", { name: "Remove from future checks" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("list refresh unavailable"));
    expect(screen.getByRole("status").textContent).toContain("regression-1");
    expect(removeRequests).toHaveLength(1);
    expect(removeRequests[0]?.regressionId).toBe("regression-1");
    expect(removeRequests[0]?.body.operation_id).toBeTruthy();
    expect(listCalls).toBe(2);

    await user.click(screen.getByRole("button", { name: /Retry/ }));
    expect(await screen.findByText(/Removed/)).toBeTruthy();
    expect(listCalls).toBe(3);
    expect(removeRequests).toHaveLength(1);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
