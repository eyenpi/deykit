"""Project application services with injected source factory, clock, and ID generation."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from deykit.application.errors import ServiceFailure
from deykit.application.project_references import validate_project_references
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import semantic_hash
from deykit.contracts.ports import Clock, ProjectSource, ResourceKey, SourceChange, StoredRecord
from deykit.contracts.records import ProjectRecord


class ProjectBackend(ProjectSource, Protocol):
    last_index_error: str | None

    def close(self) -> None: ...
    def execution_active(self) -> bool: ...
    def capture_snapshot(
        self, keys: tuple[ResourceKey, ...] | None = None
    ) -> tuple[StoredRecord, ...]: ...
    def rebuild_index(self) -> int: ...


SourceFactory = Callable[[Path, bool], ProjectBackend]


@dataclass(frozen=True)
class ProjectInfo:
    project: ProjectRecord
    etag: str
    execution_active: bool
    record_count: int
    index_warning: str | None = None
    reference_warnings: tuple[ServiceError, ...] = ()


class ProjectService:
    def __init__(
        self, source_factory: SourceFactory, clock: Clock, id_factory: Callable[[], str]
    ) -> None:
        self._factory = source_factory
        self._clock = clock
        self._id = id_factory

    @staticmethod
    def validate_opened(source: ProjectBackend) -> ProjectInfo:
        """Validate one captured view of a caller-owned, already-open source."""
        # Probe execution first; never wait for execution ownership while holding source lock.
        active = source.execution_active()
        with source.consistent_read():
            records = source.capture_snapshot()
            reference_warnings = validate_project_references(records).warnings
        return ProjectService._info_from_records(
            records,
            execution_active=active,
            index_warning=source.last_index_error,
            reference_warnings=reference_warnings,
        )

    @staticmethod
    def _info_from_records(
        records: tuple[StoredRecord, ...],
        *,
        execution_active: bool,
        index_warning: str | None,
        reference_warnings: tuple[ServiceError, ...] = (),
    ) -> ProjectInfo:
        projects = [record for record in records if record.key.collection == "project"]
        if len(projects) != 1:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="project_record_missing")
            )
        record = projects[0]
        return ProjectInfo(
            load_record(ProjectRecord, record.body),
            record.etag,
            execution_active,
            len(records),
            index_warning,
            reference_warnings,
        )

    @staticmethod
    def _info(source: ProjectBackend) -> ProjectInfo:
        # Opening a project remains metadata-only; keep the legacy private spelling.
        return ProjectService.describe(source)

    @staticmethod
    def describe(source: ProjectBackend) -> ProjectInfo:
        """Describe a caller-owned opened project without closing it."""
        active = source.execution_active()
        records = source.capture_snapshot()
        return ProjectService._info_from_records(
            records,
            execution_active=active,
            index_warning=source.last_index_error,
        )

    def create(self, path: Path, name: str, operation_id: str) -> ProjectInfo:
        source = self._factory(path, True)
        try:
            return self.create_in(source, name, operation_id)
        finally:
            source.close()

    def create_in(self, source: ProjectBackend, name: str, operation_id: str) -> ProjectInfo:
        """Create or replay a project using a caller-owned opened source."""
        intent = semantic_hash({"command": "project_create", "name": name})
        receipt = source.operation_receipt(operation_id, intent_hash=intent)
        if receipt is None:
            with source.consistent_read():
                # Another caller may commit this intent after our first lookup.
                receipt = source.operation_receipt(operation_id, intent_hash=intent)
                if receipt is None:
                    if source.list_ids("project"):
                        raise ServiceFailure(
                            ServiceError(code="conflict", reason="project_exists")
                        )
                    try:
                        project = ProjectRecord(
                            id=self._id(), name=name, created_at=self._clock.utc_now()
                        )
                    except ValidationError:
                        raise ServiceFailure(
                            ServiceError(code="validation_error", reason="invalid_project")
                        ) from None
                    receipt = source.commit(
                        operation_id,
                        (
                            SourceChange(
                                ResourceKey("project", project.id), dump_record(project), None
                            ),
                        ),
                        intent_hash=intent,
                    )
        current = self.describe(source)
        original = next(
            record for record in receipt.changes if record.key.collection == "project"
        )
        return ProjectInfo(
            load_record(ProjectRecord, original.body),
            original.etag,
            current.execution_active,
            current.record_count,
            current.index_warning,
        )

    def open(self, path: Path) -> ProjectInfo:
        source = self._factory(path, False)
        try:
            return self._info(source)
        finally:
            source.close()

    def validate(self, path: Path) -> ProjectInfo:
        source = self._factory(path, False)
        try:
            return self.validate_opened(source)
        finally:
            source.close()

    def rebuild_index(self, path: Path) -> int:
        source = self._factory(path, False)
        try:
            self._info(source)
            return source.rebuild_index()
        finally:
            source.close()

    def snapshot(
        self, path: Path, keys: tuple[ResourceKey, ...] | None = None
    ) -> tuple[StoredRecord, ...]:
        source = self._factory(path, False)
        try:
            return source.capture_snapshot(keys)
        finally:
            source.close()


def nearest_project(start: Path) -> Path | None:
    """CLI ancestor discovery uses the single authoritative root marker."""
    directory = start if start.is_dir() else start.parent
    for candidate in (directory, *directory.parents):
        marker = candidate / "deykit.project.json"
        if marker.is_symlink():
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="unsafe_project_path")
            )
        if marker.is_file():
            return candidate
    return None
