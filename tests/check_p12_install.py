"""Build first; verify real P12 console fixture flows in clean artifact environments."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from check_install import run


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    assert uv is not None
    artifacts = sorted((root / "dist").glob("deykit-*"))
    assert len(artifacts) == 2
    with tempfile.TemporaryDirectory(prefix="deykit P12 install ü ") as directory:
        destination = Path(directory)
        for index, artifact in enumerate(artifacts):
            environment = destination / f"venv {index} é"
            run(uv, "venv", "--python", sys.executable, str(environment), cwd=destination)
            binary = environment / ("Scripts" if os.name == "nt" else "bin")
            python = binary / ("python.exe" if os.name == "nt" else "python")
            cli = binary / ("deykit.exe" if os.name == "nt" else "deykit")
            run(uv, "pip", "install", "--python", str(python), str(artifact), cwd=destination)
            context = {**os.environ, "PATH": str(binary)}
            context.pop("PYTHONPATH", None)
            output = run(
                str(python),
                "-I",
                str(root / "tests" / "p12_console_probe.py"),
                str(cli),
                str(destination / f"project {index} é"),
                cwd=destination,
                env=context,
            )
            assert "PASS P12 offline real-console fixture flow" in output
            print(f"PASS clean P12 installed console: {artifact.name}")


if __name__ == "__main__":
    main()
