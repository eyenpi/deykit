"""Offline console acceptance usable against a clean wheel/sdist installation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DecisionDraft,
    DecisionRecord,
    FixtureBinding,
    FixtureSet,
    NormalizedAnswer,
    ProjectRecord,
    ProviderProfile,
)
from deykit.providers.choice import JevChoiceCompiler
from deykit.providers.fixtures import fixture_set_hash
from deykit.storage import FileProjectSource


def probe(cli: Path, project: Path) -> None:
    cli = cli.resolve()
    stamp = "2026-10-05T00:00:00Z"
    definition = ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose",
                options=(ChoiceOption(id="a", name="A"), ChoiceOption(id="b", name="B")),
            ),
        ),
    )
    profile = ProviderProfile(
        id="fixture-profile",
        adapter="fixture",
        requested_model="authored-p12",
        destination="fixture:jev-choice",
    )
    bindings = []
    for index, options in enumerate(
        (definition.questions[0].options, tuple(reversed(definition.questions[0].options)))
    ):
        ordered = definition.model_copy(
            update={"questions": (definition.questions[0].model_copy(update={"options": options}),)}
        )
        request = JevChoiceCompiler().compile(ordered, {"text": "frozen input"}, profile)
        bindings.append(
            FixtureBinding(
                id=f"binding-{index}",
                case_id="case",
                request=request,
                answer=NormalizedAnswer(
                    question_id="q", option_id="b", reported_model="authored-p12"
                ),
            )
        )
    fixtures = FixtureSet(
        id="set",
        decision_id="decision",
        dataset_id="data",
        name="Explicit two-order fixture",
        model_identity="authored-p12",
        bindings=tuple(bindings),
        content_hash="0" * 64,
        created_at=stamp,
    )
    fixtures = fixtures.model_copy(update={"content_hash": fixture_set_hash(fixtures)})
    missing = fixtures.model_copy(
        update={"id": "missing-set", "bindings": (bindings[0],), "content_hash": "0" * 64}
    )
    missing = missing.model_copy(update={"content_hash": fixture_set_hash(missing)})
    with FileProjectSource(project, create=True) as source:
        seed = (
            (ResourceKey("project", "p"), ProjectRecord(id="p", name="P12", created_at=stamp)),
            (ResourceKey("decisions", "decision"), DecisionRecord(id="decision", name="Decision")),
            (
                ResourceKey("drafts", "decision"),
                DecisionDraft(
                    decision_id="decision",
                    editor_source=dump_record(definition).decode(),
                    updated_at=stamp,
                ),
            ),
            (
                ResourceKey("datasets", "data"),
                DatasetRecord(id="data", name="Data", created_at=stamp),
            ),
            (
                ResourceKey("cases", "case", ("data",)),
                CaseRecord(
                    id="case",
                    dataset_id="data",
                    input_kind="json",
                    input_source='{"text":"frozen input","exact":9007199254740993}',
                ),
            ),
            (ResourceKey("fixtures", "set"), fixtures),
            (ResourceKey("fixtures", "missing-set"), missing),
        )
        source.commit(
            "seed", tuple(SourceChange(key, dump_record(record), None) for key, record in seed)
        )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    def invoke(*args: str, code: int = 0, project_root: Path | None = None):
        target = project if project_root is None else project_root
        completed = subprocess.run(
            [str(cli), "--json", "--project", str(target), *args],
            text=True,
            capture_output=True,
            env=environment,
            cwd=target.parent,
            timeout=60,
        )
        assert completed.returncode == code, (args, completed.stdout, completed.stderr)
        envelope = json.loads(completed.stdout)
        assert "frozen input" not in completed.stdout
        return envelope["data"] if "data" in envelope else envelope

    diagnose = (
        "diagnose",
        "choice-order",
        "--decision",
        "decision",
        "--dataset",
        "data",
        "--mode",
        "fixture",
        "--fixture-set",
        "set",
        "--attempt-limit",
        "2",
    )
    preview = invoke(*diagnose, "--dry-run")
    assert preview["initial_requests"] == 2 and preview["independent_case_count"] == 1
    assert (
        preview["identities"][0]["requests"][0]["request_hash"]
        != preview["identities"][1]["requests"][0]["request_hash"]
    )
    started = invoke(*diagnose, "--operation-id", "diagnose")
    group_id = started["group"]["group_id"]
    snapshot_id = started["group"]["snapshot_id"]
    assert started["group"]["attempts_used"] == 2
    assert started["summary"]["independent_case_count"] == 1
    assert invoke("diagnose", "show", group_id)["group"]["snapshot_id"] == snapshot_id
    assert invoke(*diagnose, "--operation-id", "diagnose")["group"]["replayed"]
    assert (
        invoke("diagnose", "resume", group_id, "--operation-id", "diag-resume")["group"][
            "attempts_used"
        ]
        == 2
    )
    run_id = started["group"]["members"][0]["run_id"]
    invoke("runs", "resume", run_id, code=2)
    regression = invoke(
        "regression",
        "add",
        run_id,
        "case",
        "--expected",
        "a",
        "--expected",
        "b",
        "--reason",
        "Accept either",
        "--provenance",
        "authored_fixture",
        "--operation-id",
        "save",
    )
    assert regression["provenance"] == "authored_fixture"
    assert len(invoke("regression", "list", "--decision", "decision")) == 1
    with FileProjectSource(project) as source:
        case_key = ResourceKey("cases", "case", ("data",))
        original = source.read(case_key)
        source.commit("delete-case", (SourceChange(case_key, None, original.etag),))
    check = (
        "check",
        "--decision",
        "decision",
        "--mode",
        "fixture",
        "--fixture-set",
        "set",
        "--attempt-limit",
        "1",
    )
    checked = invoke(*check, "--operation-id", "check")
    check_id = checked["group"]["group_id"]
    assert checked["cases"][0]["passed"] and checked["cases"][0]["actual_option_id"] == "b"
    assert checked["baseline_unavailable"] == "frozen_regression_selection"
    assert invoke("checks", "show", check_id)["cases"] == checked["cases"]
    assert (
        invoke("checks", "resume", check_id, "--operation-id", "check-resume")["group"][
            "attempts_used"
        ]
        == 1
    )
    removed = invoke(
        "regression",
        "remove",
        regression["id"],
        "--decision",
        "decision",
        "--operation-id",
        "remove",
    )
    assert removed["removed"] and invoke("regression", "list", "--decision", "decision") == []
    assert invoke(*check, "--operation-id", "check")["group"]["replayed"]
    historical_cases = invoke("checks", "show", check_id)["cases"]
    assert [
        (c["regression_id"], c["expected_option_ids"], c["actual_option_id"], c["passed"])
        for c in historical_cases
    ] == [
        (c["regression_id"], c["expected_option_ids"], c["actual_option_id"], c["passed"])
        for c in checked["cases"]
    ]
    invoke(*check, "--regression", regression["id"], code=2)
    # Authored original-only bindings never synthesize reordered answers.
    missing_args = list(diagnose)
    missing_args[missing_args.index("set")] = "missing-set"
    # Current case removed above; a restored case still uses exact authored original bytes.
    with FileProjectSource(project) as source:
        source.commit("restore-case", (SourceChange(original.key, original.body, None),))
    # Binding rejection is independent of the preceding history/replay scenario.
    # Reuse the exact authored seed, without its unrelated accumulated history.
    missing_project = project.with_name(f"{project.name} missing")
    with FileProjectSource(missing_project, create=True) as source:
        source.commit(
            "seed", tuple(SourceChange(key, dump_record(record), None) for key, record in seed)
        )
    missed = invoke(*missing_args, "--operation-id", "miss", code=3, project_root=missing_project)
    assert missed["group"]["attempts_used"] == 2
    missing_case = missed["group"]["members"][1]["cases"][0]
    assert missing_case["status"] == "response_error"
    assert missing_case["error"]["code"] == "missing_fixture"
    print("PASS P12 offline real-console fixture flow")


if __name__ == "__main__":
    probe(Path(sys.argv[1]), Path(sys.argv[2]))
