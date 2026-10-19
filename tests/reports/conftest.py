"""Register shared report seeds once for both CLI and projection tests."""

import pytest


@pytest.fixture(scope="session")
def fixture_graph(tmp_path_factory):
    from test_reports import build_fixture_graph

    return build_fixture_graph(tmp_path_factory)


@pytest.fixture(scope="session")
def group_report_graph(fixture_graph, tmp_path_factory):
    from test_reports import build_group_report_graph

    return build_group_report_graph(fixture_graph, tmp_path_factory)
