from dataclasses import replace
from decimal import localcontext
from itertools import permutations

import pytest

from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.application.splits import (
    SplitService,
    admit_dataset_snapshot,
    split_snapshot_hash,
)
from deykit.contracts.codec import dump_record
from deykit.contracts.evidence import evidence_hash
from deykit.contracts.json_value import (
    JsonDocument,
    bytes_hash,
    parse_json,
    semantic_hash,
)
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import CaseRecord, DatasetSnapshot
from deykit.domain.splits import assign, connected_groups, ratios


def case(key, text=None, **kwargs):
    return CaseRecord(
        id=key,
        dataset_id="data",
        input_kind="json",
        input_source=text or '{"value":"' + key + '"}',
        **kwargs,
    )


def test_a15_connected_components_transitive_duplicates_groups_missing_ancestors():
    records = (
        case("a", group_id="group"),
        case("b", group_id="group", derived_from=("c",)),
        case("c", '{"x":1.00}'),
        case("d", '{"x":1e0}'),
        case("e", derived_from=("missing", "d")),
        case("f", derived_from=("missing",)),
        case("g"),
        case("h"),
        case("i", derived_from=("cycle",)),
        case("cycle", derived_from=("i",)),
    )
    expected = (("a", "b", "c", "d", "e", "f"), ("cycle", "i"), ("g",), ("h",))
    assert connected_groups(records) == expected
    first = assign(records, 42)
    mapping = dict(first)
    for group in expected:
        assert len({mapping[key] for key in group}) == 1
    assert assign(tuple(reversed(records)), 42) == first
    for ordering in permutations(records[:4]):
        assert assign(ordering + records[4:], 42) == first


def test_exact_ratios_zero_destinations_and_context_independent_arithmetic():
    source = (
        '{"development":0.800000000000000000000000000001,'
        '"calibration":0,"test":0.199999999999999999999999999999}'
    )
    records = tuple(case(f"case-{i}") for i in range(10))
    expected = assign(records, 4, source)
    with localcontext() as context:
        context.prec = 2
        assert assign(records, 4, source) == expected
        assert sum(ratios(source)) == 1
    assert dict(
        (s, sum(value == s for _, value in expected))
        for s in ("development", "calibration", "test")
    ) == {"development": 8, "calibration": 0, "test": 2}
    assert all(value == "development" for _, value in assign(records, 1, '{"development":1}'))
    assert all(value == "calibration" for _, value in assign(records, 1, '{"calibration":1}'))


@pytest.mark.parametrize(
    "source",
    [
        '{"development":0.1,"test":0.89999999999999999999999999999}',
        '{"development":-0.1,"test":1.1}',
        '{"development":true}',
        '{"development":"1"}',
        '{"other":1}',
        "{}",
        "[]",
        '{"test":NaN}',
        '{"test":1,"test":0}',
    ],
)
def test_malformed_ratios_fail_exactly(source):
    with pytest.raises(ValueError):
        ratios(source)


def test_split_hash_profile_remains_distinct_from_ordinary_snapshot_profile():
    frozen_cases = (case("frozen", split="development"),)
    selection_source = (
        '{"snapshot_hash_profile":"deykit-split-snapshot-v1",'
        '"algorithm":"connected-greedy-squared-v1","seed":4,'
        '"ratios":{"development":1},"assignments":[["frozen","development"]],'
        '"groups":[["frozen"]],"counts":{"development":1,"calibration":0,"test":0},'
        '"input_identity":"' + "0" * 64 + '","dataset_etag":"' + "1" * 64 + '"}'
    )
    case_bytes = tuple(dump_record(item) for item in frozen_cases)
    parsed_selection = parse_json(selection_source)
    expected_split_hash = semantic_hash(
        {
            "profile": "deykit-split-snapshot-v1",
            "case_bytes_hashes": [bytes_hash(body) for body in case_bytes],
            "selection_hash": semantic_hash(parsed_selection),
        }
    )
    assert split_snapshot_hash(frozen_cases, selection_source) == expected_split_hash

    split_snapshot = DatasetSnapshot(
        id="split-snapshot",
        dataset_id="data",
        cases=frozen_cases,
        content_hash=expected_split_hash,
        created_at="2026-10-05T12:00:00Z",
        selection_source=selection_source,
    )
    ordinary_snapshot = DatasetSnapshot(
        id="ordinary-snapshot",
        dataset_id="data",
        cases=frozen_cases,
        content_hash=evidence_hash(tuple(dump_record(item) for item in frozen_cases)),
        created_at="2026-10-05T12:00:00Z",
        selection_source="{}",
    )
    assert split_snapshot.content_hash != ordinary_snapshot.content_hash
    assert admit_dataset_snapshot(split_snapshot) == split_snapshot
    assert admit_dataset_snapshot(ordinary_snapshot) == ordinary_snapshot


def test_split_snapshot_counts_are_bounded_before_integer_conversion():
    frozen_cases = (case("frozen", split="development"),)
    selection_source = (
        '{"snapshot_hash_profile":"deykit-split-snapshot-v1",'
        '"algorithm":"connected-greedy-squared-v1","seed":4,'
        '"ratios":{"development":1},"assignments":[["frozen","development"]],'
        '"groups":[["frozen"]],"counts":{"development":999999999999999999999,'
        '"calibration":0,"test":0},"input_identity":"' + "0" * 64
        + '","dataset_etag":"' + "1" * 64 + '"}'
    )
    snapshot = DatasetSnapshot(
        id="bad-count-snapshot",
        dataset_id="data",
        cases=frozen_cases,
        content_hash=split_snapshot_hash(frozen_cases, selection_source),
        created_at="2026-10-05T12:00:00Z",
        selection_source=selection_source,
    )

    with pytest.raises(ServiceFailure) as invalid_count:
        admit_dataset_snapshot(snapshot)

    assert invalid_count.value.error.reason == "invalid_split_counts"


def test_unknown_snapshot_hash_profile_is_not_admitted_as_ordinary_legacy_hash():
    frozen_cases = (case("frozen", split="development"),)
    selection_source = '{"snapshot_hash_profile":"deykit-split-snapshot-v99"}'
    snapshot = DatasetSnapshot(
        id="unknown-profile-snapshot",
        dataset_id="data",
        cases=frozen_cases,
        content_hash=evidence_hash(tuple(dump_record(item) for item in frozen_cases)),
        created_at="2026-10-05T12:00:00Z",
        selection_source=selection_source,
    )

    with pytest.raises(ServiceFailure) as unknown_profile:
        admit_dataset_snapshot(snapshot)

    assert unknown_profile.value.error.reason == "unknown_snapshot_hash_profile"


def split_service(project):
    source, datasets, _, _ = project
    return SplitService(source, datasets.clock, datasets.id_factory)


def populate(project):
    _, datasets, _, _ = project
    for record in (
        case("a", group_id="pair"),
        case("b", group_id="pair"),
        case("c"),
        case("d"),
        case("e"),
    ):
        datasets.add_case(
            "data",
            CaseInput(
                **{
                    key: value
                    for key, value in record.model_dump().items()
                    if key not in {"schema_version", "hash_format", "id", "dataset_id"}
                }
            ),
            case_id=record.id,
            expected_dataset_etag=datasets.read("data").etag,
            operation_id="add-" + record.id,
        )


def test_preview_no_writes_atomic_commit_actual_counts_and_immutable_evidence(project):
    populate(project)
    source, datasets, _, _ = project
    splits = split_service(project)
    old = datasets.read("data")
    preview = splits.preview("data", seed=10)
    assert datasets.read("data") == old
    assert source.list_ids("dataset_snapshots") == ()
    assert sum(count for _, count in preview.counts) == 5
    assert dict(preview.assignments)["a"] == dict(preview.assignments)["b"]
    first = splits.commit(preview, operation_id="split")
    assert first.dataset.record.revision_id != old.record.revision_id
    snapshot_key = ResourceKey("dataset_snapshots", first.snapshot.id)
    frozen = source.read(snapshot_key)
    evidence = parse_json(first.snapshot.selection_source)
    assert evidence["seed"] == 10
    assert evidence["algorithm"] == "connected-greedy-squared-v1"
    assert evidence["input_identity"] == preview.input_identity
    assert {c.id: c.split for c in first.snapshot.cases} == dict(preview.assignments)
    explicit = splits.preview(
        "data", assignments=tuple((key, "test") for key, _ in preview.assignments)
    )
    splits.commit(explicit, operation_id="all-test")
    assert source.read(snapshot_key) == frozen
    replay = splits.commit(preview, operation_id="split")
    assert replay.replayed and replay.snapshot == first.snapshot
    assert all(c.record.split == "test" for c in datasets.list_cases("data").items)
    with pytest.raises(ServiceFailure):
        splits.commit(replace(preview, seed=11), operation_id="split")


@pytest.mark.parametrize(
    "assignments",
    [
        (("a", "development"),),
        (("a", "development"), ("b", "test"), ("c", "test"), ("d", "test"), ("e", "test")),
        (("a", "test"), ("b", "test"), ("c", "test"), ("d", "test"), ("extra", "test")),
        (("a", "test"), ("b", "test"), ("c", "test"), ("d", "test"), ("e", "wrong")),
        (("a", "test"), ("a", "test"), ("b", "test"), ("c", "test"), ("d", "test"), ("e", "test")),
    ],
)
def test_explicit_assignments_reject_missing_unknown_duplicates_and_group_conflicts(
    project, assignments
):
    populate(project)
    splits = split_service(project)
    with pytest.raises(ServiceFailure):
        splits.preview("data", assignments=assignments)
    assert project[0].list_ids("dataset_snapshots") == ()


def test_stale_or_tampered_preview_writes_nothing(project):
    populate(project)
    source, datasets, _, _ = project
    splits = split_service(project)
    preview = splits.preview("data")
    with pytest.raises(ServiceFailure):
        splits.commit(replace(preview, counts=(("test", 999),)), operation_id="tampered")
    item = datasets.case("data", "a")
    datasets.edit_case(
        "data",
        "a",
        CaseInput(input_kind="text", input_source='"changed"'),
        expected_dataset_etag=datasets.read("data").etag,
        expected_case_etag=item.etag,
        operation_id="edited",
    )
    with pytest.raises(ServiceFailure):
        splits.commit(preview, operation_id="stale")
    assert source.list_ids("dataset_snapshots") == ()


def test_empty_dataset_split_is_recorded_and_exact_duplicate_values_stay_together(project):
    splits = split_service(project)
    preview = splits.preview("data")
    result = splits.commit(preview, operation_id="empty")
    assert result.snapshot.cases == () and sum(c for _, c in preview.counts) == 0
    precise = (
        case("a", '{"x":9007199254740993.000000000000001}'),
        case("b", '{"x":9007199254740993.0000000000000010}'),
        case("c", '{"x":9007199254740993.000000000000002}'),
    )
    assert connected_groups(precise) == (("a", "b"), ("c",))
    assert (
        JsonDocument(precise[0].input_source).value != JsonDocument(precise[2].input_source).value
    )


@pytest.mark.parametrize(
    "assignments", [None, (("a",),), (("a", "test", "extra"),), ((123, "test"),), (["a", "test"],)]
)
def test_malformed_assignment_shapes_have_safe_failures(project, assignments):
    splits = split_service(project)
    with pytest.raises(ServiceFailure):
        if assignments is None:
            splits.preview("data", seed=True)
        else:
            splits.preview("data", assignments=assignments)
