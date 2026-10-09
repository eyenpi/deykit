import asyncio
from dataclasses import replace

from test_execution import request

from deykit.runner.history import read_history
from deykit.runner.views import RunSourceReferences, progress_view


def test_progress_view_adds_captured_fixture_compiler_metadata_without_writes(setup):
    source, service, _, _ = setup(2)
    result = asyncio.run(service.start(request(), operation_id="start"))
    before = source.capture_snapshot()

    progress = progress_view(read_history(source, result.run_id))

    assert source.capture_snapshot() == before
    assert progress.sources.adapter == "fixture"
    assert progress.sources.compiler_version == "1"
    assert progress.sources.compiler_id == "jev-choice"
    assert progress.sources.compiler_id_unavailable_reason is None
    assert progress.sources.evidence_mode == "authored_fixture"


def test_progress_view_reports_absent_compiler_for_all_invalid_prepared_plan(setup):
    source, service, _, _ = setup(1, invalid=(0,))
    result = asyncio.run(service.start(request(), operation_id="invalid"))

    progress = progress_view(read_history(source, result.run_id))

    assert progress.cases[0].status == "input_invalid"
    assert progress.sources.compiler_id is None
    assert progress.sources.compiler_id_unavailable_reason == "no_prepared_request"
    assert progress.sources.compiler_version == "not_compiled"


def test_progress_view_maps_live_provenance_and_avoids_inconsistent_compiler_choice(setup):
    source, service, _, _ = setup(2)
    result = asyncio.run(service.start(request(), operation_id="start"))
    history = read_history(source, result.run_id)
    first, second = history.prepared
    assert first.request is not None and second.request is not None
    second_request = second.request.model_copy(update={"compiler": "other-compiler"})
    history = replace(
        history,
        manifest=history.manifest.model_copy(update={"mode": "live"}),
        prepared=(first, second.model_copy(update={"request": second_request})),
    )

    progress = progress_view(history)

    assert progress.sources.evidence_mode == "live"
    assert progress.sources.compiler_id is None
    assert (
        progress.sources.compiler_id_unavailable_reason == "inconsistent_prepared_compiler_identity"
    )


def test_legacy_run_source_references_constructor_keeps_defaults():
    value = RunSourceReferences(
        "revision", "dataset", "labels", "dev", "dev-labels", "profile", None, None
    )

    assert value.adapter is None
    assert value.compiler_id is None
    assert value.evidence_mode is None
