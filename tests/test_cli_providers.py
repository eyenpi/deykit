"""Offline installed CLI and fake-transport proof for non-secret provider workflows."""

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from deykit.cli.main import app
from deykit.contracts.codec import dump_record
from deykit.contracts.records import ProviderProfile
from deykit.providers.choice import JEV_DESTINATION
from deykit.providers.credentials import CredentialUnavailable
from deykit.providers.fixtures import FIXTURE_DESTINATION


def cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(Path(sys.executable).with_name("deykit")), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def result(process: subprocess.CompletedProcess[str], expected_code: int = 0) -> dict[str, object]:
    assert process.returncode == expected_code, process.stderr
    assert process.stderr == ""
    assert process.stdout.count("\n") == 1
    return json.loads(process.stdout)


def project(tmp_path: Path) -> Path:
    path = tmp_path / "Project ü"
    result(cli(tmp_path, "--json", "init", str(path), "--name", "Provider tests"))
    return path


def test_provider_profile_commands_and_credential_refs_are_offline(
    tmp_path: Path, monkeypatch
) -> None:
    root = project(tmp_path)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    created = result(
        cli(
            root,
            "--json",
            "provider",
            "configure",
            "jev-main",
            "--adapter",
            "jev",
            "--model",
            "jev-1.13.0",
            "--operation-id",
            "configure-jev",
        )
    )
    view = created["data"]["profile"]["view"]
    assert view["profile"]["credential_ref"] == "env:JEV_API_KEY"
    original_etag = view["etag"]
    assert "jev-main\tjev\tjev-1.13.0" in cli(root, "provider", "list").stdout
    shown = result(cli(root, "--json", "provider", "show", "jev-main"))
    assert shown["data"]["credential"] == {"configured": True, "kind": "env"}
    assert shown["data"]["capabilities"]["evidence_mode"] == "live"
    status = result(cli(root, "--json", "credential", "status", "--provider", "jev-main"))
    assert status["data"]["available"] is False
    missing = result(cli(root, "--json", "provider", "models", "jev-main"), 2)
    assert missing["error"]["reason"] == "credential_unavailable"
    doctor = result(cli(root, "--json", "doctor"))
    assert doctor["data"]["profile_count"] == 1 and doctor["data"]["network"] is None

    linked = result(
        cli(
            root,
            "--json",
            "credential",
            "set",
            "--provider",
            "jev-main",
            "--env",
            "OTHER_OFFLINE_KEY",
            "--if-hash",
            original_etag,
            "--operation-id",
            "link-env",
        )
    )
    assert linked["data"]["profile"]["view"]["profile"]["credential_ref"] == "env:OTHER_OFFLINE_KEY"
    updated_etag = linked["data"]["profile"]["view"]["etag"]
    changed = result(
        cli(
            root,
            "--json",
            "provider",
            "configure",
            "jev-main",
            "--adapter",
            "jev",
            "--model",
            "jev-latest",
            "--credential-env",
            "OTHER_OFFLINE_KEY",
            "--if-hash",
            updated_etag,
            "--operation-id",
            "change-model",
        )
    )
    changed_etag = changed["data"]["profile"]["view"]["etag"]
    linked_replay = result(
        cli(
            root,
            "--json",
            "credential",
            "set",
            "--provider",
            "jev-main",
            "--env",
            "OTHER_OFFLINE_KEY",
            "--if-hash",
            original_etag,
            "--operation-id",
            "link-env",
        )
    )
    assert linked_replay["data"]["replayed"] is True
    assert linked_replay["data"]["profile"] == linked["data"]["profile"]
    assert result(cli(root, "--json", "provider", "show", "jev-main"))["data"]["view"][
        "profile"
    ]["requested_model"] == "jev-latest"
    forgotten = result(
        cli(
            root,
            "--json",
            "credential",
            "forget",
            "--provider",
            "jev-main",
            "--if-hash",
            changed_etag,
            "--operation-id",
            "forget-env",
        )
    )
    assert forgotten["data"]["profile"]["view"]["profile"]["credential_ref"] is None
    forgotten_etag = forgotten["data"]["profile"]["view"]["etag"]
    next_profile = ProviderProfile(
        id="jev-main",
        adapter="jev",
        requested_model="jev-preview",
        destination=JEV_DESTINATION,
    )
    next_source = tmp_path / "next-profile.json"
    next_source.write_bytes(dump_record(next_profile))
    result(
        cli(
            root,
            "--json",
            "provider",
            "configure",
            "jev-main",
            "--file",
            str(next_source),
            "--if-hash",
            forgotten_etag,
            "--operation-id",
            "later-profile",
        )
    )
    replay = result(
        cli(
            root,
            "--json",
            "credential",
            "forget",
            "--provider",
            "jev-main",
            "--if-hash",
            changed_etag,
            "--operation-id",
            "forget-env",
        )
    )
    assert replay["data"]["replayed"] is True
    assert replay["data"]["profile"] == forgotten["data"]["profile"]
    assert result(cli(root, "--json", "provider", "show", "jev-main"))["data"]["view"][
        "profile"
    ]["requested_model"] == "jev-preview"


def test_fixture_profile_file_and_deterministic_pagination(tmp_path: Path) -> None:
    root = project(tmp_path)
    fixture = ProviderProfile(
        id="authored",
        adapter="fixture",
        requested_model="authored-demo",
        destination=FIXTURE_DESTINATION,
    )
    source = tmp_path / "fixture-profile.json"
    source.write_bytes(dump_record(fixture))
    created = result(
        cli(root, "--json", "provider", "configure", "authored", "--file", str(source))
    )
    assert created["data"]["profile"]["capabilities"]["evidence_mode"] == "authored_fixture"
    result(
        cli(
            root,
            "--json",
            "provider",
            "configure",
            "live",
            "--adapter",
            "jev",
            "--model",
            "jev-1.13.0",
        )
    )
    first = result(cli(root, "--json", "provider", "list", "--limit", "1"))["data"]
    assert first["total"] == 2 and first["next_cursor"] == "authored"
    second = result(
        cli(root, "--json", "provider", "list", "--limit", "1", "--cursor", first["next_cursor"])
    )["data"]
    assert second["items"][0]["profile"]["id"] == "live"
    invalid = result(cli(root, "--json", "credential", "status", "--provider", "missing"), 2)
    assert invalid["error"]["code"] == "not_found"
    no_models = result(cli(root, "--json", "provider", "models", "authored"), 2)
    assert no_models["error"]["reason"] == "models_require_live_provider"


def test_explicit_model_list_and_network_doctor_use_fake_zero_inference(
    tmp_path: Path, monkeypatch
) -> None:
    root = project(tmp_path)
    result(
        cli(
            root,
            "--json",
            "provider",
            "configure",
            "jev-main",
            "--adapter",
            "jev",
            "--model",
            "jev-1.13.0",
        )
    )
    calls = []

    class FakeJev:
        def __init__(self, profile, credentials):
            assert profile.requested_model == "jev-1.13.0"
            calls.append("constructed")

        async def models(self, *, timeout_seconds=60):
            calls.append("GET models")
            return ({"name": "jev-1.13.0", "description": "Pinned", "release_date": "2026-01-01"},)

        async def dispatch(self, *args, **kwargs):
            raise AssertionError("inference forbidden")

    monkeypatch.setattr("deykit.providers.jev.JevProvider", FakeJev)
    runner = CliRunner()
    listed = runner.invoke(
        app, ["--project", str(root), "--json", "provider", "models", "jev-main"]
    )
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["data"]["models"][0]["name"] == "jev-1.13.0"
    checked = runner.invoke(
        app,
        ["--project", str(root), "--json", "doctor", "--provider", "jev-main", "--network-check"],
    )
    assert checked.exit_code == 0
    assert json.loads(checked.stdout)["data"]["network"] == {"model_count": 1, "inference_calls": 0}
    assert calls == ["constructed", "GET models", "constructed", "GET models"]


def test_stdin_secret_store_failure_is_redacted_and_does_not_change_profile(
    tmp_path: Path, monkeypatch
) -> None:
    root = project(tmp_path)
    result(
        cli(
            root,
            "--json",
            "provider",
            "configure",
            "jev-main",
            "--adapter",
            "jev",
            "--model",
            "jev-1.13.0",
        )
    )
    from deykit.cli.commands import providers

    def unavailable():
        raise CredentialUnavailable()

    monkeypatch.setattr(providers, "os_secret_store", unavailable)
    attempt = CliRunner().invoke(
        app,
        [
            "--project",
            str(root),
            "--json",
            "credential",
            "set",
            "--provider",
            "jev-main",
            "--stdin",
        ],
        input="SECRET_SENTINEL\n",
    )
    assert attempt.exit_code == 2
    assert "SECRET_SENTINEL" not in attempt.output
    assert json.loads(attempt.stdout)["error"]["reason"] == "credential_store_unavailable"
    shown = result(cli(root, "--json", "provider", "show", "jev-main"))
    assert shown["data"]["view"]["profile"]["credential_ref"] == "env:JEV_API_KEY"


def test_stale_credential_change_never_touches_os_store(tmp_path: Path, monkeypatch) -> None:
    root = project(tmp_path)
    created = result(
        cli(
            root,
            "--json",
            "provider",
            "configure",
            "jev-main",
            "--adapter",
            "jev",
            "--model",
            "jev-1.13.0",
        )
    )
    original_etag = created["data"]["profile"]["view"]["etag"]
    result(
        cli(
            root,
            "--json",
            "credential",
            "set",
            "--provider",
            "jev-main",
            "--env",
            "OTHER_OFFLINE_KEY",
        )
    )
    from deykit.cli.commands import providers

    def forbidden_store():
        raise AssertionError("stale commands must not touch the OS credential store")

    monkeypatch.setattr(providers, "os_secret_store", forbidden_store)
    stale = CliRunner().invoke(
        app,
        [
            "--project",
            str(root),
            "--json",
            "credential",
            "set",
            "--provider",
            "jev-main",
            "--stdin",
            "--if-hash",
            original_etag,
        ],
        input="SECRET_SENTINEL\n",
    )
    assert stale.exit_code == 2
    assert json.loads(stale.stdout)["error"]["code"] == "conflict"
    assert "SECRET_SENTINEL" not in stale.output
