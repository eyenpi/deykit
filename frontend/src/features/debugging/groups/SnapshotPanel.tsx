import type { ApiOperationData } from "../../../api/client";

type DiagnosticSnapshots = ApiOperationData<"listChoiceOrderSnapshots">;
type CheckSnapshots = ApiOperationData<"listCheckSnapshots">;
type Snapshot = DiagnosticSnapshots[number] | CheckSnapshots[number];

export function SnapshotPanel({
  snapshots,
  selectedId,
  onSelect,
  disabled = false,
}: {
  snapshots: readonly Snapshot[];
  selectedId: string | null;
  onSelect: (snapshotId: string) => void;
  disabled?: boolean;
}) {
  return (
    <section aria-labelledby="saved-snapshots-title">
      <h2 id="saved-snapshots-title">Saved snapshots</h2>
      {snapshots.length === 0 ? (
        <p className="muted">Pending snapshot. No immutable result is saved yet.</p>
      ) : (
        <div className="field">
          <label htmlFor="group-snapshot-select">Selected snapshot</label>
          <select
            id="group-snapshot-select"
            value={selectedId ?? ""}
            disabled={disabled}
            onChange={(event) => onSelect(event.currentTarget.value)}
          >
            {!selectedId && <option value="">Choose a saved snapshot</option>}
            {snapshots.map((snapshot) => (
              <option key={snapshot.id} value={snapshot.id}>
                Snapshot {snapshot.sequence} · {snapshot.id}
              </option>
            ))}
          </select>
        </div>
      )}
      {selectedId && (
        <button
          type="button"
          disabled={disabled || snapshots.at(-1)?.id === selectedId}
          onClick={() => {
            const latest = snapshots.at(-1);
            if (latest) onSelect(latest.id);
          }}
        >
          Select latest snapshot
        </button>
      )}
      {selectedId && (
        <p className="muted">
          The selected snapshot stays pinned while new snapshots arrive. Choose a
          different snapshot explicitly to change this view.
        </p>
      )}
      {selectedId && (
        <ol className="snapshot-membership">
          {snapshots
            .find((snapshot) => snapshot.id === selectedId)
            ?.results.map((member) => (
              <li key={`${member.run_id}:${member.result_snapshot_id}`}>
                <span>Member run </span>
                <code>{member.run_id}</code>
                <span> · result </span>
                <code>{member.result_snapshot_id}</code>
              </li>
            ))}
        </ol>
      )}
    </section>
  );
}
