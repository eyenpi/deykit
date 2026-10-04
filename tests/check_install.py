"""Build first, then run `uv run python tests/check_install.py`.
Dependency installation may use the package registry.

Each artifact gets a clean environment in a path with spaces and non-ASCII characters.
Imports/CLI run outside the checkout with no Node or other system tools on PATH.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr)
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", completed.stdout)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    assert uv is not None
    artifacts = sorted(root.joinpath("dist").glob("deykit-*"))
    assert len(artifacts) == 2, artifacts
    with tempfile.TemporaryDirectory(prefix="deykit install ü ") as temp:
        destination = Path(temp)
        for index, artifact in enumerate(artifacts):
            environment = destination / f"venv {index} é"
            run(uv, "venv", "--python", sys.executable, str(environment), cwd=destination)
            bin_dir = environment / ("Scripts" if os.name == "nt" else "bin")
            python = bin_dir / ("python.exe" if os.name == "nt" else "python")
            run(
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                str(artifact),
                cwd=destination,
            )
            env = {**os.environ, "PATH": str(bin_dir)}
            env.pop("PYTHONPATH", None)
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
            print(f"PASS clean installation: {artifact.name}; CLI without Node on PATH")


if __name__ == "__main__":
    main()
