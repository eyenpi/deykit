"""Offline installed CLI and fake-transport proof for non-secret provider workflows."""

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from deykit.cli.main import app
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import dump_json, parse_json
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
    assert (
        result(cli(root, "--json", "provider", "show", "jev-main"))["data"]["view"]["profile"][
            "requested_model"
        ]
        == "jev-latest"
    )
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
    assert (
        result(cli(root, "--json", "provider", "show", "jev-main"))["data"]["view"]["profile"][
            "requested_model"
        ]
        == "jev-preview"
    )


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


def test_models_cli_uses_one_authenticated_get_and_redacts_fake_secret(
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
    monkeypatch.setenv("JEV_API_KEY", "SECRET_SENTINEL")
    from deykit.providers import jev
    from deykit.providers.http import OneShotHttp

    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "jev-1.13.0",
                        "description": "SECRET_SENTINEL",
                        "release_date": "2026-10-01",
                    }
                ]
            },
        )

    monkeypatch.setattr(jev, "OneShotHttp", lambda: OneShotHttp(httpx.MockTransport(handle)))
    invoked = CliRunner().invoke(
        app, ["--project", str(root), "--json", "provider", "models", "jev-main"]
    )
    assert invoked.exit_code == 0
    assert len(calls) == 1 and calls[0].method == "GET"
    assert calls[0].url.path == "/v1/models"
    assert not calls[0].content
    assert "SECRET_SENTINEL" not in invoked.output
    assert json.loads(invoked.stdout)["data"]["models"][0]["description"] == "[REDACTED]"


def test_doctor_live_smoke_uses_runner_one_attempt_and_replays_without_dispatch(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "Smoke ü"
    demo = result(cli(tmp_path, "--json", "demo", str(root)))["data"]["info"]
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
    monkeypatch.setenv("JEV_API_KEY", "SECRET_SENTINEL")
    from deykit.providers import jev
    from deykit.providers.http import OneShotHttp

    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        compiled = parse_json(request.content)
        questions = compiled["questions"]
        question_id = next(iter(questions))
        options = tuple(questions[question_id]["criteria"])
        return httpx.Response(
            200,
            content=dump_json(
                {
                    "model": "jev-1.13.0",
                    "answers": {
                        question_id: {
                            "type": "choice",
                            "choice": options[0],
                            "probabilities": {
                                option_id: Decimal(1 if index == 0 else 0)
                                for index, option_id in enumerate(options)
                            },
                            "confidence": Decimal(1),
                        }
                    },
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                }
            ).encode(),
        )

    monkeypatch.setattr(jev, "OneShotHttp", lambda: OneShotHttp(httpx.MockTransport(handle)))
    arguments = [
        "--project",
        str(root),
        "--json",
        "doctor",
        "--live-smoke",
        "--provider",
        "jev-main",
        "--decision",
        demo["decision_id"],
        "--dataset",
        demo["dataset_id"],
        "--case",
        "ex-001",
        "--operation-id",
        "one-smoke",
    ]
    first = CliRunner().invoke(app, arguments)
    assert first.exit_code == 0, first.output
    smoke = json.loads(first.stdout)["data"]["smoke"]
    assert smoke["mode"] == "live" and smoke["requested_model"] == "jev-1.13.0"
    assert smoke["attempts_used"] == smoke["attempt_limit"] == 1
    assert smoke["settings"] == {
        "max_attempts": 1,
        "concurrency": 1,
        "timeout_seconds": 60,
        "deadline_seconds": 60,
        "max_retries_per_case": 0,
    }
    assert smoke["result_snapshot_id"] and smoke["case"]["case_id"] == "ex-001"
    assert [request.method for request in calls] == ["POST"]
    assert "SECRET_SENTINEL" not in first.output
    replay = CliRunner().invoke(app, arguments)
    assert replay.exit_code == 0, replay.output
    replay_smoke = json.loads(replay.stdout)["data"]["smoke"]
    assert replay_smoke["run_id"] == smoke["run_id"] and replay_smoke["replayed"] is True
    assert len(calls) == 1


def test_doctor_smoke_preflight_has_zero_dispatch_and_modes_are_exclusive(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "Smoke"
    demo = result(cli(tmp_path, "--json", "demo", str(root)))["data"]["info"]
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
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    from deykit.providers import jev

    async def forbidden_dispatch(*args, **kwargs):
        raise AssertionError("missing credentials may not dispatch")

    monkeypatch.setattr(jev.JevProvider, "dispatch", forbidden_dispatch)
    base = ["--project", str(root), "--json", "doctor", "--provider", "jev-main"]
    context = [
        "--decision",
        demo["decision_id"],
        "--dataset",
        demo["dataset_id"],
        "--case",
        "ex-001",
    ]
    conflict = CliRunner().invoke(app, [*base, "--live-smoke", "--network-check", *context])
    assert conflict.exit_code == 2
    assert json.loads(conflict.stdout)["error"]["reason"] == "diagnostic_mode_conflict"
    missing = CliRunner().invoke(app, [*base, "--live-smoke", *context])
    assert missing.exit_code == 2
    assert json.loads(missing.stdout)["error"]["reason"] == "credential_unavailable"
    changed_timeout = CliRunner().invoke(
        app, [*base, "--live-smoke", *context, "--timeout-seconds", "61"]
    )
    assert changed_timeout.exit_code == 2
    assert json.loads(changed_timeout.stdout)["error"]["reason"] == "smoke_timeout_fixed_at_60"


@pytest.mark.parametrize(
    ("failure", "exit_code", "status", "reason"),
    [
        ("auth", 3, "response_error", None),
        ("payload", 3, "response_error", "invalid_payload"),
        ("rate_limit", 3, "response_error", "rate_limit"),
        ("overload", 3, "response_error", "overloaded"),
        ("malformed", 3, "response_error", "missing_answers"),
        ("timeout", 4, "unknown", "timeout"),
        ("disconnect", 4, "unknown", "disconnect"),
    ],
)
def test_doctor_failed_smoke_preserves_evidence_without_retry(
    tmp_path: Path, monkeypatch, failure, exit_code, status, reason
) -> None:
    root = tmp_path / "Failed smoke"
    demo = result(cli(tmp_path, "--json", "demo", str(root)))["data"]["info"]
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
    monkeypatch.setenv("JEV_API_KEY", "SECRET_SENTINEL")
    from deykit.providers import jev
    from deykit.providers.http import OneShotHttp

    calls = []

    def handle(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("Bearer SECRET_SENTINEL", request=request)
        if failure == "disconnect":
            raise httpx.ReadError("Authorization: Bearer SECRET_SENTINEL", request=request)
        code = {"auth": 401, "payload": 422, "rate_limit": 429, "overload": 529}.get(failure, 200)
        return httpx.Response(code, content=b'{"authorization":"Bearer SECRET_SENTINEL"}')

    monkeypatch.setattr(jev, "OneShotHttp", lambda: OneShotHttp(httpx.MockTransport(handle)))
    arguments = [
        "--project",
        str(root),
        "--json",
        "doctor",
        "--live-smoke",
        "--provider",
        "live",
        "--decision",
        demo["decision_id"],
        "--dataset",
        demo["dataset_id"],
        "--case",
        "ex-001",
        "--operation-id",
        "failed-smoke",
    ]
    invoked = CliRunner().invoke(app, arguments)
    assert invoked.exit_code == exit_code, invoked.output
    smoke = json.loads(invoked.stdout)["data"]["smoke"]
    assert smoke["case"]["status"] == status
    assert smoke["case"]["error"]["reason"] == reason
    assert smoke["attempts_used"] == smoke["attempt_limit"] == len(calls) == 1
    assert smoke["result_snapshot_id"]
    assert "SECRET_SENTINEL" not in invoked.output
    assert "authorization" not in invoked.output.lower()
    replay = CliRunner().invoke(app, arguments)
    assert replay.exit_code == exit_code, replay.output
    assert json.loads(replay.stdout)["data"]["smoke"]["replayed"] is True
    assert len(calls) == 1
    assert not any(b"SECRET_SENTINEL" in path.read_bytes() for path in root.rglob("*.json"))
    assert not any(b"SECRET_SENTINEL" in path.read_bytes() for path in root.rglob("*.jsonl"))


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


def test_explicit_os_store_commands_keep_values_outside_project(
    tmp_path: Path, monkeypatch
) -> None:
    root = project(tmp_path)
    created = result(
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
    initial_etag = created["data"]["profile"]["view"]["etag"]
    from deykit.cli.commands import providers
    from deykit.providers import credentials

    values = {}
    writes = []

    class FakeStore:
        def get_password(self, service, account):
            return values.get((service, account))

        def set_password(self, service, account, value):
            writes.append((service, account))
            values[(service, account)] = value

        def delete_password(self, service, account):
            del values[(service, account)]

    store = FakeStore()
    monkeypatch.setattr(providers, "os_secret_store", lambda: store)
    monkeypatch.setattr(credentials, "os_secret_store", lambda: store)
    base = ["--project", str(root), "--json"]
    arguments = [
        *base,
        "credential",
        "set",
        "--provider",
        "live",
        "--stdin",
        "--if-hash",
        initial_etag,
        "--operation-id",
        "os-set",
    ]
    first = CliRunner().invoke(app, arguments, input="SECRET_SENTINEL\n")
    assert first.exit_code == 0, first.output
    profile = json.loads(first.stdout)["data"]["profile"]["view"]
    assert profile["profile"]["credential_ref"] == "keyring:deykit/live"
    assert values == {("deykit", "live"): "SECRET_SENTINEL"}
    status = CliRunner().invoke(app, [*base, "credential", "status", "--provider", "live"])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["data"]["available"] is True
    replay = CliRunner().invoke(app, arguments, input="SECRET_SENTINEL\n")
    assert replay.exit_code == 0 and json.loads(replay.stdout)["data"]["replayed"]
    assert writes == [("deykit", "live")]
    forgotten = CliRunner().invoke(
        app, [*base, "credential", "forget", "--provider", "live", "--operation-id", "os-forget"]
    )
    assert forgotten.exit_code == 0 and values == {}
    assert (
        json.loads(forgotten.stdout)["data"]["profile"]["view"]["profile"]["credential_ref"] is None
    )
    for output in (first.output, status.output, replay.output, forgotten.output):
        assert "SECRET_SENTINEL" not in output
    assert not any(b"SECRET_SENTINEL" in path.read_bytes() for path in root.rglob("*.json"))


def test_environment_and_fixture_commands_never_load_optional_os_store(
    tmp_path: Path, monkeypatch
) -> None:
    root = project(tmp_path)
    from deykit.providers import credentials

    def forbidden_store():
        raise AssertionError("ordinary environment and fixture profiles must not load keyring")

    monkeypatch.setattr(credentials, "os_secret_store", forbidden_store)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    base = ["--project", str(root), "--json"]
    commands = [
        ["provider", "configure", "live", "--adapter", "jev", "--model", "jev-1.13.0"],
        ["provider", "configure", "authored", "--adapter", "fixture", "--model", "authored-test"],
        ["provider", "list"],
        ["provider", "show", "live"],
        ["credential", "status", "--provider", "live"],
        ["doctor", "--provider", "live"],
    ]
    for command in commands:
        invoked = CliRunner().invoke(app, [*base, *command])
        assert invoked.exit_code == 0, invoked.output


def test_forget_recovers_native_deletion_after_source_failure_and_replays_original(
    tmp_path: Path, monkeypatch
) -> None:
    root = project(tmp_path)
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
    from deykit.cli.commands import providers
    from deykit.storage import FileProjectSource

    values = {}
    deletions = []

    class NativeStore:
        def get_password(self, service, account):
            return values.get((service, account))

        def set_password(self, service, account, value):
            values[(service, account)] = value

        def delete_password(self, service, account):
            deletions.append((service, account))
            del values[(service, account)]  # Native backends reject a missing entry.

    monkeypatch.setattr(providers, "os_secret_store", lambda: NativeStore())
    base = ["--project", str(root), "--json"]
    stored = CliRunner().invoke(
        app,
        [*base, "credential", "set", "--provider", "live", "--stdin"],
        input="SECRET_SENTINEL\n",
    )
    assert stored.exit_code == 0, stored.output
    etag = json.loads(stored.stdout)["data"]["profile"]["view"]["etag"]
    original_commit = FileProjectSource.commit
    fail_once = True

    def commit(source, operation_id, *args, **kwargs):
        nonlocal fail_once
        if operation_id == "recover-forget" and fail_once:
            fail_once = False
            raise OSError("SECRET_SENTINEL")
        return original_commit(source, operation_id, *args, **kwargs)

    monkeypatch.setattr(FileProjectSource, "commit", commit)
    arguments = [
        *base,
        "credential",
        "forget",
        "--provider",
        "live",
        "--if-hash",
        etag,
        "--operation-id",
        "recover-forget",
    ]
    failed = CliRunner().invoke(app, arguments)
    assert failed.exit_code == 1, failed.output
    failure = json.loads(failed.stdout)["error"]
    assert failure["code"] == "internal_error"
    assert failure["reason"] == "credential_update_outcome_unknown"
    assert failure["resource_id"] == "live"
    assert values == {} and deletions == [("deykit", "live")]
    unchanged = CliRunner().invoke(app, [*base, "provider", "show", "live"])
    assert (
        json.loads(unchanged.stdout)["data"]["view"]["profile"]["credential_ref"]
        == "keyring:deykit/live"
    )
    with monkeypatch.context() as backend_missing:

        def unavailable():
            raise CredentialUnavailable()

        backend_missing.setattr(providers, "os_secret_store", unavailable)
        blocked = CliRunner().invoke(app, arguments)
        assert blocked.exit_code == 2, blocked.output
        assert json.loads(blocked.stdout)["error"]["reason"] == "credential_store_unavailable"
        still_linked = CliRunner().invoke(app, [*base, "provider", "show", "live"])
        assert (
            json.loads(still_linked.stdout)["data"]["view"]["profile"]["credential_ref"]
            == "keyring:deykit/live"
        )
    recovered = CliRunner().invoke(app, arguments)
    assert recovered.exit_code == 0, recovered.output
    saved = json.loads(recovered.stdout)["data"]
    assert saved["profile"]["view"]["profile"]["credential_ref"] is None
    assert deletions == [("deykit", "live")]
    changed = CliRunner().invoke(
        app, [*base, "credential", "set", "--provider", "live", "--env", "OTHER_OFFLINE_KEY"]
    )
    assert changed.exit_code == 0
    replay = CliRunner().invoke(app, arguments)
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.stdout)["data"] == {**saved, "replayed": True}
    current = CliRunner().invoke(app, [*base, "provider", "show", "live"])
    assert (
        json.loads(current.stdout)["data"]["view"]["profile"]["credential_ref"]
        == "env:OTHER_OFFLINE_KEY"
    )
    assert deletions == [("deykit", "live")]
    for output in (stored.output, failed.output, unchanged.output, recovered.output, replay.output):
        assert "SECRET_SENTINEL" not in output
