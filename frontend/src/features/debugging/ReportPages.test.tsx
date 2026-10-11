import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import { ReportPage } from "./ReportPages";

function result<T>(data: T) {
  return Promise.resolve({ data, warnings: [] });
}

const report: ApiOperationData<"readReport"> = {
  schema_version: 1,
  report_id: "report-1",
  target_kind: "evaluation",
  target_id: "evaluation-1",
  evaluation_ids: ["evaluation-1"],
  result_snapshot_ids: ["result-1"],
  label_snapshot_ids: ["labels-1"],
  diagnostic_snapshot_id: null,
  check_snapshot_id: null,
  comparison_id: null,
  evidence_modes: ["authored_fixture"],
  legacy: false,
  nonexportable_reason: null,
  raw: { inputs: false, requests: false, responses: false },
  created_at: "2026-10-11T00:00:00Z",
  content_hash: "a".repeat(64),
};

it("clears bytes and preview when changing the requested report format", async () => {
  const requests: Parameters<typeof disconnectedWorkspace.debugging.reports.download>[0][] = [];
  const operations = {
    ...disconnectedWorkspace.debugging.reports,
    read: async () => result(report),
    download: async (request: (typeof requests)[number]) => {
      requests.push(request);
      return {
        blob: new Blob([request.query.format === "json" ? '{"report":1}' : "# Report\n"]),
        filename: request.query.format === "json" ? "report.json" : "report.md",
      };
    },
  };
  render(
    <ReportPage registrationId="registration-1" reportId="report-1" operations={operations} />,
  );
  const user = userEvent.setup();
  await screen.findByText(/Report report-1/);
  await user.click(screen.getByRole("button", { name: "Preview report bytes" }));
  expect(await screen.findByText('{"report":1}')).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain("as json");

  await user.selectOptions(screen.getByLabelText("Download format"), "markdown");
  expect(screen.queryByText('{"report":1}')).toBeNull();
  expect(screen.queryByRole("status")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Preview report bytes" }));
  expect(await screen.findByText("# Report")).toBeTruthy();
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[0]?.query.format).toBe("json");
  expect(requests[1]?.query.format).toBe("markdown");
  expect(screen.getByRole("status").textContent).toContain("as markdown");
});
