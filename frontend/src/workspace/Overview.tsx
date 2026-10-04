import type { Ref } from "react";
import { DataTable } from "../components/DataTable";
import type { ProjectOverview, ResourceSummary } from "./gateway";
export function Overview({
  project,
  headingRef,
  onDecision,
  onAction,
}: {
  project: ProjectOverview;
  headingRef?: Ref<HTMLHeadingElement>;
  onDecision: (decision: ResourceSummary) => void;
  onAction: (action: string) => void;
}) {
  return (
    <article className="document">
      <h1 ref={headingRef} tabIndex={-1}>
        {project.name}
      </h1>
      <p className="muted">Project folder</p>
      <div className="section">
        <p className="muted">Project location</p>
        <p className="path">{project.path}</p>
      </div>
      <section className="section">
        <h2>Decisions</h2>
        <p className="muted">Define the question and allowed answers.</p>
        {project.decisions.length > 0 && (
          <DataTable
            caption="Project decisions"
            rows={project.decisions}
            rowId={(row) => row.id}
            columns={[
              {
                key: "name",
                heading: "Decision",
                render: (row) => (
                  <button
                    className="text-button"
                    onClick={() => onDecision(row)}
                  >
                    {row.name}
                  </button>
                ),
              },
              {
                key: "id",
                heading: "ID",
                render: (row) => <code>{row.id}</code>,
              },
            ]}
          />
        )}
        <button className="primary" onClick={() => onAction("Create decision")}>
          Create decision
        </button>
      </section>
      <section className="section">
        <h2>Examples</h2>
        <p className="muted">
          Add inputs now, even before defining a decision.
        </p>
        {project.datasets.length > 0 && (
          <DataTable
            caption="Project datasets"
            rows={project.datasets}
            rowId={(row) => row.id}
            columns={[
              { key: "name", heading: "Dataset", render: (row) => row.name },
            ]}
          />
        )}
        <div className="actions">
          <button onClick={() => onAction("Import examples")}>
            Import examples
          </button>
          <button onClick={() => onAction("Add example")}>Add example</button>
        </div>
      </section>
    </article>
  );
}
