import { ApiError } from "../api/client";
export interface ResourceSummary {
  id: string;
  name: string;
}
export interface ProjectSummary extends ResourceSummary {
  path: string;
}
export interface ProjectOverview extends ProjectSummary {
  decisions: readonly ResourceSummary[];
  datasets: readonly ResourceSummary[];
}
export type ProjectAction = "create" | "open" | "demo";
export interface ProjectRequest {
  action: ProjectAction;
  path: string;
  name: string;
  operationId: string;
}
/** Presentation port. P15's generated transport adapter will implement this interface. */
export interface WorkspaceGateway {
  recentProjects(signal: AbortSignal): Promise<readonly ProjectSummary[]>;
  openProject(request: ProjectRequest): Promise<ProjectOverview>;
}
const pending = () =>
  new ApiError(
    "integration_pending",
    "The local workspace service is not connected in this build. Project folders are unavailable.",
  );
/** Deliberately no mock successes, filesystem guesses, or speculative API endpoints. */
export const disconnectedWorkspace: WorkspaceGateway = {
  async recentProjects() {
    throw pending();
  },
  async openProject() {
    throw pending();
  },
};
