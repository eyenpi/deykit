import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import type { ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { RegressionSheet } from "./RegressionSheet";

vi.mock("../../components/Modal", () => ({
  Modal: ({ children, title }: { children: ReactNode; title: string }) => (
    <div role="dialog" aria-label={title}>
      {children}
    </div>
  ),
}));

type Regression = ApiOperationData<"addRegression">;

it("requires a human oracle and replays the exact retained regression request", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const requests: Parameters<
    typeof disconnectedWorkspace.debugging.regressions.add
  >[0][] = [];
  let adds = 0;
  const regression: Regression = {
    schema_version: 1,
    regression_id: "regression-1",
    decision_id: "decision-1",
    dataset_id: "dataset-1",
    case_id: "case-1",
    question_id: "question-1",
    input_hash: "frozen-input-hash",
    acceptable_option_ids: ["option-2"],
    provenance: "human",
    reason: "The accepted answer is supported by the source.",
    source_run_id: "run-1",
    source_result_snapshot_id: "result-1",
    original_split: "test",
    executable: true,
    removed: false,
    unavailable_reason: null,
  };
  const operations = {
    ...disconnectedWorkspace.debugging.regressions,
    add: async (
      request: Parameters<
        typeof disconnectedWorkspace.debugging.regressions.add
      >[0],
    ) => {
      requests.push(request);
      adds += 1;
      if (adds === 1)
        throw new Error("reply lost after the service received the request");
      return { data: regression, warnings: [] };
    },
  };
  const tree = render(
    <RegressionSheet
      registrationId="registration-1"
      decisionId="decision-1"
      decisionName="Decision"
      runId="run-1"
      caseId="case-1"
      resultSnapshotId="result-1"
      options={[
        { id: "option-1", name: "First" },
        { id: "option-2", name: "Second" },
      ]}
      operations={operations}
      navigation={navigation}
      onClose={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    const first = screen.getByRole("checkbox", { name: /First/ });
    const second = screen.getByRole("checkbox", { name: /Second/ });
    expect((first as HTMLInputElement).checked).toBe(false);
    expect((second as HTMLInputElement).checked).toBe(false);
    await user.click(second);
    await user.type(
      screen.getByLabelText("Reason"),
      "The accepted answer is supported by the source.",
    );
    const save = screen.getByRole("button", {
      name: "Save regression example",
    });
    await user.dblClick(save);
    expect(
      await screen.findByRole("button", {
        name: "Retry original unchanged regression",
      }),
    ).toBeTruthy();
    expect(requests).toHaveLength(1);
    const original = requests[0]!;
    expect(original.body.acceptable_option_ids).toEqual(["option-2"]);
    expect(original.body.reason).toBe(
      "The accepted answer is supported by the source.",
    );
    expect(original.body.case_id).toBe("case-1");
    expect(original.body.run_id).toBe("run-1");
    expect(original.body.result_snapshot_id).toBe("result-1");

    await user.click(
      screen.getByRole("button", {
        name: "Retry original unchanged regression",
      }),
    );
    expect(
      await screen.findByText(
        /Regression regression-1 saved for the selected frozen case/,
      ),
    ).toBeTruthy();
    expect(requests).toHaveLength(2);
    expect(requests[1]?.body).toBe(original.body);
    expect(requests[1]?.body.operation_id).toBe(original.body.operation_id);
    expect(requests[1]?.body).toEqual(original.body);
    expect(adds).toBe(2);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
