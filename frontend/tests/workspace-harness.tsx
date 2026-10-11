// Authored workspace gateway for browser regressions only; not a production entry.
import { createRoot } from "react-dom/client";
import { App } from "../src/App";
import { disconnectedWorkspace } from "../src/workspace/gateway";
import type { WorkspaceGateway } from "../src/workspace/gateway";
import "../src/styles.css";
const recent = [
  { id: "first", name: "First authored project", path: "/tmp/First folder" },
  {
    id: "second",
    name: "Second authored project",
    path: "/tmp/Second exact folder",
  },
];
const gateway: WorkspaceGateway = {
  authoring: disconnectedWorkspace.authoring,
  execution: disconnectedWorkspace.execution,
  async recentProjects() {
    return { items: recent, warnings: [] };
  },
  async projectOverview(registrationId) {
    const project = recent.find((item) => item.id === registrationId);
    if (!project)
      throw new Error("Authored test expected a known project registration");
    return { ...project, decisions: [], datasets: [], warnings: [] };
  },
  async openProject(request) {
    const project = recent.find((item) => item.path === request.path);
    if (!project)
      throw new Error("Authored test expected a known project path");
    return { ...project, decisions: [], datasets: [], warnings: [] };
  },
  async reconnect() {},
};
createRoot(document.getElementById("root")!).render(<App gateway={gateway} />);
