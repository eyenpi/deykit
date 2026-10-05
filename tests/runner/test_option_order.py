import asyncio

import pytest
from test_execution import request

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import load_record
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import DecisionRevision
from deykit.runner.history import read_history


@pytest.mark.parametrize("order", [(), ("yes",), ("yes", "yes"), ("yes", "unknown")])
def test_invalid_option_permutations_are_global_zero_dispatch(setup, order):
    source, service, factory, _ = setup(1)
    with pytest.raises(ServiceFailure) as caught:
        service.preview(request(option_order=order))
    assert caught.value.error.reason == "invalid_option_order"
    assert not factory.calls and not source.list_ids("runs")


def test_order_changes_only_compiled_bytes_and_survives_resume(setup):
    source, service, factory, _ = setup(1)
    selection = request(option_order=("no", "yes"))
    stopped = asyncio.run(
        service.start(
            selection,
            operation_id="start",
            on_created=lambda created: service.cancel(created.run_id, operation_id="cancel"),
        )
    )
    history = read_history(source, stopped.run_id)
    frozen = history.prepared[0].request
    assert history.manifest.option_order == ("no", "yes")
    revision = load_record(
        DecisionRevision,
        source.read(
            ResourceKey("revisions", history.manifest.decision_revision_id, ("decision",))
        ).body,
    )
    assert tuple(option.id for option in revision.definition.questions[0].options) == ("yes", "no")
    assert frozen.body.index(b'"no":') < frozen.body.index(b'"yes":')

    class ForbiddenCompiler:
        def compile(self, *_args):
            raise AssertionError("resume must not compile")

    factory.compiler = ForbiddenCompiler()
    resumed = asyncio.run(service.resume(stopped.run_id, operation_id="resume"))
    assert resumed.exit_code == 0 and factory.calls[0][1] == frozen
    with pytest.raises(ServiceFailure) as caught:
        asyncio.run(service.start(request(option_order=("yes", "no")), operation_id="start"))
    assert caught.value.error.reason == "operation_id_conflict"
