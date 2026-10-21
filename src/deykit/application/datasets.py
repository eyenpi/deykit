"""Dataset aggregates and shared cases over conflict-checked portable source records."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import Field, ValidationError

from deykit.application.dataset_support import (
    CaseView,
    DatasetView,
    cases,
    decoded,
    fail,
    fingerprint,
    identifier,
    intent,
    page,
    required,
    validated_model,
)
from deykit.application.errors import ServiceFailure
from deykit.contracts.base import FrozenModel
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import new_id
from deykit.contracts.images import CaseImage
from deykit.contracts.json_value import JsonSource, JsonValue
from deykit.contracts.ports import (
    Clock,
    CommitReceipt,
    ProjectSource,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import CaseRecord, DatasetRecord, LabelChange, LabelRecord
from deykit.domain.case_identity import case_input_hash


class CaseInput(FrozenModel):
    input_kind: Literal["text", "json"]
    input_source: JsonSource
    tags: tuple[str, ...] = ()
    split: Literal["development", "calibration", "test"] = "development"
    group_id: str | None = None
    derived_from: tuple[str, ...] = ()
    metadata_source: JsonSource = "{}"
    images: tuple[CaseImage, ...] = Field(default=(), exclude_if=lambda v: not v)


@dataclass(frozen=True)
class DatasetPage:
    items: tuple[DatasetView, ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class CasePage:
    items: tuple[CaseView, ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class CaseMutation:
    dataset: DatasetView
    case: CaseView | None
    cleared_label_ids: tuple[str, ...] = ()
    replayed: bool = False


class DatasetService:
    def __init__(
        self, source: ProjectSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory

    def create(
        self,
        name: str,
        *,
        dataset_id: str | None = None,
        metadata_source: str = "{}",
        operation_id: str,
    ) -> DatasetView:
        identifier(operation_id)
        if dataset_id is not None:
            identifier(dataset_id)
        digest = intent("dataset.create", [dataset_id, name, metadata_source])
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self.from_receipt(replay)
            try:
                record = DatasetRecord(
                    id=dataset_id or identifier(self.id_factory()),
                    revision_id=identifier(self.id_factory()),
                    name=name,
                    created_at=self.clock.utc_now(),
                    metadata_source=metadata_source,
                )
                body = dump_record(record)
            except (ValueError, ValidationError):
                fail("invalid_dataset")
            receipt = self.source.commit(
                operation_id,
                (SourceChange(ResourceKey("datasets", record.id), body, None),),
                intent_hash=digest,
            )
            return self.from_receipt(receipt)

    def read(self, dataset_id: str) -> DatasetView:
        stored = required(self.source, ResourceKey("datasets", identifier(dataset_id)))
        return DatasetView(decoded(DatasetRecord, stored), stored.etag)

    def list(
        self, *, include_archived: bool = False, cursor: str | None = None, limit: int = 50
    ) -> DatasetPage:
        with self.source.consistent_read():
            views = {key: self.read(key) for key in self.source.list_ids("datasets")}
            visible = tuple(
                key for key, view in views.items() if include_archived or not view.record.archived
            )
            selected, next_cursor = page(visible, cursor, limit)
            return DatasetPage(tuple(views[key] for key in selected), len(visible), next_cursor)

    def update(
        self,
        dataset_id: str,
        *,
        name: str | None = None,
        metadata_source: str | None = None,
        expected_etag: str,
        operation_id: str,
    ) -> DatasetView:
        return self._update(
            dataset_id, expected_etag, operation_id, name=name, metadata_source=metadata_source
        )

    def archive(self, dataset_id: str, *, expected_etag: str, operation_id: str) -> DatasetView:
        return self._update(dataset_id, expected_etag, operation_id, archived=True)

    def restore(self, dataset_id: str, *, expected_etag: str, operation_id: str) -> DatasetView:
        return self._update(dataset_id, expected_etag, operation_id, archived=False)

    def _update(
        self, dataset_id: str, expected_etag: str, operation_id: str, **updates: str | bool | None
    ) -> DatasetView:
        identifier(dataset_id)
        identifier(operation_id)
        digest = intent("dataset.update", [dataset_id, expected_etag, cast(JsonValue, updates)])
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self.from_receipt(replay)
            current = self.read(dataset_id)
            self.check_etag(current, expected_etag, allow_archived=True)
            resolved = {
                key: (getattr(current.record, key) if value is None else value)
                for key, value in updates.items()
            }
            changed = self.bump(current.record, **resolved)
            receipt = self.source.commit(
                operation_id,
                (
                    SourceChange(
                        ResourceKey("datasets", dataset_id), dump_record(changed), expected_etag
                    ),
                ),
                intent_hash=digest,
            )
        return self.from_receipt(receipt)

    def list_cases(
        self,
        dataset_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        tag: str | None = None,
        group_id: str | None = None,
        split: str | None = None,
    ) -> CasePage:
        identifier(dataset_id)
        if group_id is not None:
            identifier(group_id)
        if split is not None and split not in {"development", "calibration", "test"}:
            fail("invalid_split")
        with self.source.consistent_read():
            self.read(dataset_id)
            records = cases(self.source, dataset_id)
            views = self._case_views(records)
            visible = tuple(
                key
                for key, view in views.items()
                if (tag is None or tag in view.record.tags)
                and (group_id is None or group_id == view.record.group_id)
                and (split is None or split == view.record.split)
            )
            chosen, next_cursor = page(visible, cursor, limit)
            return CasePage(tuple(views[key] for key in chosen), len(visible), next_cursor)

    def case(self, dataset_id: str, case_id: str) -> CaseView:
        identifier(dataset_id)
        identifier(case_id)
        with self.source.consistent_read():
            self.read(dataset_id)
            views = self._case_views(cases(self.source, dataset_id))
            if case_id not in views:
                fail("case_not_found", "not_found")
            return views[case_id]

    def add_case(
        self,
        dataset_id: str,
        value: CaseInput,
        *,
        expected_dataset_etag: str,
        operation_id: str,
        case_id: str | None = None,
    ) -> CaseMutation:
        return self._write_case(
            dataset_id,
            value,
            expected_dataset_etag,
            operation_id,
            case_id,
            expected_case_etag=None,
            creating=True,
        )

    def edit_case(
        self,
        dataset_id: str,
        case_id: str,
        value: CaseInput,
        *,
        expected_dataset_etag: str,
        expected_case_etag: str,
        operation_id: str,
    ) -> CaseMutation:
        return self._write_case(
            dataset_id,
            value,
            expected_dataset_etag,
            operation_id,
            case_id,
            expected_case_etag,
            creating=False,
        )

    def _write_case(
        self,
        dataset_id: str,
        value: CaseInput,
        dataset_etag: str,
        operation_id: str,
        case_id: str | None,
        expected_case_etag: str | None,
        *,
        creating: bool,
    ) -> CaseMutation:
        identifier(dataset_id)
        identifier(operation_id)
        if case_id is not None:
            identifier(case_id)
        value = validated_model(CaseInput, value, "invalid_case")
        digest = intent(
            "case.add" if creating else "case.edit",
            [
                dataset_id,
                case_id,
                dataset_etag,
                expected_case_etag,
                cast(JsonValue, value.model_dump(mode="json")),
            ],
        )
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self.mutation_from_receipt(replay)
            dataset = self.read(dataset_id)
            self.check_etag(dataset, dataset_etag)
            record = self.case_record(dataset_id, case_id or identifier(self.id_factory()), value)
            from deykit.application.images import case_assets

            asset_records = {
                ResourceKey("image_assets", image.asset_id): required(
                    self.source, ResourceKey("image_assets", image.asset_id)
                )
                for image in record.images
            }
            case_assets(record, asset_records)
            before = cases(self.source, dataset_id)
            existing = {item.key.resource_id: item for item in before}
            if creating and any(key.casefold() == record.id.casefold() for key in existing):
                fail("case_id_conflict", "conflict")
            if not creating and record.id not in existing:
                fail("case_not_found", "not_found")
            if fingerprint(before) != fingerprint(cases(self.source, dataset_id)):
                fail("unstable_dataset", "conflict")
            changed = self.bump(dataset.record)
            receipt = self.source.commit(
                operation_id,
                (
                    SourceChange(
                        ResourceKey("cases", record.id, (dataset_id,)),
                        dump_record(record),
                        expected_case_etag,
                    ),
                    SourceChange(
                        ResourceKey("datasets", dataset_id), dump_record(changed), dataset_etag
                    ),
                ),
                intent_hash=digest,
            )
        return self.mutation_from_receipt(receipt)

    def remove_case(
        self,
        dataset_id: str,
        case_id: str,
        *,
        expected_dataset_etag: str,
        expected_case_etag: str,
        operation_id: str,
    ) -> CaseMutation:
        identifier(dataset_id)
        identifier(case_id)
        identifier(operation_id)
        digest = intent(
            "case.remove", [dataset_id, case_id, expected_dataset_etag, expected_case_etag]
        )
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self.mutation_from_receipt(replay)
            dataset = self.read(dataset_id)
            self.check_etag(dataset, expected_dataset_etag)
            required(self.source, ResourceKey("cases", case_id, (dataset_id,)))
            changes = [
                SourceChange(ResourceKey("cases", case_id, (dataset_id,)), None, expected_case_etag)
            ]
            for decision_id in self.source.list_ids("decisions"):
                scope = (decision_id, dataset_id)
                for key in self.source.list_ids("labels", scope):
                    stored = required(self.source, ResourceKey("labels", key, scope))
                    label = decoded(LabelRecord, stored)
                    if label.case_id != case_id:
                        continue
                    change = LabelChange(
                        id=identifier(self.id_factory()),
                        operation_id=operation_id,
                        decision_id=decision_id,
                        dataset_id=dataset_id,
                        case_id=case_id,
                        question_id=label.question_id,
                        action="clear",
                        label=None,
                        created_at=self.clock.utc_now(),
                    )
                    changes += [
                        SourceChange(stored.key, None, stored.etag),
                        SourceChange(
                            ResourceKey("label_history", change.id, scope),
                            dump_record(change),
                            None,
                        ),
                    ]
            changes.append(
                SourceChange(
                    ResourceKey("datasets", dataset_id),
                    dump_record(self.bump(dataset.record)),
                    expected_dataset_etag,
                )
            )
            receipt = self.source.commit(operation_id, tuple(changes), intent_hash=digest)
        return self.mutation_from_receipt(receipt)

    def bump(self, record: DatasetRecord, **updates: str | bool) -> DatasetRecord:
        try:
            return DatasetRecord.model_validate(
                {**record.model_dump(), **updates, "revision_id": identifier(self.id_factory())}
            )
        except (ValueError, ValidationError):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_dataset")
            ) from None

    @staticmethod
    def check_etag(view: DatasetView, expected: str, *, allow_archived: bool = False) -> None:
        if view.etag != expected:
            fail("dataset_revision_changed", "conflict")
        if view.record.archived and not allow_archived:
            fail("dataset_archived", "conflict")

    @staticmethod
    def case_record(dataset_id: str, case_id: str, value: CaseInput) -> CaseRecord:
        try:
            record = CaseRecord(id=case_id, dataset_id=dataset_id, **value.model_dump())
            if len(record.tags) != len(set(record.tags)) or any(
                not tag.strip() for tag in record.tags
            ):
                fail("invalid_tags")
            return record
        except (ValueError, ValidationError):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_case")
            ) from None

    @staticmethod
    def from_receipt(receipt: CommitReceipt) -> DatasetView:
        for stored in receipt.changes:
            if stored.key.collection == "datasets":
                return DatasetView(decoded(DatasetRecord, stored), stored.etag)
        raise ServiceFailure(ServiceError(code="internal_error", reason="incomplete_receipt"))

    @classmethod
    def mutation_from_receipt(cls, receipt: CommitReceipt) -> CaseMutation:
        stored = next((item for item in receipt.changes if item.key.collection == "cases"), None)
        view = CaseView(decoded(CaseRecord, stored), stored.etag) if stored else None
        return CaseMutation(
            cls.from_receipt(receipt),
            view,
            tuple(key.resource_id for key in receipt.deleted_keys if key.collection == "labels"),
            receipt.replayed,
        )

    @staticmethod
    def _case_views(records: tuple["StoredRecord", ...]) -> dict[str, CaseView]:
        views: dict[str, CaseView] = {}
        hashes: dict[str, list[str]] = {}
        for stored in records:
            record = decoded(CaseRecord, stored)
            views[record.id] = CaseView(record, stored.etag)
            hashes.setdefault(case_input_hash(record), []).append(record.id)
        return {
            key: CaseView(
                view.record,
                view.etag,
                tuple(other for other in hashes[case_input_hash(view.record)] if other != key),
            )
            for key, view in views.items()
        }
