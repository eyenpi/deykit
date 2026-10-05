"""Preview and atomically apply full-dataset grouped splits with immutable evidence."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from deykit.application.dataset_support import (
    DatasetView,
    cases,
    decoded,
    fail,
    fingerprint,
    identifier,
    intent,
    safe_hash,
)
from deykit.application.datasets import DatasetService
from deykit.contracts.codec import dump_record
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import JsonError, JsonValue, bytes_hash, dump_json, parse_json
from deykit.contracts.ports import Clock, CommitReceipt, ProjectSource, ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, DatasetSnapshot
from deykit.domain.splits import (
    ALGORITHM,
    DEFAULT_RATIOS,
    SPLITS,
    Split,
    assign,
    connected_groups,
    validate_assignments,
)


@dataclass(frozen=True)
class SplitPreview:
    dataset_id: str
    dataset_etag: str
    input_identity: str
    algorithm: str
    seed: int | None
    ratios_source: str | None
    assignments: tuple[tuple[str, Split], ...]
    groups: tuple[tuple[str, ...], ...]
    counts: tuple[tuple[Split, int], ...]

    def evidence(self) -> JsonValue:
        return {
            "snapshot_hash_profile": "deykit-split-snapshot-v1",
            "algorithm": self.algorithm,
            "seed": self.seed,
            "ratios": parse_json(self.ratios_source) if self.ratios_source else None,
            "assignments": [list(pair) for pair in self.assignments],
            "groups": [list(group) for group in self.groups],
            "counts": dict(self.counts),
            "input_identity": self.input_identity,
            "dataset_etag": self.dataset_etag,
        }


@dataclass(frozen=True)
class SplitCommit:
    dataset: DatasetView
    snapshot: DatasetSnapshot
    replayed: bool


class SplitService:
    def __init__(
        self, source: ProjectSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory
        self.datasets = DatasetService(source, clock, id_factory)

    def preview(
        self,
        dataset_id: str,
        *,
        seed: int = 0,
        ratios_source: str = DEFAULT_RATIOS,
        assignments: tuple[tuple[str, Split], ...] | None = None,
    ) -> SplitPreview:
        identifier(dataset_id)
        with self.source.consistent_read():
            dataset = self.datasets.read(dataset_id)
            if dataset.record.archived:
                fail("dataset_archived", "conflict")
            stored = cases(self.source, dataset_id)
            records = tuple(decoded(CaseRecord, item) for item in stored)
            try:
                if type(seed) is not int:
                    fail("invalid_split_seed")
                if assignments is not None:
                    if seed != 0 or ratios_source != DEFAULT_RATIOS:
                        fail("assignments_exclude_seed_and_ratios")
                    validate_assignments(records, assignments)
                    chosen = tuple(sorted(assignments))
                else:
                    chosen = assign(records, seed, ratios_source)
                groups = connected_groups(records)
            except (ValueError, JsonError) as error:
                reason = str(error) if isinstance(error, ValueError) else error.code
                # Domain errors use fixed, public reason identifiers only.
                fail(reason)
            identity = fingerprint(stored)
            if identity != fingerprint(cases(self.source, dataset_id)):
                fail("unstable_split_input", "conflict")
            return SplitPreview(
                dataset_id,
                dataset.etag,
                identity,
                "explicit-connected-v1" if assignments is not None else ALGORITHM,
                None if assignments is not None else seed,
                None if assignments is not None else ratios_source,
                chosen,
                groups,
                tuple((split, sum(s == split for _, s in chosen)) for split in SPLITS),
            )

    def commit(self, preview: SplitPreview, *, operation_id: str) -> SplitCommit:
        identifier(operation_id)
        try:
            digest = intent("split.commit", [preview.dataset_id, preview.evidence()])
        except (ValueError, TypeError):
            fail("invalid_split_preview")
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self._result(replay)
            if preview.algorithm == "explicit-connected-v1":
                current = self.preview(preview.dataset_id, assignments=preview.assignments)
            elif (
                preview.algorithm == ALGORITHM
                and preview.seed is not None
                and preview.ratios_source is not None
            ):
                current = self.preview(
                    preview.dataset_id, seed=preview.seed, ratios_source=preview.ratios_source
                )
            else:
                fail("invalid_split_preview")
            if current != preview:
                fail("split_preview_changed", "conflict")
            stored = cases(self.source, preview.dataset_id)
            mapping = dict(preview.assignments)
            records = tuple(
                CaseRecord.model_validate(
                    {
                        **decoded(CaseRecord, item).model_dump(),
                        "split": mapping[item.key.resource_id],
                    }
                )
                for item in stored
            )
            try:
                selection = dump_json(preview.evidence())
                snapshot = DatasetSnapshot(
                    id=identifier(self.id_factory()),
                    dataset_id=preview.dataset_id,
                    cases=records,
                    content_hash=safe_hash(
                        {
                            "profile": "deykit-split-snapshot-v1",
                            "case_bytes_hashes": [bytes_hash(dump_record(r)) for r in records],
                            "selection_hash": safe_hash(parse_json(selection)),
                        }
                    ),
                    created_at=self.clock.utc_now(),
                    selection_source=selection,
                )
                snapshot_body = dump_record(snapshot)
            except (ValueError, ValidationError, JsonError):
                fail("split_snapshot_resource_limit")
            dataset = self.datasets.read(preview.dataset_id)
            self.datasets.check_etag(dataset, preview.dataset_etag)
            changes = [
                SourceChange(item.key, dump_record(record), item.etag)
                for item, record in zip(stored, records, strict=True)
            ]
            changes.extend(
                (
                    SourceChange(
                        ResourceKey("datasets", preview.dataset_id),
                        dump_record(self.datasets.bump(dataset.record)),
                        preview.dataset_etag,
                    ),
                    SourceChange(
                        ResourceKey("dataset_snapshots", snapshot.id), snapshot_body, None
                    ),
                )
            )
            if fingerprint(stored) != fingerprint(cases(self.source, preview.dataset_id)):
                fail("unstable_split_input", "conflict")
            return self._result(
                self.source.commit(operation_id, tuple(changes), intent_hash=digest)
            )

    @staticmethod
    def _result(receipt: CommitReceipt) -> SplitCommit:
        snapshot = next(
            (
                decoded(DatasetSnapshot, item)
                for item in receipt.changes
                if item.key.collection == "dataset_snapshots"
            ),
            None,
        )
        if snapshot is None:
            fail("incomplete_split_receipt", "internal_error")
        return SplitCommit(DatasetService.from_receipt(receipt), snapshot, receipt.replayed)
