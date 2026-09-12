"""Tests for output-free package-management services."""

import json
import os
import sys
import threading
from pathlib import Path

import pytest

from src.services.package_manager import (
    CancellationToken,
    OperationCancelled,
    PackageManager,
    UpgradeResult,
)


def _make_pack(path: Path, pack_id: str, version: str = "1.0.0") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "name": f"{pack_id} name",
                "author": "Tester",
                "version": version,
                "description": "Service test pack",
            }
        ),
        encoding="utf-8",
    )
    (path / "plugin.py").write_text(
        "from core.base_plugin import BaseRecitePlugin\n"
        "class Plugin(BaseRecitePlugin):\n"
        "    def load_data(self): self.ids = ['1']\n"
        "    def get_all_problem_ids(self): return self.ids\n"
        "    def render_statement(self, pid): return pid\n"
        "    def check_answer(self, pid, value): return value == pid\n"
        "    def get_expected_display(self, pid): return pid\n",
        encoding="utf-8",
    )


def test_install_emits_progress_without_printing(tmp_path, capsys):
    source = tmp_path / "source"
    _make_pack(source, "progress-pack")
    manager = PackageManager()
    manager.packs_dir = str(tmp_path / "packs")
    os.makedirs(manager.packs_dir)

    events = []
    pack_id = manager.install_pack(str(source), progress=events.append)

    captured = capsys.readouterr()
    assert pack_id == "progress-pack"
    assert captured.out == ""
    assert captured.err == ""
    assert any("Installing pack" in event.message for event in events)


def test_upgrade_all_results_contains_per_pack_status(monkeypatch, tmp_path):
    manager = PackageManager()
    manager.packs_dir = str(tmp_path / "packs")
    os.makedirs(manager.packs_dir)
    monkeypatch.setattr(
        manager,
        "list_packs",
        lambda: [{"id": "a"}, {"id": "b"}],
    )
    monkeypatch.setattr(
        manager,
        "upgrade_pack_result",
        lambda pack_id, progress=None, cancel_token=None: UpgradeResult(
            pack_id=pack_id,
            status="failed" if pack_id == "b" else "current",
            error="network" if pack_id == "b" else None,
        ),
    )

    results = manager.upgrade_all_results()

    assert results["a"].status == "current"
    assert results["b"].failed
    assert results["b"].error == "network"


def test_install_observes_cancellation_before_writing(tmp_path):
    source = tmp_path / "source"
    _make_pack(source, "cancelled-pack")
    manager = PackageManager()
    manager.packs_dir = str(tmp_path / "packs")
    os.makedirs(manager.packs_dir)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(OperationCancelled):
        manager.install_pack(str(source), cancel_token=token)

    assert not os.path.exists(os.path.join(manager.packs_dir, "cancelled-pack"))


def test_subprocess_cancellation_terminates_running_process():
    manager = PackageManager()
    token = CancellationToken()
    timer = threading.Timer(0.1, token.cancel)
    timer.start()
    try:
        with pytest.raises(OperationCancelled):
            manager._run_subprocess(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                timeout=10,
                cancel_token=token,
            )
    finally:
        timer.cancel()
