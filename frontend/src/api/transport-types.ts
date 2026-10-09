/** Shapes generated from the checked-in local API OpenAPI contract. */
export interface VersionedRequest {
  schema_version: 1;
}

export interface RegisterProjectRequest extends VersionedRequest {
  operation_id: string;
  action: "open" | "create";
  path: string;
  name: string | null;
}
