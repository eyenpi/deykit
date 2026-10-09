"""Start the qualified installed M10 browser server with fake provider ports."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "docs"
        / "verification"
        / "M08-installed-api-reference.py",
    )
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("m08_installed_api_reference", args.reference)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot_load_installed_api_reference")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.serve_installed_api(args.workspace, args.ready_file)


if __name__ == "__main__":
    main()
