"""Native, read-only admission and exclusive acquisition for demo destinations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from deykit.application.demo import ExistingDemoDestination
from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.storage.filesystem import SafeFiles
from deykit.storage.source import FaultHook, FileProjectSource, IndexUpdater


class FileDemoDestinationFactory:
    def __init__(
        self,
        *,
        fault_hook: FaultHook | None = None,
        index_updater: IndexUpdater | None = None,
        acquisition_hook: Callable[[str], None] | None = None,
        admission_timeout_seconds: float | None = None,
    ) -> None:
        self._fault_hook = fault_hook
        self._index_updater = index_updater
        self._acquisition_hook = acquisition_hook
        self._admission_timeout_seconds = admission_timeout_seconds

    def open_existing(
        self, path: Path, *, operation_id: str, intent_hash: str
    ) -> ExistingDemoDestination | None:
        try:
            files = SafeFiles.open_existing(path)
        except ServiceFailure as error:
            if error.error.reason == "operation_id_conflict":
                raise
            raise self._path_conflict() from None
        except OSError:
            raise self._path_conflict() from None
        if files is None:
            return None
        try:
            source = FileProjectSource._from_files(
                files,
                fault_hook=self._fault_hook,
                index_updater=self._index_updater,
                admission_timeout_seconds=self._admission_timeout_seconds,
            )
        except BaseException:
            files.close()
            raise
        try:
            receipt = source._peek_durable_receipt(operation_id, intent_hash=intent_hash)
            if receipt is None:
                raise self._path_conflict()
            return ExistingDemoDestination(source, receipt)
        except ServiceFailure as error:
            source.close()
            if error.error.reason == "operation_id_conflict":
                raise
            if error.error.reason in {
                "journal_invalid",
                "journal_integrity_error",
                "journal_manifest_missing",
                "journal_identity_mismatch",
            }:
                raise error
            raise self._path_conflict() from None
        except BaseException:
            source.close()
            raise

    def create_exclusive(self, path: Path) -> FileProjectSource:
        files: SafeFiles | None = None
        try:
            files = SafeFiles.create_exclusive(path, acquisition_hook=self._acquisition_hook)
            return FileProjectSource._from_files(
                files,
                fault_hook=self._fault_hook,
                index_updater=self._index_updater,
                admission_timeout_seconds=self._admission_timeout_seconds,
            )
        except ServiceFailure as error:
            if files is not None:
                files.close()
            if error.error.reason in {"casefold_collision", "unsafe_project_path"}:
                raise self._path_conflict() from None
            raise
        except OSError:
            if files is not None:
                files.close()
            raise ServiceFailure(
                ServiceError(code="internal_error", reason="demo_path_unavailable")
            ) from None
        except BaseException:
            if files is not None:
                files.close()
            raise

    @staticmethod
    def _path_conflict() -> ServiceFailure:
        return ServiceFailure(ServiceError(code="conflict", reason="demo_path_exists"))
