"""Project registration accepts explicit local paths and rejects path syntax."""

import pytest

from deykit.api.registry import _path
from deykit.application.errors import ServiceFailure


@pytest.mark.parametrize(
    "value",
    [
        "relative/project",
        "~/project",
        "file:///tmp/project",
        "//server/share/project",
        "/tmp/drive:relative",
        "/tmp/back\\slash",
        "/tmp/control\npath",
        "/tmp/\ud800",
    ],
)
def test_rejects_nonliteral_or_nonlocal_path_syntax(value: str) -> None:
    with pytest.raises(ServiceFailure) as error:
        _path(value)
    assert error.value.error.reason == "invalid_project_path"


def test_accepts_absolute_paths_with_spaces_and_unicode() -> None:
    assert str(_path("/tmp/Decision project ü")) == "/tmp/Decision project ü"
    assert str(_path("/tmp/%2e%2e")) == "/tmp/%2e%2e"
