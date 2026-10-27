"""Classification comparisons disclose selected-input differences."""

import subprocess
import sys

from test_reports import MemorySnapshotSource

from deykit.application.reports import ReportService
from deykit.cli.context import SystemClock
from deykit.reports.models import ReportRequest


def test_comparison_reconstructs_selected_input_identity_from_frozen_cases(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    report = service.create(
        ReportRequest(target_id=fixture_graph.comparison_id, preset="classification"),
        operation_id="selected-input-identity",
    )
    classification = report.content.classification
    assert classification.policy == "classification-strict-v4"
    comparison = classification.experimental_comparison
    assert comparison.selected_input_comparison == "reconstructed_selection_v1"
    assert comparison.selected_input_changed_count == 0
    assert comparison.selected_input_unavailable_count == 1
    cases = {case.case_id: case for case in comparison.cases}
    assert cases["ex-001"].selected_input.changed is False
    assert cases["ex-011"].selected_input.changed is None
    assert cases["ex-011"].selected_input.unavailable_reason == "input_not_prepared"
    assert service.read(report.record.id).content == report.content


def test_report_projection_does_not_load_provider_adapters():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import deykit.reports.projection; "
            "assert 'deykit.providers' not in sys.modules; "
            "assert 'httpx' not in sys.modules; assert 'PIL.Image' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
