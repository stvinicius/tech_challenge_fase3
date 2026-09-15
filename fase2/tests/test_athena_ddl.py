from pathlib import Path
import subprocess
import os


def test_render_athena_ddl_uses_project_name(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    script = repo / "infrastructure" / "render_athena_ddl.sh"
    out = tmp_path / "athena.sql"
    env = {**os.environ, "PROJECT_NAME": "demo-literacy-xyz"}
    result = subprocess.run(
        ["bash", str(script), str(out)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    body = out.read_text()
    assert "s3://demo-literacy-xyz-gold/" in body
    assert "CREATE DATABASE IF NOT EXISTS demo_literacy_xyz" in body
    assert "__GOLD_BUCKET__" not in body
    assert "official_state_indicator_rate" in body
