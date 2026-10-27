"""Recorded cohort filters must not invent historical selection evidence."""

from types import SimpleNamespace

import pytest

from deykit.contracts.records import DatasetSnapshot, RunManifest
from deykit.reports.projection import _cohort_selection


@pytest.mark.parametrize(
    "selection",
    [
        "{}",
        '{"split":"invalid","case_ids":[]}',
        '{"split":"test","case_ids":[]}',
        '{"split":"all","case_ids":["another-case"]}',
        '{"split":"all","case_ids":["case-1","case-2"]}',
        '{"split":"development","case_ids":["case-1","../invalid"]}',
        '{"split":"all","case_ids":["case-1","case-1"]}',
        '{"split":"all","case_ids":[{}]}',
    ],
)
def test_missing_or_inconsistent_selection_is_unavailable(selection):
    dataset = DatasetSnapshot.model_construct(
        selection_source=selection, cases=(SimpleNamespace(id="case-1", split="development"),)
    )
    manifest = RunManifest.model_construct(regression_ids=())
    assert _cohort_selection(dataset, manifest) == {
        "split": None,
        "explicit_case_ids": None,
        "requested_case_count": None,
        "regression_selected": False,
    }


def test_frozen_regression_selection_is_disclosed_separately():
    dataset = DatasetSnapshot.model_construct(
        selection_source='{"split":"all","case_ids":[]}',
        cases=(SimpleNamespace(id="case-1", split="development"),),
    )
    manifest = RunManifest.model_construct(regression_ids=("regression-1",))
    assert _cohort_selection(dataset, manifest) == {
        "split": "all",
        "explicit_case_ids": False,
        "requested_case_count": 0,
        "regression_selected": True,
    }
