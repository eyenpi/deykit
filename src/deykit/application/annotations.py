"""Append-only user notes separate from frozen answers and evaluations."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from deykit.application.dataset_support import identifier, page
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import JsonError, bytes_hash, semantic_hash
from deykit.contracts.ports import Clock, ProjectSource, ResourceKey, SourceChange, StoredRecord
from deykit.contracts.records import ResultAnnotation, RunManifest


@dataclass(frozen=True)
class StoredAnnotation:
    annotation: ResultAnnotation
    etag: str
    replayed: bool = False


@dataclass(frozen=True)
class AnnotationPage:
    items: tuple[StoredAnnotation, ...]
    total: int
    next_cursor: str | None


def annotation_hash(run_id: str, case_id: str, note: str) -> str:
    return semantic_hash({"run_id": run_id, "case_id": case_id, "note": note})


def _decoded(stored: StoredRecord, *, replayed: bool = False) -> StoredAnnotation:
    try:
        record = load_record(ResultAnnotation, stored.body)
        if record.content_hash != annotation_hash(record.run_id, record.case_id, record.note):
            raise JsonError("annotation_hash_mismatch")
    except (JsonError, ValidationError) as error:
        reason = error.code if isinstance(error, JsonError) else "invalid_annotation"
        raise ServiceFailure(
            ServiceError(code="validation_error", resource_id=stored.key.resource_id, reason=reason)
        ) from None
    return StoredAnnotation(record, stored.etag, replayed)


class AnnotationService:
    def __init__(
        self, source: ProjectSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory

    def add(self, run_id: str, case_id: str, note: str, *, operation_id: str) -> StoredAnnotation:
        identifier(run_id), identifier(case_id), identifier(operation_id)
        if type(note) is not str or not note.strip():
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_annotation_note")
            ) from None
        try:
            digest = semantic_hash(
                {
                    "command": "annotation.add",
                    "run_id": run_id,
                    "case_id": case_id,
                    "note_hash": bytes_hash(note.encode("utf-8")),
                }
            )
        except UnicodeError:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_annotation_note")
            ) from None
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return _decoded(replay.changes[0], replayed=True)
            stored_run = source.read(ResourceKey("runs", run_id))
            if stored_run is None:
                raise ServiceFailure(
                    ServiceError(code="not_found", reason="run_missing", resource_id=run_id)
                ) from None
            try:
                run = load_record(RunManifest, stored_run.body)
            except JsonError:
                raise ServiceFailure(
                    ServiceError(code="validation_error", reason="invalid_run", resource_id=run_id)
                ) from None
            if case_id not in run.case_ids:
                raise ServiceFailure(
                    ServiceError(code="not_found", reason="run_case_missing", resource_id=case_id)
                ) from None
            try:
                annotation = ResultAnnotation(
                    id=identifier(self.id_factory()),
                    run_id=run_id,
                    case_id=case_id,
                    operation_id=operation_id,
                    note=note,
                    content_hash=annotation_hash(run_id, case_id, note),
                    created_at=self.clock.utc_now(),
                )
                body = dump_record(annotation)
            except (ValidationError, JsonError):
                raise ServiceFailure(
                    ServiceError(code="validation_error", reason="invalid_annotation")
                ) from None
            receipt = source.commit(
                operation_id,
                (SourceChange(ResourceKey("annotations", annotation.id), body, None),),
                intent_hash=digest,
            )
            return _decoded(receipt.changes[0], replayed=receipt.replayed)

    def read(self, annotation_id: str) -> StoredAnnotation:
        key = ResourceKey("annotations", identifier(annotation_id))
        with self.source.consistent_read() as source:
            stored = source.read(key)
            if stored is None:
                raise ServiceFailure(
                    ServiceError(
                        code="not_found", reason="annotation_missing", resource_id=annotation_id
                    )
                ) from None
            return _decoded(stored)

    def list(
        self,
        run_id: str,
        *,
        case_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AnnotationPage:
        identifier(run_id)
        if case_id is not None:
            identifier(case_id)
        with self.source.consistent_read() as source:
            matching: dict[str, StoredAnnotation] = {}
            for annotation_id in source.list_ids("annotations"):
                stored = source.read(ResourceKey("annotations", annotation_id))
                if stored is None:
                    continue
                value = _decoded(stored)
                if value.annotation.run_id == run_id and (
                    case_id is None or value.annotation.case_id == case_id
                ):
                    matching[annotation_id] = value
            chosen, next_cursor = page(tuple(matching), cursor, limit)
            return AnnotationPage(
                tuple(matching[key] for key in chosen), len(matching), next_cursor
            )
