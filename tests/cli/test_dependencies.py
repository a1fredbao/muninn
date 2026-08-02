"""Tests for shared-venv dependency management."""

import json
import os
import subprocess
import sys
import sysconfig

from src.cli.manager import PackageManager


class TestEnsureVenv:
    def test_creates_venv_when_missing(self, monkeypatch, tmp_path):
        venv_dir = tmp_path / "venv"
        m = PackageManager()
        monkeypatch.setattr(m, "venv_dir", str(venv_dir))

        python_exe = m._ensure_venv()

        assert os.path.isfile(python_exe)
        assert os.path.isdir(str(venv_dir))

    def test_reuses_existing_venv(self, monkeypatch, tmp_path):
        venv_dir = tmp_path / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
        )

        m = PackageManager()
        monkeypatch.setattr(m, "venv_dir", str(venv_dir))

        python_exe = m._ensure_venv()
        assert os.path.isfile(python_exe)


class TestGetVenvSitePackages:
    def test_returns_valid_path(self, monkeypatch, tmp_path):
        venv_dir = tmp_path / "venv"
        m = PackageManager()
        monkeypatch.setattr(m, "venv_dir", str(venv_dir))

        site_pkgs = m._get_venv_site_packages()
        assert "site-packages" in site_pkgs
        assert str(venv_dir) in site_pkgs

    def test_matches_venv_scheme(self, monkeypatch, tmp_path):
        venv_dir = tmp_path / "venv"
        m = PackageManager()
        monkeypatch.setattr(m, "venv_dir", str(venv_dir))

        site_pkgs = m._get_venv_site_packages()
        expected = sysconfig.get_path(
            "purelib", scheme="venv", vars={"base": str(venv_dir)}
        )
        assert site_pkgs == expected


class TestInstallPackDependencies:
    def test_noop_when_no_requirements_file(self, monkeypatch, tmp_path):
        pack_dir = tmp_path / "pack"
        os.makedirs(pack_dir)

        m = PackageManager()
        monkeypatch.setattr(m, "venv_dir", str(tmp_path / "venv_noexist"))
        # Should not raise
        m._install_pack_dependencies(str(pack_dir))

    def test_noop_when_requirements_is_empty(self, monkeypatch, tmp_path):
        pack_dir = tmp_path / "pack"
        os.makedirs(pack_dir)
        (pack_dir / "requirements.txt").write_text("")

        m = PackageManager()
        monkeypatch.setattr(m, "venv_dir", str(tmp_path / "venv_noexist"))
        m._install_pack_dependencies(str(pack_dir))

    def test_invokes_pip_with_correct_args(self, monkeypatch, tmp_path):
        """Verify that pip is called with the right arguments."""
        venv_dir = tmp_path / "venv"
        pack_dir = tmp_path / "pack"
        os.makedirs(pack_dir)
        req_path = pack_dir / "requirements.txt"
        req_path.write_text("foo>=1.0")

        # Create the venv so _ensure_venv picks it up
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
        )

        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            # Return a fake CompletedProcess
            return subprocess.CompletedProcess(args, 0)

        m = PackageManager()
        monkeypatch.setattr(m, "venv_dir", str(venv_dir))
        monkeypatch.setattr(subprocess, "run", fake_run)

        m._install_pack_dependencies(str(pack_dir))

        # Should have called pip install -r <req_path>
        assert len(calls) >= 1
        pip_args = calls[0][0]
        assert "install" in pip_args
        assert "-r" in pip_args
        assert str(req_path) in pip_args


class TestDependencyEndToEnd:
    """End-to-end: install a pack with requirements.txt and verify venv
    integration without real network access."""

    def test_no_requirements_does_nothing(self, tmp_path, monkeypatch):
        packs_dir = tmp_path / "packs"
        os.makedirs(packs_dir)
        venv_dir = tmp_path / "venv"

        # Create a minimal pack without requirements.txt
        pack_src = tmp_path / "src"
        os.makedirs(pack_src)
        (pack_src / "manifest.json").write_text(
            json.dumps({"id": "nopkg", "name": "NoPkg", "version": "1.0.0"})
        )
        (pack_src / "plugin.py").write_text(
            "from core.base_plugin import BaseRecitePlugin\n"
            "class Plugin(BaseRecitePlugin):\n"
            "    def load_data(self): pass\n"
            "    def get_all_problem_ids(self): return []\n"
            "    def render_statement(self, pid): return ''\n"
            "    def check_answer(self, pid, ui): return False\n"
            "    def get_expected_display(self, pid): return ''\n"
        )

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", str(packs_dir))
        monkeypatch.setattr(m, "venv_dir", str(venv_dir))

        m.install_pack(str(pack_src))
        # Venv should NOT have been created (no requirements.txt)
        assert not os.path.isdir(str(venv_dir))
