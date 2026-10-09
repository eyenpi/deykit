"""HTTP settings reject unsafe numbers and preserve historical values as exact text."""

import pytest
from pydantic import ValidationError

from deykit.api.dto.execution import (
    CheckRequestDTO,
    ExecutionSettingsViewDTO,
    RunRequestDTO,
    RunResumeRequest,
)
from deykit.contracts.records import ExecutionSettings
from deykit.runner.planner import RunRequest, start_intent


def _run_body(settings: dict[str, object]) -> dict[str, object]:
    return {
        "decision_id": "decision",
        "dataset_id": "dataset",
        "mode": "fixture",
        "fixture_set_id": "fixtures",
        "settings": settings,
    }


@pytest.mark.parametrize("invalid", [True, 1.5, 9_007_199_254_740_992])
def test_http_run_settings_reject_boolean_fraction_and_unsafe_integer(invalid: object) -> None:
    with pytest.raises(ValidationError):
        RunRequestDTO.model_validate(_run_body({"max_attempts": invalid}))


@pytest.mark.parametrize("invalid", [True, 1.5, 9_007_199_254_740_992])
def test_http_resume_cap_rejects_boolean_fraction_and_unsafe_integer(invalid: object) -> None:
    with pytest.raises(ValidationError):
        RunResumeRequest.model_validate(
            {"schema_version": 1, "operation_id": "resume", "max_attempts": invalid}
        )


@pytest.mark.parametrize("invalid", [True, 1.5, 9_007_199_254_740_992])
def test_http_check_settings_reject_boolean_fraction_and_unsafe_integer(
    invalid: object,
) -> None:
    with pytest.raises(ValidationError):
        CheckRequestDTO.model_validate(
            {
                "decision_id": "decision",
                "mode": "fixture",
                "fixture_set_id": "fixtures",
                "settings": {"max_attempts": invalid},
            }
        )


def test_http_settings_convert_to_unchanged_domain_settings_and_intent() -> None:
    source = _run_body(
        {
            "max_attempts": 9_007_199_254_740_991,
            "concurrency": 64,
            "timeout_seconds": 600,
            "deadline_seconds": 86_400,
            "max_retries_per_case": 1,
        }
    )
    transport = RunRequestDTO.model_validate(source)
    domain = transport.to_application()
    direct = RunRequest.model_validate(
        {**source, "settings": ExecutionSettings(**source["settings"])}
    )

    assert domain.settings == ExecutionSettings(**source["settings"])
    assert start_intent(domain) == start_intent(direct)


def test_historical_domain_settings_project_to_exact_text_without_clamping() -> None:
    historical = ExecutionSettings(
        max_attempts=10**30,
        concurrency=10**24,
        timeout_seconds=10**28,
        deadline_seconds=86_400,
        max_retries_per_case=0,
    )

    projected = ExecutionSettingsViewDTO.from_application(historical)

    assert projected.model_dump() == {
        "max_attempts": str(10**30),
        "concurrency": str(10**24),
        "timeout_seconds": str(10**28),
        "deadline_seconds": "86400",
        "max_retries_per_case": "0",
    }
