"""Create on Ubuntu; open/replay/rebuild the exact archived project on each CI OS."""

import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, ProjectRecord
from deykit.storage import FileProjectSource

PROJECT = ProjectRecord(id="portable", name="Portable café", created_at="2026-10-05T00:00:00Z")
CASE = CaseRecord(
    id="exact",
    dataset_id="data",
    input_kind="json",
    input_source='{"n":9007199254740993.0000000000000000001,"text":"فارسی"}',
)
CHANGES = (
    SourceChange(ResourceKey("project", "portable"), dump_record(PROJECT), None),
    SourceChange(ResourceKey("cases", "exact", ("data",)), dump_record(CASE), None),
)


def hashes(root):
    return {
        p.relative_to(root).as_posix(): bytes_hash(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".deykit" not in p.parts
    }


def main():
    mode, archive = sys.argv[1], Path(sys.argv[2])
    with tempfile.TemporaryDirectory(prefix="deykit copy café ") as temporary:
        root = Path(temporary) / "project فارسی"
        if mode == "create":
            with FileProjectSource(root, create=True) as source:
                source.commit("seed", CHANGES)
            digest = hashes(root)
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                for name in digest:
                    bundle.write(root / name, "project/" + name)
                bundle.writestr("hashes.json", json.dumps(digest, sort_keys=True))
        elif mode == "verify":
            with zipfile.ZipFile(archive) as bundle:
                # Only the artifact produced by this workflow is accepted here.
                bundle.extractall(root.parent / "unpacked")
            unpacked = root.parent / "unpacked"
            shutil.move(str(unpacked / "project"), root)
            digest = json.loads((unpacked / "hashes.json").read_text(encoding="utf-8"))
            assert hashes(root) == digest
            with FileProjectSource(root) as source:
                assert len(source.capture_snapshot()) == 2
                assert source.read(CHANGES[1].key).body == dump_record(CASE)
                assert source.commit("seed", CHANGES).replayed
                source.rebuild_index()
            assert hashes(root) == digest
        else:
            raise ValueError("Expected create or verify")
        print(f"PASS {mode}: {len(digest)} unchanged authoritative byte hashes")


if __name__ == "__main__":
    main()
