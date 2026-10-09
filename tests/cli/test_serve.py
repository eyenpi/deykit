from pathlib import Path

from typer.testing import CliRunner

from deykit.application.demo import DemoInfo
from deykit.cli.commands import demo as demo_module
from deykit.cli.commands import serve as serve_module
from deykit.cli.main import app


def test_serve_forwards_project_port_and_no_open(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "Project"
    calls: list[tuple[Path | None, int, bool]] = []
    monkeypatch.setattr(
        serve_module,
        "launch_local_server",
        lambda path, *, port, open_browser: calls.append((path, port, open_browser)),
    )

    result = CliRunner().invoke(
        app,
        ["--project", str(project), "serve", "--port", "0", "--no-open"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [(project, 0, False)]


def test_demo_open_starts_server_only_after_demo_service_returns(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "Sandbox"
    events: list[str] = []

    class DemoStub:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def create(self, path: Path, *, operation_id: str) -> DemoInfo:
            path.mkdir()
            (path / "durable-demo.marker").write_text(operation_id)
            events.append("created")
            return DemoInfo(
                path=path,
                project_id="project-1",
                decision_id="decision-1",
                revision_id="revision-1",
                dataset_id="dataset-1",
                profile_id="profile-1",
                fixture_set_id="fixture-set-1",
                case_count=12,
                binding_count=11,
                label_count=9,
                operation_id=operation_id,
                replayed=False,
            )

    def launch(path: Path, *, open_browser: bool) -> None:
        assert (path / "durable-demo.marker").read_text() == "demo-operation"
        events.append("opened")
        assert open_browser is True

    monkeypatch.setattr(demo_module, "DemoService", DemoStub)
    monkeypatch.setattr(serve_module, "launch_local_server", launch)

    result = CliRunner().invoke(
        app,
        ["demo", str(target), "--operation-id", "demo-operation", "--open"],
    )

    assert result.exit_code == 0, result.output
    assert events == ["created", "opened"]
