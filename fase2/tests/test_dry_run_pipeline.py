import sys
from pathlib import Path

import pandas as pd

from tests.helpers import write_min_csvs

REPO = Path(__file__).resolve().parents[1]
BATCH = REPO / "pipelines" / "batch"


def _run(script: Path, *args: str) -> None:
    import subprocess

    cmd = [sys.executable, str(script), *args]
    result = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_ingest_silver_gold_dry_run_is_offline(tmp_path):
    csv_dir = tmp_path / "raw"
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    quality = tmp_path / "quality"
    write_min_csvs(csv_dir)

    _run(
        BATCH / "ingest_batch.py",
        "--dry-run",
        "--input-dir",
        str(csv_dir),
        "--output-dir",
        str(bronze),
    )
    assert (bronze / "batch" / "states" / "states.parquet").exists()
    assert (
        bronze / "batch" / "child_literacy_indicator_uf" / "child_literacy_indicator_uf.parquet"
    ).exists()

    _run(
        BATCH / "process_silver.py",
        "--dry-run",
        "--bronze-dir",
        str(bronze),
        "--output-dir",
        str(silver),
        "--quality-output-dir",
        str(quality),
    )
    silver_files = list(silver.rglob("*.parquet"))
    assert silver_files
    silver_df = pd.concat([pd.read_parquet(p) for p in silver_files], ignore_index=True)
    assert "state_indicator_literacy_rate" in silver_df.columns
    assert silver_df["state_indicator_literacy_rate"].notna().all()
    years = {
        int(part.split("=", 1)[1])
        for path in silver_files
        for part in path.parts
        if part.startswith("year=")
    }
    assert years == {2023, 2024}

    _run(
        BATCH / "build_gold.py",
        "--dry-run",
        "--silver-dir",
        str(silver),
        "--output-dir",
        str(gold),
    )
    evolution = pd.read_parquet(gold / "time_evolution" / "time_evolution.parquet")
    assert "official_state_indicator_rate" in evolution.columns
    state_rows = evolution[evolution["aggregation_level"] == "state"]
    assert state_rows["official_state_indicator_rate"].notna().all()
