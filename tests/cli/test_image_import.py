"""The CLI reviews local preparation, commits it and replays without source files."""

import json
import shutil
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from deykit.cli.main import app
from deykit.contracts.json_value import parse_json


def test_cli_image_preview_commit_replay_and_portable_project(tmp_path, monkeypatch):
    runner = CliRunner()
    project = tmp_path / "project é"
    root = tmp_path / "original images"
    root.mkdir()
    Image.new("RGB", (2, 1), (255, 0, 0)).save(root / "photo.png")

    def call(*arguments, expected=0):
        result = runner.invoke(app, ["--project", str(project), "--json", *arguments])
        assert result.exit_code == expected, result.output
        envelope = json.loads(result.stdout)
        assert envelope["schema_version"] == 1
        return envelope

    call("init", str(project), "--operation-id", "init")
    call("dataset", "create", "products", "--name", "Products", "--operation-id", "dataset")
    rows = tmp_path / "rows.jsonl"
    rows.write_text(
        '{"id":"p1","text":"red","photo":"photo.png","metadata":{"private":"kept outside input"}}\n'
    )
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "input_kind": "text",
                "input_column": "text",
                "id_column": "id",
                "metadata_column": "metadata",
                "images": [
                    {
                        "name": "product",
                        "source": "photo",
                        "preparation": {"mode": "pad", "min_width": 4, "min_height": 4},
                    }
                ],
            }
        )
    )
    preview = call(
        "dataset",
        "import",
        "products",
        "--file",
        str(rows),
        "--format",
        "jsonl",
        "--mapping",
        str(mapping),
        "--asset-root",
        str(root),
        "--dry-run",
    )
    row = preview["data"]["preview"]["rows"][0]
    assert row["errors"] == []
    assert (row["assets"][0]["source"]["width"], row["assets"][0]["prepared"]["width"]) == (2, 4)
    assert row["case"]["input_source"] == '"red"'
    assert call("case", "list", "--dataset", "products")["data"]["total"] == 0
    reviewed = tmp_path / "preview.json"
    reviewed.write_text(json.dumps(preview))
    arguments = (
        "dataset",
        "import",
        "products",
        "--preview",
        str(reviewed),
        "--asset-root",
        str(root),
        "--operation-id",
        "import-image",
    )
    assert call(*arguments)["data"]["result"]["imported_case_ids"] == ["p1"]
    call(
        "dataset",
        "create",
        "prepared-assets",
        "--name",
        "Prepared images",
        "--operation-id",
        "staging-dataset",
    )
    preserve_mapping = json.loads(mapping.read_text())
    preserve_mapping["images"][0]["preparation"] = {"mode": "preserve"}
    mapping.write_text(json.dumps(preserve_mapping))
    staged = call(
        "dataset",
        "import",
        "prepared-assets",
        "--file",
        str(rows),
        "--format",
        "jsonl",
        "--mapping",
        str(mapping),
        "--asset-root",
        str(root),
        "--dry-run",
    )
    staged_path = tmp_path / "staged-preview.json"
    staged_path.write_text(json.dumps(staged))
    call(
        "dataset",
        "import",
        "prepared-assets",
        "--preview",
        str(staged_path),
        "--asset-root",
        str(root),
        "--operation-id",
        "import-prepared",
    )
    original = call("case", "show", "p1", "--dataset", "products")
    prepared = call("case", "show", "p1", "--dataset", "prepared-assets")
    (tmp_path / "original.json").write_text(json.dumps(original))
    (tmp_path / "prepared.json").write_text(json.dumps(prepared))
    dataset_etag = call("dataset", "show", "products")["data"]["dataset"]["etag"]
    guide = (Path(__file__).parents[2] / "guide" / "imports.md").read_text()
    snippet = guide.split("```python\n", 1)[1].split("```", 1)[0]
    monkeypatch.chdir(tmp_path)
    exec(compile(snippet, "guide/imports.md", "exec"), {})
    call(
        "case",
        "edit",
        "p1",
        "--dataset",
        "products",
        "--file",
        str(tmp_path / "case-edit.json"),
        "--if-hash",
        original["data"]["etag"],
        "--if-dataset-hash",
        dataset_etag,
        "--operation-id",
        "switch-preparation",
    )
    switched = call("case", "show", "p1", "--dataset", "products")["data"]["record"]
    assert switched["images"] == prepared["data"]["record"]["images"]
    assert switched["images"] != original["data"]["record"]["images"]
    assert switched["metadata_source"] == original["data"]["record"]["metadata_source"]
    assert switched["input_source"] == original["data"]["record"]["input_source"]
    shutil.rmtree(root)
    assert call(*arguments)["data"]["result"]["replayed"]
    saved = call("case", "show", "p1", "--dataset", "products")["data"]["record"]
    assert parse_json(saved["metadata_source"]) == {"private": "kept outside input"}
    assert str(root) not in next((project / "source" / "image_assets").glob("*.json")).read_text()
    call("project", "validate")
    copied = tmp_path / "copied project"
    shutil.copytree(project, copied)
    project = copied
    call("project", "validate")
