import pytest

from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import parse_json, semantic_hash
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DatasetSnapshot, LabelChange, LabelRecord
from deykit.domain.label_identity import label_id


def test_crud_revision_pagination_tags_groups_and_duplicate_inputs(project):
    source, service, _, dataset = project
    first = service.add_case(
        "data",
        CaseInput(
            input_kind="text", input_source='"same"', tags=("t",), group_id="group", split="test"
        ),
        case_id="b",
        expected_dataset_etag=dataset.etag,
        operation_id="add-b",
    )
    second = service.add_case(
        "data",
        CaseInput(input_kind="text", input_source='"same"'),
        case_id="a",
        expected_dataset_etag=first.dataset.etag,
        operation_id="add-a",
    )
    assert second.dataset.etag != first.dataset.etag != dataset.etag
    assert second.dataset.record.revision_id != first.dataset.record.revision_id
    assert service.case("data", "a").duplicate_ids == ("b",)
    assert service.case("data", "b").duplicate_ids == ("a",)
    page = service.list_cases("data", limit=1)
    assert page.total == 2 and page.items[0].record.id == "a" and page.next_cursor == "a"
    assert service.list_cases("data", cursor=page.next_cursor).items[0].record.id == "b"
    assert service.list_cases("data", tag="t", group_id="group", split="test").total == 1
    assert service.list_cases("data", group_id="other").total == 0
    archived = service.archive("data", expected_etag=second.dataset.etag, operation_id="archive")
    assert service.list().total == 0 and service.list(include_archived=True).total == 1
    with pytest.raises(ServiceFailure) as failure:
        service.add_case(
            "data",
            CaseInput(input_kind="text", input_source='"x"'),
            expected_dataset_etag=archived.etag,
            operation_id="blocked",
        )
    assert failure.value.error.reason == "dataset_archived"
    restored = service.restore("data", expected_etag=archived.etag, operation_id="restore")
    renamed = service.update(
        "data",
        name="Changed",
        metadata_source='{"note":"x"}',
        expected_etag=restored.etag,
        operation_id="rename",
    )
    assert renamed.record.id == "data" and renamed.record.name == "Changed"


def test_changed_expected_dataset_revision_blocks_case_edit(project):
    _, service, _, dataset = project
    added = service.add_case(
        "data",
        CaseInput(input_kind="text", input_source='"original"'),
        expected_dataset_etag=dataset.etag,
        case_id="case",
        operation_id="add",
    )
    with pytest.raises(ServiceFailure) as failure:
        service.edit_case(
            "data",
            "case",
            CaseInput(input_kind="text", input_source='"changed"'),
            expected_dataset_etag=dataset.etag,
            expected_case_etag=added.case.etag,
            operation_id="stale",
        )
    assert failure.value.error.code == "conflict"
    assert service.case("data", "case").record.input_source == '"original"'


def test_operation_replay_keeps_original_after_later_edits_and_uses_no_new_ids(project):
    source, service, _, dataset = project
    value = CaseInput(input_kind="text", input_source='"first"')
    first = service.add_case("data", value, expected_dataset_etag=dataset.etag, operation_id="add")
    service.edit_case(
        "data",
        first.case.record.id,
        CaseInput(input_kind="text", input_source='"new"'),
        expected_dataset_etag=first.dataset.etag,
        expected_case_etag=first.case.etag,
        operation_id="edit",
    )

    def forbidden():
        raise AssertionError("new ID requested on replay")

    replay = DatasetService(source, service.clock, forbidden).add_case(
        "data", value, expected_dataset_etag=dataset.etag, operation_id="add"
    )
    assert replay.replayed and replay.case == first.case and replay.dataset == first.dataset
    with pytest.raises(ServiceFailure) as failure:
        service.add_case(
            "data",
            CaseInput(input_kind="text", input_source='"other"'),
            expected_dataset_etag=dataset.etag,
            operation_id="add",
        )
    assert failure.value.error.reason == "operation_id_conflict"


def test_case_removal_clears_labels_keeps_snapshot_and_readd_is_unlabelled(project):
    source, service, _, dataset = project
    value = CaseInput(input_kind="json", input_source='{"text":"hello"}')
    added = service.add_case(
        "data", value, case_id="case", expected_dataset_etag=dataset.etag, operation_id="add"
    )
    label = LabelRecord(
        id=label_id("case", "category"),
        decision_id="decision",
        dataset_id="data",
        case_id="case",
        question_id="category",
        input_hash=semantic_hash(parse_json(value.input_source)),
        acceptable_option_ids=("A",),
        provenance="human",
        updated_at="2026-10-05T12:00:00Z",
    )
    snapshot = DatasetSnapshot(
        id="frozen",
        dataset_id="data",
        cases=(added.case.record,),
        content_hash="a" * 64,
        created_at="2026-10-05T12:00:00Z",
    )
    source.commit(
        "label-and-snapshot",
        (
            SourceChange(
                ResourceKey("labels", label.id, ("decision", "data")), dump_record(label), None
            ),
            SourceChange(ResourceKey("dataset_snapshots", "frozen"), dump_record(snapshot), None),
        ),
    )
    removed = service.remove_case(
        "data",
        "case",
        expected_dataset_etag=added.dataset.etag,
        expected_case_etag=added.case.etag,
        operation_id="remove",
    )
    assert source.list_ids("labels", ("decision", "data")) == ()
    assert service.list_cases("data").total == 0
    changes = [
        load_record(
            LabelChange, source.read(ResourceKey("label_history", key, ("decision", "data"))).body
        )
        for key in source.list_ids("label_history", ("decision", "data"))
    ]
    assert [change.action for change in changes] == ["clear"]
    assert source.read(ResourceKey("dataset_snapshots", "frozen")).body == dump_record(snapshot)
    service.add_case(
        "data",
        value,
        case_id="case",
        expected_dataset_etag=removed.dataset.etag,
        operation_id="readd",
    )
    assert source.list_ids("labels", ("decision", "data")) == ()
    assert len(source.operation_history(ResourceKey("cases", "case", ("data",)))) == 3


def test_manual_cases_preserve_precision_and_can_fail_another_decision(project):
    _, service, _, dataset = project
    raw = '{"big":9007199254740993,"small":0.1234567890123456789}'
    added = service.add_case(
        "data",
        CaseInput(input_kind="json", input_source=raw),
        expected_dataset_etag=dataset.etag,
        operation_id="add",
    )
    assert added.case.record.input_source == raw


@pytest.mark.parametrize("limit", [0, -1, 501, True])
def test_invalid_pagination_is_structured(project, limit):
    with pytest.raises(ServiceFailure) as failure:
        project[1].list_cases("data", limit=limit)
    assert failure.value.error.reason == "invalid_page_limit"


def test_stable_label_id_exact_oracle():
    assert (
        label_id("case", "category")
        == "label-cb2f9462de4923c7da53704a6b52a56f34df05da3bb6b971a06dad48c08848cc"
    )
    assert label_id("a-b", "c") != label_id("a", "b-c")


def test_remove_clears_labels_across_active_and_archived_decisions(project):
    from deykit.contracts.records import DecisionRecord

    source, service, _, dataset = project
    added = service.add_case(
        "data",
        CaseInput(input_kind="text", input_source='"hello"'),
        case_id="case",
        expected_dataset_etag=dataset.etag,
        operation_id="add",
    )
    changes = [
        SourceChange(
            ResourceKey("decisions", "archived"),
            dump_record(DecisionRecord(id="archived", name="Archived", archived=True)),
            None,
        )
    ]
    for decision in ("decision", "archived"):
        label = LabelRecord(
            id=label_id("case", "q"),
            decision_id=decision,
            dataset_id="data",
            case_id="case",
            question_id="q",
            input_hash=semantic_hash("hello"),
            acceptable_option_ids=("A",),
            provenance="human",
            updated_at="2026-10-05T12:00:00Z",
        )
        changes.append(
            SourceChange(
                ResourceKey("labels", label.id, (decision, "data")), dump_record(label), None
            )
        )
    source.commit("labels", tuple(changes))
    service.remove_case(
        "data",
        "case",
        expected_dataset_etag=added.dataset.etag,
        expected_case_etag=added.case.etag,
        operation_id="remove",
    )
    for decision in ("decision", "archived"):
        assert source.list_ids("labels", (decision, "data")) == ()
        assert len(source.list_ids("label_history", (decision, "data"))) == 1


def test_invalid_direct_request_traceback_never_contains_input(project):
    import traceback

    _, service, _, dataset = project
    invalid = CaseInput(input_kind="text", input_source='"x"').model_copy(
        update={"input_source": "PRIVATE_INPUT_SENTINEL"}
    )
    with pytest.raises(ServiceFailure) as failure:
        service.add_case(
            "data", invalid, expected_dataset_etag=dataset.etag, operation_id="invalid"
        )
    assert failure.value.error.reason == "invalid_case"
    assert "PRIVATE_INPUT_SENTINEL" not in "".join(traceback.format_exception(failure.value))
