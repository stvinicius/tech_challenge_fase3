#!/usr/bin/env python3
"""
Orchestrator -- runs the full batch pipeline in sequence: ingest ->
silver (with quality gate) -> gold, with centralized logging (CloudWatch
when running on Lambda/EC2/ECS; terminal when running locally).

Each stage is the same script that can also be run in isolation:

  1. ingest  -> pipelines/batch/ingest_batch.py    (raw_downloads/ -> S3 Bronze)
  2. silver  -> pipelines/batch/process_silver.py  (S3 Bronze -> S3 Silver)
  3. gold    -> pipelines/batch/build_gold.py      (S3 Silver -> S3 Gold)

Quality validation (`quality/validations.py`) is not a stage of its own in
the orchestrator: it already runs *inside* the "silver" stage, as a gate
between the integration of the 6 entities and the S3 write (see
`process_silver.py`) -- if the checks fail, Silver is not written and the
"silver" stage exits with an error, stopping the pipeline before Gold. This
reflects the actual flow described in the project plan (ingest -> quality ->
silver -> gold): quality is the "gate" between the transformation and the
Silver write, not a loose process that runs on its own.

Each stage is launched as an independent Python subprocess (same interpreter
as the orchestrator), preserving each script's own `argparse` and behavior.
Each subprocess's output (stdout/stderr) is inherited by the orchestrator
process, so the entire pipeline log stays on the same stream -- exactly what
CloudWatch Logs captures in full when the orchestrator runs as a scheduled
job on Lambda, ECS/Fargate, EC2, etc. If a stage fails (exit code != 0), the
pipeline stops immediately and the following stages do not run -- the same
"don't move bad data to the next layer" rule used inside each script.

Usage:
  python pipelines/orchestrator.py
  python pipelines/orchestrator.py --dry-run                  # no stage touches real S3
  python pipelines/orchestrator.py --stages silver gold        # reprocess only silver + gold
  python pipelines/orchestrator.py --stages ingest --dry-run   # only validates the input CSVs
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # enables `import common`
from common import get_logger  # noqa: E402

logger = get_logger("orchestrator")

PIPELINES_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINES_DIR.parent
BATCH_DIR = PIPELINES_DIR / "batch"


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    script: Path


STAGES: tuple[Stage, ...] = (
    Stage("ingest", "ingest (raw_downloads/ -> Bronze)", BATCH_DIR / "ingest_batch.py"),
    Stage("silver", "silver + quality gate (Bronze -> Silver)", BATCH_DIR / "process_silver.py"),
    Stage("gold", "gold (Silver -> Gold)", BATCH_DIR / "build_gold.py"),
)
STAGES_BY_KEY = {stage.key: stage for stage in STAGES}


def run_stage(stage: Stage, dry_run: bool) -> tuple[bool, float]:
    """Runs a stage as a subprocess and returns (success, duration in
    seconds). stdout/stderr are inherited from the orchestrator (same
    stream, not captured)."""
    cmd = [sys.executable, str(stage.script)]
    if dry_run:
        cmd.append("--dry-run")

    logger.info("-> Starting stage '%s': %s", stage.key, " ".join(cmd))
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, cwd=str(REPO_ROOT))
        returncode = result.returncode
    except OSError:
        logger.exception("Failed to start the subprocess for stage '%s'", stage.key)
        returncode = 1
    elapsed = time.monotonic() - start

    ok = returncode == 0
    log = logger.info if ok else logger.error
    log(
        "[%s] Stage '%s' finished in %.1fs (exit code %d)",
        "OK" if ok else "FAILED",
        stage.key,
        elapsed,
        returncode,
    )
    return ok, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=list(STAGES_BY_KEY),
        default=list(STAGES_BY_KEY),
        metavar="{ingest,silver,gold}",
        help="Subset of stages to run, in the given order (default: all, in sequence)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Propagates --dry-run to all selected stages (read/write locally, without touching S3)",
    )
    args = parser.parse_args()

    selected = [STAGES_BY_KEY[key] for key in args.stages]

    logger.info("== Pipeline orchestrator: %s ==", " -> ".join(s.key for s in selected))
    if args.dry_run:
        logger.info("--dry-run mode: no stage will read/write real S3 data")

    summary: list[tuple[Stage, bool, float]] = []
    start_total = time.monotonic()
    for stage in selected:
        ok, elapsed = run_stage(stage, args.dry_run)
        summary.append((stage, ok, elapsed))
        if not ok:
            logger.error(
                "Pipeline stopped: stage '%s' failed -- the following stages will not run",
                stage.key,
            )
            break
    total_elapsed = time.monotonic() - start_total

    logger.info("-- Run summary (%.1fs total) --", total_elapsed)
    for stage, ok, elapsed in summary:
        logger.info("  [%s] %s (%.1fs)", "OK" if ok else "FAILED", stage.name, elapsed)
    for stage in selected[len(summary):]:
        logger.warning("  [NOT RUN] %s", stage.name)

    if not all(ok for _, ok, _ in summary):
        logger.error("Pipeline finished with FAILURE")
        return 1

    logger.info("Pipeline finished with SUCCESS: %d/%d stage(s)", len(summary), len(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
