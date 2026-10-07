"""Project validation reuses one caller-owned capture and surfaces legacy warnings."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectBackend, ProjectService
from deykit.cli import projects as project_commands
from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.evidence import evidence_hash
from deykit.contracts.ports import Collection, ResourceKey, StoredRecord
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DatasetSnapshot,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    ExecutionSettings,
    LabelSnapshot,
    ProjectRecord,
    ProviderProfile,
    RunManifest,
)
from deykit.domain.definitions import definition_hash

STAMP = "2026-10-05T12:00:00Z"


def captured_legacy_project() -> tuple[StoredRecord, ...]:
    definition = ChoiceDefinition(
        input_kind="json",
        questions=(
            ChoiceQuestion(
                id="question",
                instructions="Choose an option",
                options=(
                    ChoiceOption(id="yes", name="Yes"),
                    ChoiceOption(id="no", name="No"),
                ),
            ),
        ),
    )
    revision = DecisionRevision(
        id="revision",
        decision_id="decision",
        definition=definition,
        content_hash=definition_hash(definition),
        created_at=STAMP,
    )
    dataset_snapshot = DatasetSnapshot(
        id="dataset-snapshot",
        dataset_id="dataset",
        cases=(),
        content_hash=evidence_hash(()),
        created_at=STAMP,
    )
    label_snapshot = LabelSnapshot(
        id="label-snapshot",
        decision_id="decision",
        dataset_snapshot_id=dataset_snapshot.id,
        labels=(),
        content_hash=evidence_hash(()),
        created_at=STAMP,
    )
    run = RunManifest(
        id="legacy-run",
        decision_id=None,
        dataset_id=None,
        provider=None,
        decision_revision_id=revision.id,
        dataset_snapshot_id=dataset_snapshot.id,
        label_snapshot_id=label_snapshot.id,
        provider_profile_id="provider",
        provider_config_hash="0" * 64,
        adapter="fixture",
        compiler_version="not_compiled",
        requested_model="authored-model",
        mode="fixture",
        case_ids=(),
        settings=ExecutionSettings(),
        created_at=STAMP,
        operation_id="legacy-operation",
    )
    values: tuple[tuple[Collection, str, tuple[str, ...], Record], ...] = (
        (
            "project",
            "project",
            (),
            ProjectRecord(id="project", name="Project", created_at=STAMP),
        ),
        (
            "decisions",
            "decision",
            (),
            DecisionRecord(id="decision", name="Decision", latest_revision_id=revision.id),
        ),
        (
            "drafts",
            "decision",
            (),
            DecisionDraft(decision_id="decision", editor_source="{", updated_at=STAMP),
        ),
        ("revisions", revision.id, ("decision",), revision),
        (
            "datasets",
            "dataset",
            (),
            DatasetRecord(id="dataset", name="Dataset", created_at=STAMP),
        ),
        ("dataset_snapshots", dataset_snapshot.id, (), dataset_snapshot),
        ("label_snapshots", label_snapshot.id, (), label_snapshot),
        (
            "providers",
            "provider",
            (),
            ProviderProfile(
                id="provider",
                adapter="fixture",
                requested_model="authored-model",
                destination="fixture:local",
            ),
        ),
        ("runs", run.id, (), run),
    )
    return tuple(
        StoredRecord(ResourceKey(collection, resource_id, scope), dump_record(value), "0" * 64)
        for collection, resource_id, scope, value in values
    )


class RetainedSource:
    def __init__(self, records: tuple[StoredRecord, ...]) -> None:
        self.records = records
        self.active_probes = 0
        self.captures = 0
        self.closes = 0
        self.read_entries = 0
        self.read_exits = 0
        self.order: list[str] = []
        self.last_index_error: str | None = None

    def execution_active(self) -> bool:
        self.active_probes += 1
        self.order.append("active")
        return False

    @contextmanager
    def consistent_read(self) -> Iterator[None]:
        self.read_entries += 1
        self.order.append("enter_read")
        try:
            yield
        finally:
            self.read_exits += 1
            self.order.append("exit_read")

    def capture_snapshot(
        self, keys: tuple[ResourceKey, ...] | None = None
    ) -> tuple[StoredRecord, ...]:
        if self.captures:
            raise AssertionError("validation must use one captured batch")
        self.captures += 1
        self.order.append("capture")
        return self.records

    def read(self, _key: ResourceKey):
        raise AssertionError("validation must not read after capture")

    def list_ids(self, _collection: Collection, _scope: tuple[str, ...] = ()):
        raise AssertionError("validation must not list after capture")

    def commit(self, *_args: object, **_kwargs: object):
        raise AssertionError("validation must not write")

    def rebuild_index(self) -> int:
        raise AssertionError("validation must not rebuild the index")

    def close(self) -> None:
        self.closes += 1


class Clock:
    def utc_now(self) -> str:
        return STAMP

    def monotonic(self) -> float:
        return 0.0


class CaptureFailureSource(RetainedSource):
    def capture_snapshot(
        self, keys: tuple[ResourceKey, ...] | None = None
    ) -> tuple[StoredRecord, ...]:
        self.captures += 1
        self.order.append("capture")
        raise ServiceFailure(ServiceError(code="internal_error", reason="capture_failed"))


def test_validate_opened_uses_one_capture_and_returns_graph_warnings(monkeypatch) -> None:
    source = RetainedSource(captured_legacy_project())

    info = ProjectService.validate_opened(cast(ProjectBackend, source))

    assert source.active_probes == 1
    assert source.captures == 1
    assert source.read_entries == source.read_exits == 1
    assert source.order == ["active", "enter_read", "capture", "exit_read"]
    assert source.closes == 0
    assert info.project.id == "project"
    assert [warning.reason for warning in info.reference_warnings] == ["legacy_run_not_executable"]

    class Service:
        def validate(self, _path: Path):
            return info

    monkeypatch.setattr(project_commands, "projects_service", lambda: Service())
    outcome = project_commands._project_outcome(Path("project"), validate=True)
    assert outcome.data["path"] == Path("project")
    assert outcome.warnings == info.reference_warnings

    invalid_retained_source = RetainedSource(())
    with pytest.raises(ServiceFailure) as missing:
        ProjectService.validate_opened(cast(ProjectBackend, invalid_retained_source))
    assert missing.value.error.reason == "project_record_missing"
    assert invalid_retained_source.captures == 1
    assert invalid_retained_source.read_entries == invalid_retained_source.read_exits == 1
    assert invalid_retained_source.closes == 0


def test_path_open_preserves_metadata_behavior_and_path_validate_closes_after_failure() -> None:
    dangling_records = (
        StoredRecord(
            ResourceKey("project", "project"),
            dump_record(ProjectRecord(id="project", name="Project", created_at=STAMP)),
            "0" * 64,
        ),
        StoredRecord(
            ResourceKey("decisions", "decision"),
            dump_record(DecisionRecord(id="decision", name="Decision")),
            "0" * 64,
        ),
    )
    opened_source = RetainedSource(dangling_records)
    service = ProjectService(
        lambda _path, _create: cast(ProjectBackend, opened_source),
        Clock(),
        lambda: "unused",
    )

    info = service.open(Path("project"))
    assert info.reference_warnings == ()
    assert opened_source.captures == 1
    assert opened_source.read_entries == 0
    assert opened_source.closes == 1

    valid_source = RetainedSource(captured_legacy_project())
    validating_service = ProjectService(
        lambda _path, _create: cast(ProjectBackend, valid_source),
        Clock(),
        lambda: "unused",
    )
    valid_info = validating_service.validate(Path("project"))
    assert [warning.reason for warning in valid_info.reference_warnings] == [
        "legacy_run_not_executable"
    ]
    assert valid_source.captures == 1
    assert valid_source.read_entries == valid_source.read_exits == 1
    assert valid_source.closes == 1

    invalid_source = RetainedSource(())
    validating_service = ProjectService(
        lambda _path, _create: cast(ProjectBackend, invalid_source),
        Clock(),
        lambda: "unused",
    )
    with pytest.raises(ServiceFailure) as missing:
        validating_service.validate(Path("project"))
    assert missing.value.error.reason == "project_record_missing"
    assert invalid_source.captures == 1
    assert invalid_source.read_entries == invalid_source.read_exits == 1
    assert invalid_source.closes == 1


def test_capture_failure_releases_read_and_path_owner_but_not_retained_handle() -> None:
    retained = CaptureFailureSource(captured_legacy_project())
    with pytest.raises(ServiceFailure) as retained_failure:
        ProjectService.validate_opened(cast(ProjectBackend, retained))
    assert retained_failure.value.error.reason == "capture_failed"
    assert retained.captures == 1
    assert retained.read_entries == retained.read_exits == 1
    assert retained.closes == 0

    path_source = CaptureFailureSource(captured_legacy_project())
    service = ProjectService(
        lambda _path, _create: cast(ProjectBackend, path_source),
        Clock(),
        lambda: "unused",
    )
    with pytest.raises(ServiceFailure) as path_failure:
        service.validate(Path("project"))
    assert path_failure.value.error.reason == "capture_failed"
    assert path_source.captures == 1
    assert path_source.read_entries == path_source.read_exits == 1
    assert path_source.closes == 1
