"""Validate/copy the genuine production frontend bundle to package resources."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "dist"
TARGET = ROOT / "src" / "deykit" / "api" / "static"
LICENSE_SOURCE = SOURCE / ".vite" / "license.md"
LICENSE_TARGET = ROOT / "src" / "deykit" / "api" / "THIRD-PARTY-NOTICES.md"
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def bundle() -> dict[str, bytes]:
    if not SOURCE.is_dir() or not (SOURCE / "index.html").is_file():
        raise SystemExit("Production frontend is absent. Run npm run build in frontend first.")
    if not LICENSE_SOURCE.is_file() or LICENSE_SOURCE.is_symlink():
        raise SystemExit("Vite third-party license inventory is absent.")
    result = {}
    entries = []
    for path in sorted(SOURCE.rglob("*")):
        if path.is_symlink():
            raise SystemExit("Symlink in production bundle")
        if not path.is_file() or path == LICENSE_SOURCE:
            continue
        name = path.relative_to(SOURCE).as_posix()
        if not name.isascii() or path.suffix not in MIME or path.name.startswith("."):
            raise SystemExit("Unsupported production bundle file")
        body = path.read_bytes()
        result[name] = body
        entries.append(
            {
                "name": name,
                "sha256": hashlib.sha256(body).hexdigest(),
                "content_type": MIME[path.suffix],
            }
        )
    result["manifest.json"] = (
        json.dumps({"schema_version": 1, "assets": entries}, sort_keys=True, indent=2) + "\n"
    ).encode()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = bundle()
    license_body = LICENSE_SOURCE.read_bytes()
    if not license_body or len(license_body) > 2_097_152:
        raise SystemExit("Invalid production third-party license inventory")
    if args.check:
        if (
            not LICENSE_TARGET.is_file()
            or LICENSE_TARGET.is_symlink()
            or LICENSE_TARGET.read_bytes() != license_body
        ):
            raise SystemExit("Packaged third-party notices differ from the production build")
        actual = {}
        for path in TARGET.rglob("*"):
            if path.is_symlink():
                raise SystemExit("Symlink in packaged frontend")
            if path.is_file():
                actual[path.relative_to(TARGET).as_posix()] = path.read_bytes()
        if actual != expected:
            raise SystemExit("Packaged UI differs from production frontend; regenerate bundle")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.is_symlink():
        raise SystemExit("Refusing to replace a symlinked UI directory")
    if LICENSE_TARGET.is_symlink():
        raise SystemExit("Refusing to replace a symlinked third-party notice")
    with tempfile.TemporaryDirectory(prefix="deykit-ui-", dir=TARGET.parent) as temp:
        staged = Path(temp)
        for name, body in expected.items():
            file = staged / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(body)
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.copytree(staged, TARGET)
    with tempfile.NamedTemporaryFile(dir=LICENSE_TARGET.parent, delete=False) as staged_license:
        staged_license.write(license_body)
        staged_name = Path(staged_license.name)
    os.replace(staged_name, LICENSE_TARGET)


if __name__ == "__main__":
    main()
