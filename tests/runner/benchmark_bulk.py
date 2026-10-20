"""Offline scaling probe over the real file source and a controlled fake transport."""

import argparse
import asyncio
import cProfile
import json
import platform
import pstats
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from conftest import Factory, answer, seed

from deykit.application.execution import ExecutionService
from deykit.application.imports import ImportService
from deykit.cli.context import SystemClock
from deykit.contracts.records import ExecutionSettings
from deykit.domain.import_mapping import ImportMapping, InputField
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--controls", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if not 1 <= args.count <= 10_000 or not 1 <= args.concurrency <= 64:
        parser.error("count must be 1..10000 and concurrency 1..64")
    factory = Factory()
    with FileProjectSource(args.output / "project", create=True) as source:
        started = time.perf_counter()
        seed(source, 0)
        seeded = time.perf_counter()
        importer = ImportService(source, SystemClock())
        text = "\n".join(
            json.dumps({"id": f"case-{index:05}", "text": f"Text {index}"})
            for index in range(args.count)
        )
        (args.output / "input.jsonl").write_text(text, encoding="utf-8")
        preview_import = importer.preview(
            "data",
            text,
            format="jsonl",
            mapping=ImportMapping(
                input_kind="json",
                id_column="id",
                fields=(InputField(source="text", target="text"),),
            ),
        )

        def record_json(value):
            return value.model_dump(mode="json")

        (args.output / "import-preview.json").write_text(
            json.dumps(asdict(preview_import), default=record_json), encoding="utf-8"
        )
        importer.commit(preview_import, operation_id="import")
        imported = time.perf_counter()
        print(f"Imported {args.count} cases", file=sys.stderr, flush=True)
        service = ExecutionService(source, source, factory, SystemClock())
        request = RunRequest(
            decision_id="decision",
            dataset_id="data",
            mode="fixture",
            fixture_set_id="set",
            settings=ExecutionSettings(
                max_attempts=args.count + (args.concurrency if args.controls else 0),
                concurrency=args.concurrency,
                deadline_seconds=86400,
            ),
        )
        preview = service.preview(request)
        planned = time.perf_counter()
        (args.output / "run-preview.json").write_text(
            json.dumps(asdict(preview), default=record_json), encoding="utf-8"
        )
        profiles = []
        if args.profile:
            original_epoch = source.consistent_read

            @contextmanager
            def profile_epoch():
                profiler = (
                    cProfile.Profile() if not getattr(source._local, "source_depth", 0) else None
                )
                if profiler is not None:
                    profiler.enable()
                try:
                    with original_epoch() as admitted:
                        yield admitted
                finally:
                    if profiler is not None:
                        profiler.disable()
                        profiles.append(profiler)

            source.consistent_read = profile_epoch

        controls = {}
        run_ids = []

        def cli(*arguments):
            started = time.perf_counter()
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from deykit.cli.main import app; app()",
                    "--project",
                    str(source.root),
                    "--json",
                    *arguments,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            elapsed = time.perf_counter() - started
            assert completed.returncode == 0, completed.stdout + completed.stderr
            envelope = json.loads(completed.stdout)
            assert envelope["schema_version"] == 1 and "data" in envelope
            assert elapsed < 5
            return envelope["data"], elapsed

        async def exercise():
            if not args.controls:
                return await service.start(request, operation_id="benchmark")
            ready, release = asyncio.Event(), asyncio.Event()

            async def transport(_case_id, _request):
                if len(factory.calls) == min(args.count, args.concurrency):
                    ready.set()
                await release.wait()
                return answer()

            factory.callback = transport
            task = asyncio.create_task(
                service.start(
                    request,
                    operation_id="benchmark",
                    on_created=lambda created: run_ids.append(created.run_id),
                )
            )
            try:
                await asyncio.wait_for(ready.wait(), 120)
                shown, show_seconds = await asyncio.to_thread(cli, "runs", "show", run_ids[0])
                assert shown["attempts_used"] == min(args.count, args.concurrency)
                _, cancel_seconds = await asyncio.to_thread(
                    cli, "runs", "cancel", run_ids[0], "--operation-id", "benchmark-cancel"
                )
                release.set()
                cancelled = await task
                assert cancelled.state == "cancelled"
                controls.update(
                    show_seconds=show_seconds,
                    cancel_seconds=cancel_seconds,
                    calls_at_cancel=len(factory.calls),
                )
                factory.callback = None
                return await service.resume(cancelled.run_id, operation_id="benchmark-resume")
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        result = asyncio.run(exercise())
        executed = time.perf_counter()
        shown = service.show(result.run_id)
        inspected = time.perf_counter()
        if profiles:
            with (args.output / "profile.txt").open("w") as stream:
                stats = pstats.Stats(profiles[0], stream=stream)
                for profile in profiles[1:]:
                    stats.add(profile)
                stats.sort_stats("cumulative").print_stats(40)
                stats.dump_stats(args.output / "profile.pstats")
        assert result.state == "completed" and len(factory.calls) == args.count
        assert len({case for case, _, _ in factory.calls}) == args.count
        assert sum(case.status == "valid" for case in shown.cases) == args.count
        receipt = dict(
            count=args.count,
            python=platform.python_version(),
            platform=platform.system() + " " + platform.machine(),
            concurrency=args.concurrency,
            option_count=2,
            controls=controls,
            profiled=args.profile,
            run_id=result.run_id,
            attempts=result.attempts_used,
            planned=preview.initial_requests,
            calls=len(factory.calls),
            state=result.state,
            seed_seconds=seeded - started,
            import_seconds=imported - seeded,
            preview_seconds=planned - imported,
            execution_seconds=executed - planned,
            read_seconds=inspected - executed,
            evidence_mode="controlled_fake_transport",
            transport_latency_seconds=0,
        )
        (args.output / "summary.json").write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt), flush=True)
        assert result.state == "completed" and len(factory.calls) == args.count


if __name__ == "__main__":
    main()
