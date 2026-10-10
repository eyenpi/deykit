import validators from "@deykit/validators";
import { ApiError, object } from "./client";
import type {
  ProjectOverview,
  ProjectSummary,
  ResourceSummary,
} from "../workspace/gateway";

function invalid(): never {
  throw new ApiError(
    "response_invalid",
    "The local service returned unsupported project data.",
  );
}

export function decodeRecentProjects(
  value: unknown,
): readonly ProjectSummary[] {
  if (!validators.validateRecentProjectsDTO(value)) return invalid();
  const items = object(value).items;
  if (!Array.isArray(items)) return invalid();
  return items.map((item) => {
    const row = object(item);
    if (
      typeof row.id !== "string" ||
      typeof row.name !== "string" ||
      typeof row.path !== "string"
    )
      return invalid();
    return { id: row.id, name: row.name, path: row.path };
  });
}

function resources(value: unknown): readonly ResourceSummary[] {
  if (!Array.isArray(value)) return invalid();
  return value.map((item) => {
    if (!validators.validateResourceSummaryDTO(item)) return invalid();
    const row = object(item);
    if (typeof row.id !== "string" || typeof row.name !== "string")
      return invalid();
    return { id: row.id, name: row.name };
  });
}

export function decodeProjectOverview(
  value: unknown,
): Omit<ProjectOverview, "warnings"> {
  if (!validators.validateProjectOverviewDTO(value)) return invalid();
  const overview = object(value);
  const registration = object(overview.registration);
  const project = object(registration.project);
  if (
    typeof registration.registration_id !== "string" ||
    typeof registration.path !== "string" ||
    typeof project.name !== "string" ||
    !Array.isArray(overview.decisions) ||
    !Array.isArray(overview.datasets)
  )
    return invalid();
  return {
    id: registration.registration_id,
    name: project.name,
    path: registration.path,
    decisions: resources(overview.decisions),
    datasets: resources(overview.datasets),
  };
}

export function decodeRegistration(value: unknown): string {
  if (!validators.validateRegistrationDTO(value)) return invalid();
  const registration = object(value);
  if (typeof registration.registration_id !== "string") return invalid();
  return registration.registration_id;
}

export function decodeDemoRegistration(value: unknown): string {
  const result = object(value);
  if (!validators.validateRegistrationDTO(result.registration))
    return invalid();
  const registration = object(result.registration);
  const demo = object(result.demo);
  if (
    typeof registration.registration_id !== "string" ||
    typeof demo.operation_id !== "string" ||
    typeof demo.replayed !== "boolean" ||
    demo.evidence_mode !== "authored_fixture" ||
    typeof demo.project_id !== "string" ||
    typeof demo.decision_id !== "string" ||
    typeof demo.revision_id !== "string" ||
    typeof demo.dataset_id !== "string" ||
    typeof demo.profile_id !== "string" ||
    typeof demo.fixture_set_id !== "string" ||
    typeof demo.case_count !== "string" ||
    typeof demo.binding_count !== "string" ||
    typeof demo.label_count !== "string"
  )
    return invalid();
  return registration.registration_id;
}
