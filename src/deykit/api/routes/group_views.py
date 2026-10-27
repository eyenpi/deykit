"""Shared projections for the two durable execution-group route families."""

from deykit.api.dto.execution import (
    GroupMemberResumePreviewDTO,
    GroupProgressDTO,
    GroupResumePreviewDTO,
)
from deykit.runner.group_models import GroupProgress, GroupResumePreview

from .execution import run_progress


def group_progress(value: GroupProgress) -> GroupProgressDTO:
    if value.kind == "experiment":
        raise RuntimeError("unsupported_group_kind")
    return GroupProgressDTO(
        group_id=value.group_id,
        kind=value.kind,
        members=tuple(run_progress(item) for item in value.members),
        attempts_used=str(value.attempts_used),
        attempt_limit=str(value.attempt_limit),
        attempts_remaining=str(value.attempts_remaining),
        snapshot_id=value.snapshot_id,
        replayed=value.replayed,
        initial_requests=str(value.initial_requests),
        independent_case_count=str(value.independent_case_count),
        algorithm=value.algorithm,
        seed=str(value.seed) if value.seed is not None else None,
    )


def group_resume_preview(value: GroupResumePreview) -> GroupResumePreviewDTO:
    return GroupResumePreviewDTO(
        group=group_progress(value.group),
        segment_ids=value.segment_ids,
        members=tuple(
            GroupMemberResumePreviewDTO(
                run_id=member.run_id, planned_case_ids=member.planned_case_ids
            )
            for member in value.members
        ),
        retry_unknown=value.retry_unknown,
        proposed_attempt_limit=str(value.proposed_attempt_limit),
        dry_run=value.dry_run,
    )
