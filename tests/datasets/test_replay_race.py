"""Completed concurrent requests must replay before checking changed current state."""

from contextlib import contextmanager

import pytest

from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.imports import ImportService
from deykit.domain.import_mapping import ImportMapping


class InterleavedSource:
    def __init__(self, source, interleave):
        self.source = source
        self.interleave = interleave

    def __getattr__(self, name):
        return getattr(self.source, name)

    @contextmanager
    def consistent_read(self):
        # A competing identical operation completes before this caller gets its lock.
        if self.interleave is not None:
            run, self.interleave = self.interleave, None
            run()
        with self.source.consistent_read():
            yield self


@pytest.mark.parametrize("command", ["create", "update", "add", "edit", "remove", "import"])
def test_completed_same_operation_replays_when_interleaved_before_validation(project, command):
    storage, datasets, imports, dataset = project
    value = CaseInput(input_kind="text", input_source='"original"')
    added = datasets.add_case(
        "data", value, case_id="original", expected_dataset_etag=dataset.etag, operation_id="setup"
    )
    preview = imports.preview(
        "data",
        '{"text":"imported"}',
        format="jsonl",
        mapping=ImportMapping(input_kind="text", input_column="text"),
    )

    def request(service, importer):
        if command == "create":
            return service.create("Other", dataset_id="other", operation_id="same")
        if command == "update":
            return service.update(
                "data",
                name="Renamed",
                metadata_source="{}",
                expected_etag=added.dataset.etag,
                operation_id="same",
            )
        if command == "add":
            return service.add_case(
                "data",
                value,
                case_id="new",
                expected_dataset_etag=added.dataset.etag,
                operation_id="same",
            )
        if command == "edit":
            return service.edit_case(
                "data",
                "original",
                CaseInput(input_kind="text", input_source='"edited"'),
                expected_dataset_etag=added.dataset.etag,
                expected_case_etag=added.case.etag,
                operation_id="same",
            )
        if command == "remove":
            return service.remove_case(
                "data",
                "original",
                expected_dataset_etag=added.dataset.etag,
                expected_case_etag=added.case.etag,
                operation_id="same",
            )
        return importer.commit(preview, operation_id="same")

    original_results = []

    def interleave():
        first = request(datasets, imports)
        original_results.append(first)
        current = datasets.read("other" if command == "create" else "data")
        datasets.update(
            current.record.id,
            name="Later",
            metadata_source="{}",
            expected_etag=current.etag,
            operation_id="later",
        )

    def forbidden_id():
        raise AssertionError("Replay generated a new identity")

    wrapped = InterleavedSource(storage, interleave)
    result = request(
        DatasetService(wrapped, datasets.clock, forbidden_id),
        ImportService(wrapped, imports.clock, forbidden_id),
    )
    first = original_results[0]
    if command in {"create", "update"}:
        assert result == first
    else:
        assert result.replayed and result.dataset == first.dataset
        if command == "import":
            assert result.imported_case_ids == first.imported_case_ids
        else:
            assert result.case == first.case
