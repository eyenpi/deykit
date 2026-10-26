"""Large owned reports retain ordinary journal, copy and replay guarantees."""

import json
import shutil

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import JsonError
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft, ProjectRecord, ReportRecord
from deykit.storage import FileProjectSource

STAMP = "2026-10-26T00:00:00Z"


@pytest.mark.parametrize("packed", [False, True])
@pytest.mark.parametrize("crash_at", ["decided", "applied:0"])
def test_large_report_recovers_reopens_copies_and_replays(tmp_path, packed, crash_at):
    root = tmp_path / "report project é"
    with FileProjectSource(root, create=True) as source:
        source.commit(
            "init",
            (
                SourceChange(
                    ResourceKey("project", "p"),
                    dump_record(ProjectRecord(id="p", name="Report project", created_at=STAMP)),
                    None,
                ),
            ),
        )
    record = ReportRecord(
        id="large",
        evaluation_ids=(),
        result_snapshot_ids=(),
        label_snapshot_ids=(),
        content_source=json.dumps('"' * (9 * 1024 * 1024)),
        content_hash="0" * 64,
        created_at=STAMP,
    )
    key = ResourceKey("reports", record.id)
    changes = (SourceChange(key, dump_record(record), None),)
    # Escaping the 18 MiB content makes its stored envelope exceed the former
    # 32 MiB pack-read limit while remaining within the report-specific budget.
    assert 32 * 1024 * 1024 < len(changes[0].body) < 40 * 1024 * 1024
    if packed:
        changes += tuple(
            SourceChange(
                ResourceKey("reports", f"small-{i}"),
                dump_record(record.model_copy(update={"id": f"small-{i}", "content_source": "{}"})),
                None,
            )
            for i in range(15)
        )

    def interrupted(point):
        if point == crash_at:
            raise OSError("authored interruption")

    with FileProjectSource(root, fault_hook=interrupted) as source:
        with pytest.raises(ServiceFailure):
            source.commit("large-report", changes)
    with FileProjectSource(root) as source:
        saved = source.read(key)
        assert saved.body == changes[0].body
        assert source.commit("large-report", changes).replayed
        assert source.operation_history(key)[0].after == saved
        assert source.rebuild_index() == len(changes) + 1
    copied = tmp_path / "copied project ü"
    shutil.copytree(root, copied)
    shutil.rmtree(copied / ".deykit")
    with FileProjectSource(copied) as source:
        assert source.read(key) == saved
        assert source.commit("large-report", changes).replayed
        assert len(source.capture_snapshot()) == len(changes) + 1


def test_ordinary_record_envelopes_keep_sixteen_mebibyte_limit():
    record = DecisionDraft(
        decision_id="d", editor_source="x" * (17 * 1024 * 1024), updated_at=STAMP
    )
    with pytest.raises(JsonError, match="record_resource_limit"):
        dump_record(record)
