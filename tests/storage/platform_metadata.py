"""Print the actual host and test-volume identity; contains no provider calls."""

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def command(args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()


root = Path(tempfile.gettempdir())
if os.name == "nt":
    filesystem = command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-Volume -DriveLetter '{root.drive[0]}' "
            "| Select-Object DriveLetter,FileSystem | ConvertTo-Json",
        ]
    )
elif sys.platform == "darwin":
    filesystem = command(["stat", "-f", "%T", str(root)])
else:
    filesystem = command(["stat", "-f", "-c", "%T", str(root)])
print(
    json.dumps(
        {
            "os": platform.platform(),
            "architecture": platform.machine(),
            "python": sys.version,
            "sqlite": sqlite3.sqlite_version,
            "filesystem": filesystem,
            "test_temp_root": str(root),
            "runner_os": os.environ.get("RUNNER_OS"),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
            "commit": os.environ.get("GITHUB_SHA"),
            "lockfile_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
            "evidence": "Automated software tests; no physical desktop/power-loss/live evidence",
        },
        indent=2,
    )
)
