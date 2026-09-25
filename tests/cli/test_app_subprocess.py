"""Black-box tests for the traditional CLI contract."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*args: str, home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "muninn.main", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _make_pack(path: Path, pack_id: str) -> None:
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "name": pack_id,
                "version": "1.0.0",
                "entrypoint": "plugin:Plugin",
                "api_version": "1",
            }
        ),
        encoding="utf-8",
    )
    (path / "plugin.py").write_text(
        "from muninn.plugin_api import BaseTrainingPlugin\n"
        "class Plugin(BaseTrainingPlugin):\n"
        "    def load_data(self): self.ids=[]\n"
        "    def get_all_problem_ids(self): return self.ids\n"
        "    def render_statement(self, pid): return ''\n"
        "    def check_answer(self, pid, value): return False\n"
        "    def get_expected_display(self, pid): return ''\n",
        encoding="utf-8",
    )


def test_version_uses_stdout(tmp_path):
    result = _run_cli("--version", home=tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("Muninn ")
    assert result.stderr == ""


def test_install_and_list_use_expected_streams(tmp_path):
    source = tmp_path / "source"
    _make_pack(source, "cli-pack")

    installed = _run_cli("install", str(source), home=tmp_path)
    listed = _run_cli("list", home=tmp_path)

    assert installed.returncode == 0
    assert "Successfully installed pack 'cli-pack'" in installed.stdout
    assert "Installing pack" in installed.stderr
    assert listed.returncode == 0
    assert "cli-pack" in listed.stdout


def test_failed_upgrade_returns_nonzero_and_uses_stderr(tmp_path):
    source = tmp_path / "source"
    _make_pack(source, "gone-pack")
    assert _run_cli("install", str(source), home=tmp_path).returncode == 0

    for path in source.iterdir():
        path.unlink()
    source.rmdir()

    result = _run_cli("upgrade", "gone-pack", home=tmp_path)

    assert result.returncode == 1
    assert "Could not fetch remote manifest" in result.stderr
    assert "Traceback" not in result.stderr


def test_run_missing_pack_fails_without_starting_tui(tmp_path):
    result = _run_cli("run", "missing-pack", home=tmp_path)

    assert result.returncode == 1
    assert "Pack 'missing-pack' not found" in result.stderr
