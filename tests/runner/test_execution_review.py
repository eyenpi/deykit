from deykit.application.execution_review import _safe_request_source
from deykit.contracts.redaction import Sanitizer
from deykit.runner.planner import RunRequest


def request(**changes):
    return RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="fixture",
        fixture_set_id="set",
        **changes,
    )


def test_review_preview_uses_one_plan_and_reveals_source_only_on_opt_in(setup, monkeypatch):
    source, service, factory, _ = setup(3, invalid=(2,))
    original_prepare = service.planner.prepare
    prepared_requests: list[RunRequest] = []

    def prepare(selection):
        prepared_requests.append(selection)
        return original_prepare(selection)

    monkeypatch.setattr(service.planner, "prepare", prepare)
    before = source.capture_snapshot()

    hidden = service.review_preview(request())

    assert len(prepared_requests) == 1
    assert len(hidden.preview.review_context_hash) == 64
    assert len(hidden.review_context.source_context_hash) == 64
    assert len(hidden.case_reviews) == 3
    assert all(item.request_source is None for item in hidden.case_reviews)
    assert all(item.request_source_redacted is None for item in hidden.case_reviews)
    assert hidden.case_reviews[2].input_error is not None
    assert hidden.case_reviews[2].request_hash is None
    assert hidden.case_reviews[2].compiler is None
    assert factory.calls == []
    assert source.capture_snapshot() == before

    revealed = service.review_preview(request(), include_request_source=True)

    assert len(prepared_requests) == 2
    assert revealed.preview.review_context_hash == hidden.preview.review_context_hash
    assert revealed.review_context == hidden.review_context
    assert all(item.request_source is not None for item in revealed.case_reviews[:2])
    assert all(item.request_source_redacted is False for item in revealed.case_reviews[:2])
    assert revealed.case_reviews[2].request_source is None
    assert revealed.case_reviews[2].request_source_redacted is None
    assert all(item.request_hash is not None for item in revealed.case_reviews[:2])
    assert factory.calls == []
    assert source.capture_snapshot() == before


def test_projected_compiled_source_preserves_exact_numbers_and_redacts_secrets():
    exact = '{ "large": 9007199254740993, "fraction": 1.2300 }'
    source, changed = _safe_request_source(exact.encode("utf-8"), Sanitizer())
    assert source == exact
    assert changed is False

    secret = '{"api_key":"synthetic-secret","large":9007199254740993}'
    safe_source, redacted = _safe_request_source(secret.encode("utf-8"), Sanitizer())
    assert redacted is True
    assert "synthetic-secret" not in safe_source
    assert "[REDACTED]" in safe_source
    assert "9007199254740993" in safe_source
