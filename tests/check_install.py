"""Build first, then run `uv run python tests/check_install.py`.
Dependency installation may use the package registry.

Each artifact gets a clean environment in a path with spaces and non-ASCII characters.
Imports/CLI run outside the checkout with no Node or other system tools on PATH.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


def run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr)
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", completed.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use cached dependencies only.")
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    assert uv is not None
    artifacts = sorted(root.joinpath("dist").glob("deykit-*"))
    assert len(artifacts) == 2, artifacts
    with tempfile.TemporaryDirectory(prefix="deykit install ü ") as temp:
        destination = Path(temp).resolve()
        requirements = destination / "locked-runtime.txt"
        run(
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--output-file",
            str(requirements),
            cwd=root,
        )
        for index, artifact in enumerate(artifacts):
            if artifact.suffix == ".whl":
                with zipfile.ZipFile(artifact) as package:
                    names = package.namelist()
            else:
                with tarfile.open(artifact) as package:
                    names = package.getnames()
            assert not any(
                "frontend/" in name
                or "deykit/api/static/" in name
                or name.endswith(("api/assets.py", "bundle-ui.py"))
                for name in names
            ), "UI files remain in the package"

            environment = destination / f"venv {index} é"
            run(uv, "venv", "--python", sys.executable, str(environment), cwd=destination)
            bin_dir = environment / ("Scripts" if os.name == "nt" else "bin")
            python = bin_dir / ("python.exe" if os.name == "nt" else "python")
            offline = ("--offline",) if options.offline else ()
            run(
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                *offline,
                "--requirement",
                str(requirements),
                cwd=destination,
            )
            run(
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                *offline,
                "--no-deps",
                str(artifact),
                cwd=destination,
            )
            env = {"PATH": str(bin_dir)}
            if os.name == "nt" and "SystemRoot" in os.environ:
                env["SystemRoot"] = os.environ["SystemRoot"]
            cli = bin_dir / ("deykit.exe" if os.name == "nt" else "deykit")
            assert run(str(cli), "--version", cwd=destination, env=env).strip() == "0.1.0"
            assert "--version" in run(str(cli), "--help", cwd=destination, env=env)
            code = (
                "from deykit.contracts.json_value import JsonDocument; "
                "from deykit.contracts.records import CaseRecord; "
                "from deykit.contracts.codec import dump_record,load_record; "
                "s='{\\\"n\\\":9007199254740993}'; "
                "c=CaseRecord(id='c',dataset_id='d',input_kind='json',input_source=s); "
                "assert load_record(CaseRecord,dump_record(c))==c; "
                "assert JsonDocument(s).select(('n',)).source=='{\\\"n\\\":9007199254740993}'"
            )
            run(str(python), "-I", "-c", code, cwd=destination, env=env)
            run(str(cli), "demo", str(destination / f"demo {index} ü"), cwd=destination, env=env)
            if artifact.suffix == ".whl":
                run(
                    str(python),
                    "-I",
                    "-m",
                    "deykit.resources.cli_workflow.workflow",
                    "--cli",
                    str(cli),
                    "--output",
                    str(destination / "terminal walkthrough ü"),
                    cwd=destination,
                    env=env,
                )
                print("PASS complete installed authored CLI walkthrough")
            print(f"PASS clean installation: {artifact.name}; CLI without Node on PATH")


if __name__ == "__main__":
    main()
