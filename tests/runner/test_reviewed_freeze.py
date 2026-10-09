"""Focused receipts and freeze checks for reviewed run/group starts."""

import asyncio
import hashlib
from dataclasses import replace

import pytest

from deykit.application.checks import CheckRequest, CheckService
from deykit.application.diagnostics import (
    ChoiceOrderRequest,
    DiagnosticService,
    diagnostic_snapshot_from_records,
)
from deykit.application.errors import ServiceFailure
from deykit.application.labels import LabelService
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.execution_groups import ExecutionGroup
from deykit.contracts.json_value import bytes_hash, canonical_bytes, dump_json, semantic_hash
from deykit.contracts.ports import CompilerIdentity, ResourceKey, SourceChange, StoredRecord
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    ExecutionSettings,
    FixtureSet,
    ProviderProfile,
    RegressionRecord,
)
from deykit.domain.definitions import definition_hash
from deykit.providers.fixtures import fixture_set_hash
from deykit.regressions.evidence import regression_hash
from deykit.reports.group_projection import _selection as report_group_selection
from deykit.runner.group_selection import (
    decode_group_start_selection,
    encode_group_start_selection,
    group_start_intent,
)
from deykit.runner.planner import RunPlan, RunRequest, start_intent
from deykit.runner.review import run_review_hash, run_review_payload


def replace_record(source, key, value, *, operation_id):
    current = source.read(key)
    assert current is not None
    source.commit(
        operation_id,
        (SourceChange(key, dump_record(value), current.etag),),
    )


def legacy_hash(value):
    """Independent vector helper using only the format's canonical hash rule."""
    return hashlib.sha256(b"deykit-json-v1\n" + canonical_bytes(value)).hexdigest()


def request() -> RunRequest:
    return RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="fixture",
        fixture_set_id="set",
    )


def test_minimal_review_payload_matches_normative_literal_and_fixed_digest():
    selection = request()
    definition = ChoiceDefinition(
        input_kind="text",
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose.",
                options=(ChoiceOption(id="yes", name="Yes"), ChoiceOption(id="no", name="No")),
            ),
        ),
    )
    provider = ProviderProfile(
        id="fixture-profile",
        adapter="fixture",
        requested_model="authored-v1",
        destination="fixture:jev-choice",
    )
    plan = RunPlan(
        selection,
        definition,
        definition_hash(definition),
        (),
        (),
        (),
        (),
        provider,
        (),
        "unused-context-hash",
        (StoredRecord(ResourceKey("drafts", "decision"), b"{}", bytes_hash(b"{}")),),
        CompilerIdentity("jev-choice", "1"),
    )
    expected_payload = {
        "kind": "run-review-v1",
        "selection": {
            "decision_id": "decision",
            "dataset_id": "data",
            "mode": "fixture",
            "provider_id": None,
            "fixture_set_id": "set",
            "revision_id": None,
            "split": "all",
            "case_ids": [],
            "option_order": None,
            "regression_ids": [],
            "settings": {
                "max_attempts": 100,
                "concurrency": 2,
                "timeout_seconds": 60,
                "deadline_seconds": 600,
                "max_retries_per_case": 1,
            },
        },
        "records": [
            [
                "drafts",
                [],
                "decision",
                "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
                "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            ]
        ],
        "definition": [
            "159ca8d30fceb9ea03546e10479815ac90093028565a4f07d9e1d15f29109df4",
            "8d4891e6b9918955ec2d15c7d3b4c6893f2414454fede045a3d642b6c2b3fa92",
        ],
        "provider": "e6236c6f399b6c5a8ba282d174fe5a98287c0d5114cf09a259c52e4e77ff2a43",
        "compiler": ["jev-choice", "1"],
        "cases": [],
        "labels": [],
        "development_cases": [],
        "development_labels": [],
        "prepared": [],
    }
    assert run_review_payload(plan) == expected_payload
    assert run_review_hash(plan) == (
        "33054a543fa49b5717b0ae36684cff3d7a8e60313a4c343fde9ae697ff109eaa"
    )


def test_legacy_run_intent_matches_fixed_pre_review_vector():
    old_payload = {
        "command": "run.start",
        "request": {
            "decision_id": "decision",
            "dataset_id": "data",
            "mode": "fixture",
            "provider_id": None,
            "fixture_set_id": "set",
            "revision_id": None,
            "split": "all",
            "case_ids": [],
            "option_order": None,
            "regression_ids": [],
            "settings": {
                "max_attempts": 100,
                "concurrency": 2,
                "timeout_seconds": 60,
                "deadline_seconds": 600,
                "max_retries_per_case": 1,
            },
        },
    }
    expected = "04a4d55452102accc3500fd9d315c093bd6020b79ecc85ebe8f308765e2c27a0"
    assert legacy_hash(old_payload) == expected
    assert start_intent(request(), None) == expected


def test_reviewed_run_hash_binds_exact_captured_plan_and_stale_start_has_no_effects(setup):
    source, runner, factory, _ = setup(count=1)
    plan = runner.planner.prepare(request())
    preview_hash = run_review_hash(plan)
    payload = run_review_payload(plan)
    assert payload["kind"] == "run-review-v1"
    assert payload["compiler"] == ["jev-choice", "1"]
    assert payload["records"]
    assert preview_hash == semantic_hash(payload)

    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            runner.start(
                request(), operation_id="stale-run", expected_review_context_hash="0" * 64
            )
        )
    assert failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before
    assert factory.calls == []


def test_all_invalid_plan_still_binds_resolved_compiler_identity(setup):
    _source, runner, factory, _ = setup(count=1, invalid=(0,))
    first = runner.planner.prepare(request())
    first_hash = run_review_hash(first)
    assert first.initial_requests == 0
    assert first.prepared[0].error is not None

    class AlternateCompiler:
        review_identity = CompilerIdentity("alternate-choice", "9")

        def compile(self, *_args):
            raise AssertionError("invalid input must not reach the compiler")

    factory.compiler = AlternateCompiler()
    second = runner.planner.prepare(request())
    assert second.initial_requests == 0
    assert second.review_compiler == CompilerIdentity("alternate-choice", "9")
    assert run_review_hash(second) != first_hash
    assert factory.calls == []


def test_original_reviewed_run_replays_before_mutable_preflight(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    review_hash = runner.preview(request()).review_context_hash
    original = asyncio.run(
        runner.start(
            request(), operation_id="reviewed-run", expected_review_context_hash=review_hash
        )
    )
    stored = source.read(ResourceKey("cases", "case-00", ("data",)))
    case = load_record(CaseRecord, stored.body)
    source.commit(
        "edit-after-freeze",
        (
            SourceChange(
                stored.key,
                dump_record(case.model_copy(update={"input_source": '{"text":"later"}'})),
                stored.etag,
            ),
        ),
    )
    replay = asyncio.run(
        runner.start(
            request(), operation_id="reviewed-run", expected_review_context_hash=review_hash
        )
    )
    assert replay.run_id == original.run_id
    assert replay.replayed
    assert len(factory.calls) == 1

    def forbidden_prepare(*_args, **_kwargs):
        raise AssertionError("receipt replay must precede current planning")

    monkeypatch.setattr(runner.planner, "prepare", forbidden_prepare)
    for changed_request, changed_hash in (
        (request(), "f" * 64),
        (request().model_copy(update={"option_order": ("no", "yes")}), review_hash),
    ):
        with pytest.raises(ServiceFailure):
            asyncio.run(
                runner.start(
                    changed_request,
                    operation_id="reviewed-run",
                    expected_review_context_hash=changed_hash,
                )
            )
    assert len(factory.calls) == 1


@pytest.mark.parametrize("change", ["profile", "compiler"])
def test_reviewed_run_rejects_real_context_mutations_before_effects(setup, change):
    source, runner, factory, _ = setup(count=1, invalid=(0,) if change == "compiler" else ())
    selected = request()
    if change == "profile":
        profile = ProviderProfile(
            id="authored",
            adapter="fixture",
            requested_model="authored-v1",
            destination="fixture:jev-choice",
        )
        source.commit(
            "add-review-profile",
            (SourceChange(ResourceKey("providers", "authored"), dump_record(profile), None),),
        )
        selected = selected.model_copy(update={"provider_id": "authored"})
    preview_hash = runner.preview(selected).review_context_hash
    if change == "profile":
        stored = source.read(ResourceKey("providers", "authored"))
        assert stored is not None
        profile = load_record(ProviderProfile, stored.body)
        replace_record(
            source,
            stored.key,
            profile.model_copy(update={"requested_model": "authored-v2"}),
            operation_id="edit-review-profile",
        )
    else:
        class AlternateCompiler:
            review_identity = CompilerIdentity("alternate-choice", "9")

            def compile(self, *_args):
                raise AssertionError("invalid case must not reach compiler")

        factory.compiler = AlternateCompiler()

    before = source.capture_snapshot()
    callbacks = []
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            runner.start(
                selected,
                operation_id=f"stale-{change}",
                expected_review_context_hash=preview_hash,
                on_created=callbacks.append,
            )
        )
    assert failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before
    assert source.list_ids("runs") == ()
    assert callbacks == []
    assert not runner.execution.execution_active()
    assert factory.calls == []


def test_reviewed_start_rejects_same_etag_fixture_body_substitution_before_effects(
    setup, monkeypatch
):
    source, runner, factory, _ = setup(count=1)
    preview_hash = runner.preview(request()).review_context_hash
    original_capture = source.capture_snapshot
    original_records = original_capture()
    fixture_record = next(
        record
        for record in original_records
        if record.key == ResourceKey("fixtures", "set")
    )
    fixture = load_record(FixtureSet, fixture_record.body)
    substituted_fixture = fixture.model_copy(update={"name": "Renamed evidence"})
    assert fixture_set_hash(substituted_fixture) == fixture.content_hash
    faulted = tuple(
        replace(record, body=dump_record(substituted_fixture))
        if record.key == fixture_record.key
        else record
        for record in source.capture_snapshot()
    )
    captured = next(record for record in faulted if record.key == fixture_record.key)
    assert captured.etag == fixture_record.etag

    commits = []
    original_commit = source.commit

    def track_commit(*args, **kwargs):
        commits.append((args, kwargs))
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(source, "capture_snapshot", lambda: faulted)
    monkeypatch.setattr(source, "commit", track_commit)
    callbacks = []

    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            runner.start(
                request(),
                operation_id="stale-fixture-bytes",
                expected_review_context_hash=preview_hash,
                on_created=callbacks.append,
            )
        )
    assert failure.value.error.code == "conflict"
    assert original_capture() == original_records
    assert commits == []
    assert source.list_ids("runs") == ()
    assert callbacks == []
    assert factory.calls == []


@pytest.mark.parametrize(
    "changed_request",
    [
        request().model_copy(update={"settings": ExecutionSettings(max_attempts=99)}),
        request().model_copy(update={"option_order": ("no", "yes")}),
    ],
)
def test_reviewed_run_rejects_changed_cap_or_order_before_effects(setup, changed_request):
    source, runner, factory, _ = setup(count=1)
    preview_hash = runner.preview(request()).review_context_hash
    before = source.capture_snapshot()
    callbacks = []
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            runner.start(
                changed_request,
                operation_id="stale-request-shape",
                expected_review_context_hash=preview_hash,
                on_created=callbacks.append,
            )
        )
    assert failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before
    assert source.list_ids("runs") == ()
    assert callbacks == [] and factory.calls == []
    assert not runner.execution.execution_active()


def test_group_selection_codec_preserves_legacy_bytes_and_binds_review_hash():
    source = '{ "kind" : "choice_order", "request" : {"seed":0} }\n'
    legacy = encode_group_start_selection(source)
    assert legacy.stored_source == source
    assert legacy.expected_review_context_hash is None
    old_payload = {
        "command": "execution_group.start",
        "selection": {"kind": "choice_order", "request": {"seed": 0}},
    }
    expected_legacy_intent = "bf846fe067acb823d540901ab09cdeb9e3fab468769355211748b13942bd319b"
    assert legacy_hash(old_payload) == expected_legacy_intent
    assert group_start_intent(legacy) == expected_legacy_intent

    reviewed = encode_group_start_selection(
        source, expected_review_context_hash="a" * 64
    )
    decoded = decode_group_start_selection(reviewed.stored_source, expected_kind="choice_order")
    assert decoded.original_selection == legacy.original_selection
    assert decoded.expected_review_context_hash == "a" * 64
    assert group_start_intent(decoded) == semantic_hash(
        {
            "command": "execution_group.start.reviewed-v1",
            "selection": legacy.original_selection,
            "expected_review_context_hash": "a" * 64,
        }
    )


@pytest.mark.parametrize(
    "review",
    [
        {"version": "group-start-review-v2", "expected_review_context_hash": "a" * 64},
        {"version": "group-start-review-v1", "expected_review_context_hash": "A" * 64},
        {
            "version": "group-start-review-v1",
            "expected_review_context_hash": "a" * 64,
            "extra": True,
        },
        {"version": "group-start-review-v1"},
        {"version": "group-start-review-v1", "expected_review_context_hash": "a" * 63},
    ],
)
def test_reviewed_group_codec_rejects_malformed_version_keys_and_hashes(review):
    source = dump_json({"kind": "choice_order", "request": {}, "review": review})
    with pytest.raises(ServiceFailure):
        decode_group_start_selection(source, expected_kind="choice_order")


def test_stale_reviewed_group_start_has_no_group_or_dispatch_effects(setup):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    request_value = ChoiceOrderRequest(run=request())
    review_hash = service.preview(request_value).review_context_hash
    stored = source.read(ResourceKey("cases", "case-00", ("data",)))
    case = load_record(CaseRecord, stored.body)
    source.commit(
        "edit-before-freeze",
        (
            SourceChange(
                stored.key,
                dump_record(case.model_copy(update={"input_source": '{"text":"later"}'})),
                stored.etag,
            ),
        ),
    )
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            service.start(
                request_value,
                operation_id="stale-group",
                expected_review_context_hash=review_hash,
            )
        )
    assert failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before
    assert source.list_ids("execution_groups") == ()
    assert source.list_ids("runs") == ()
    assert factory.calls == []


def test_original_reviewed_group_replays_before_mutable_preflight(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    request_value = ChoiceOrderRequest(run=request(), orders=2, seed=19)
    review_hash = service.preview(request_value).review_context_hash
    original = asyncio.run(
        service.start(
            request_value,
            operation_id="reviewed-group",
            expected_review_context_hash=review_hash,
        )
    )
    stored = source.read(ResourceKey("cases", "case-00", ("data",)))
    assert stored is not None
    case = load_record(CaseRecord, stored.body)
    replace_record(
        source,
        stored.key,
        case.model_copy(update={"input_source": '{"text":"later"}'}),
        operation_id="edit-after-group-freeze",
    )

    def forbidden_prepare(*_args, **_kwargs):
        raise AssertionError("group receipt replay must precede current planning")

    monkeypatch.setattr(service, "_plan", forbidden_prepare)
    replay = asyncio.run(
        service.start(
            request_value,
            operation_id="reviewed-group",
            expected_review_context_hash=review_hash,
        )
    )
    assert replay.group.group_id == original.group.group_id
    assert replay.group.replayed
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure):
        asyncio.run(
            service.start(
                request_value,
                operation_id="reviewed-group",
                expected_review_context_hash="b" * 64,
            )
        )
    changed_selection = request_value.model_copy(update={"seed": 20})
    with pytest.raises(ServiceFailure):
        asyncio.run(
            service.start(
                changed_selection,
                operation_id="reviewed-group",
                expected_review_context_hash=review_hash,
            )
        )
    assert source.capture_snapshot() == before
    assert len(factory.calls) == 2


def test_same_etag_regression_provenance_substitution_conflicts_before_check_group_writes(
    setup, monkeypatch
):
    source, runner, factory, clock = setup(count=1)
    origin = asyncio.run(runner.start(request(), operation_id="provenance-origin"))
    regressions = RegressionService(source, clock, lambda: "review-regression")
    regressions.add(
        RegressionAdd(
            run_id=origin.run_id,
            case_id="case-00",
            acceptable_option_ids=("yes",),
            reason="Pinned expected answer",
        ),
        operation_id="save-review-regression",
    )
    service = CheckService(runner)
    check_request = CheckRequest(
        decision_id="decision", mode="fixture", fixture_set_id="set"
    )
    preview_hash = service.preview(check_request).review_context_hash
    original_capture = source.capture_snapshot
    original_records = original_capture()
    stored = next(
        record
        for record in original_records
        if record.key == ResourceKey("regressions", "review-regression")
    )
    regression = load_record(RegressionRecord, stored.body)
    changed = regression.model_copy(update={"provenance": "authored_fixture"})
    substituted = changed.model_copy(update={"content_hash": regression_hash(changed)})
    faulted = tuple(
        replace(record, body=dump_record(substituted))
        if record.key == stored.key
        else record
        for record in original_records
    )
    captured = next(record for record in faulted if record.key == stored.key)
    assert captured.etag == stored.etag
    commits = []
    original_commit = source.commit

    def track_commit(*args, **kwargs):
        commits.append((args, kwargs))
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(source, "capture_snapshot", lambda: faulted)
    monkeypatch.setattr(source, "commit", track_commit)
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            service.start(
                check_request,
                operation_id="stale-regression-provenance",
                expected_review_context_hash=preview_hash,
            )
        )
    assert failure.value.error.code == "conflict"
    assert original_capture() == original_records
    assert commits == []
    assert source.list_ids("execution_groups") == ()
    assert len(source.list_ids("runs")) == 1
    assert len(factory.calls) == 1


def test_default_check_review_binds_label_provenance_and_regression_membership(setup):
    source, runner, factory, clock = setup(count=1)
    label_ids = iter(("label-change-1", "label-change-2"))
    labels = LabelService(source, clock, lambda: next(label_ids))
    initial_review = labels.read("decision", "data", "case-00").review
    labels.set(
        initial_review,
        ("yes",),
        provenance="human",
        operation_id="save-label",
    )
    run_review_hash_before_label_edit = runner.preview(request()).review_context_hash
    current_review = labels.read("decision", "data", "case-00").review
    labels.set(
        current_review,
        ("yes",),
        provenance="authored_fixture",
        operation_id="change-label-provenance",
    )
    before_label_stale_start = source.capture_snapshot()
    label_callbacks = []
    with pytest.raises(ServiceFailure) as label_failure:
        asyncio.run(
            runner.start(
                request(),
                operation_id="stale-label-provenance",
                expected_review_context_hash=run_review_hash_before_label_edit,
                on_created=label_callbacks.append,
            )
        )
    assert label_failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before_label_stale_start
    assert source.list_ids("runs") == ()
    assert label_callbacks == []
    assert factory.calls == []

    origin = asyncio.run(runner.start(request(), operation_id="membership-origin"))
    ids = iter(("reg-a", "reg-b", "remove-a"))
    regressions = RegressionService(source, clock, lambda: next(ids))
    for option in ("yes", "no"):
        regressions.add(
            RegressionAdd(
                run_id=origin.run_id,
                case_id="case-00",
                acceptable_option_ids=(option,),
                reason="Separate oracle",
            ),
            operation_id="save-" + option,
        )
    service = CheckService(runner)
    check_request = CheckRequest(
        decision_id="decision", mode="fixture", fixture_set_id="set"
    )
    preview_hash = service.preview(check_request).review_context_hash
    regressions.remove("reg-a", decision_id="decision", operation_id="remove-reg-a")
    before = source.capture_snapshot()
    membership = [
        record
        for record in before
        if record.key.collection in {"regressions", "regression_removals"}
    ]
    regression_ids = {
        record.key.resource_id
        for record in membership
        if record.key.collection == "regressions"
    }
    assert regression_ids == {
        "reg-a",
        "reg-b",
    }
    assert any(record.key.collection == "regression_removals" for record in membership)
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            service.start(
                check_request,
                operation_id="stale-check-membership",
                expected_review_context_hash=preview_hash,
            )
        )
    assert failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before
    assert source.list_ids("execution_groups") == ()
    assert len(source.list_ids("runs")) == 1
    assert len(factory.calls) == 1


def test_legacy_group_selection_remains_admitted_and_report_readable(setup):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    request_value = ChoiceOrderRequest(run=request(), orders=2, seed=23)
    original_source = service._selection_source(request_value)
    progress = asyncio.run(service.start(request_value, operation_id="legacy-report-group"))
    stored = source.read(ResourceKey("execution_groups", progress.group.group_id))
    assert stored is not None
    group = load_record(ExecutionGroup, stored.body)
    assert group.selection_source == original_source
    assert group.intent_hash == legacy_hash(
        {
            "command": "execution_group.start",
            "selection": {
                "kind": "choice_order",
                "request": request_value.model_dump(mode="json"),
            },
        }
    )
    frozen = diagnostic_snapshot_from_records(
        source.capture_snapshot(), progress.group.snapshot_id
    )
    orders = tuple(member.manifest.option_order for member in frozen.members)
    assert report_group_selection(frozen) == (23, "deykit-choice-order-v1", orders)
    assert factory.calls


def test_same_etag_body_substitution_conflicts_in_admission_port(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    plan = runner.planner.prepare(request())
    review_hash = run_review_hash(plan)
    original_capture = source.capture_snapshot
    original_records = original_capture()
    case_record = next(
        record
        for record in plan.review_records
        if record.key == ResourceKey("cases", "case-00", ("data",))
    )
    case = load_record(CaseRecord, case_record.body)
    substituted = case.model_copy(update={"input_source": '{"text":"same-etag substitution"}'})
    faulted = tuple(
        replace(record, body=dump_record(substituted))
        if record.key == case_record.key
        else record
        for record in original_records
    )
    captured = next(record for record in faulted if record.key == case_record.key)
    assert captured.etag == case_record.etag
    commits = []
    original_commit = source.commit

    def track_commit(*args, **kwargs):
        commits.append((args, kwargs))
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(source, "capture_snapshot", lambda: faulted)
    monkeypatch.setattr(source, "commit", track_commit)
    callbacks = []
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            runner.start(
                request(),
                operation_id="same-etag-case-fault",
                expected_review_context_hash=review_hash,
                on_created=callbacks.append,
            )
        )
    assert failure.value.error.code == "conflict"
    assert original_capture() == original_records
    assert commits == []
    assert source.list_ids("runs") == ()
    assert callbacks == []
    assert factory.calls == []
