"""Tests for per-pack venv dependency management."""

import json
import os
import subprocess
import sys

import pytest

from src.cli.manager import PackageManager

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _make_pack_with_deps(path, pack_id, version="1.0.0", requirements=None):
    """Create a minimal pack with an optional requirements.txt."""
    os.makedirs(path, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "name": f"{pack_id} Name",
                "version": version,
                "description": "Test pack",
            }
        )
    )
    (path / "plugin.py").write_text(
        "from core.base_plugin import BaseRecitePlugin\n"
        "class Plugin(BaseRecitePlugin):\n"
        "    def load_data(self): pass\n"
        "    def get_all_problem_ids(self): return []\n"
        "    def render_statement(self, pid): return ''\n"
        "    def check_answer(self, pid, ui): return False\n"
        "    def get_expected_display(self, pid): return ''\n"
    )
    if requirements:
        (path / "requirements.txt").write_text(requirements)


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestEnsurePackVenv:
    # These two tests are the only ones that create *real* venvs,
    # because they're testing the venv creation logic itself.

    def test_creates_venv_for_pack(self, monkeypatch, tmp_path):
        venvs_base = tmp_path / "venvs"
        m = PackageManager()
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))

        python_exe = m._ensure_pack_venv("p1")

        assert os.path.isfile(python_exe)
        assert os.path.isdir(str(venvs_base / "p1"))

    def test_separate_venvs_for_different_packs(self, monkeypatch, tmp_path):
        venvs_base = tmp_path / "venvs"
        m = PackageManager()
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))

        py_a = m._ensure_pack_venv("pack_a")
        py_b = m._ensure_pack_venv("pack_b")

        assert os.path.isfile(py_a)
        assert os.path.isfile(py_b)
        assert py_a != py_b


class TestGetPackSitePackages:
    def test_returns_distinct_paths(self, monkeypatch, tmp_path):
        venvs_base = tmp_path / "venvs"
        m = PackageManager()
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))

        site_a = m._get_pack_site_packages("x")
        site_b = m._get_pack_site_packages("y")

        assert site_a != site_b
        assert "site-packages" in site_a
        assert "site-packages" in site_b


class TestInstallPackDependencies:
    def test_noop_when_no_requirements(self, monkeypatch, tmp_path):
        pack_dir = tmp_path / "pack"
        os.makedirs(pack_dir)
        m = PackageManager()
        monkeypatch.setattr(
            m, "_get_pack_venv_dir", lambda pid: str(tmp_path / "venvs" / pid)
        )
        m._install_pack_dependencies(str(pack_dir), "nopkg")

    def test_noop_when_empty_requirements(self, monkeypatch, tmp_path):
        pack_dir = tmp_path / "pack"
        os.makedirs(pack_dir)
        (pack_dir / "requirements.txt").write_text("")
        m = PackageManager()
        monkeypatch.setattr(
            m, "_get_pack_venv_dir", lambda pid: str(tmp_path / "venvs" / pid)
        )
        m._install_pack_dependencies(str(pack_dir), "emptypkg")

    def test_pip_called_in_correct_venv(self, monkeypatch, tmp_path):
        """pip install is invoked inside the pack's own venv.

        ``_ensure_pack_venv`` is mocked so this test does not pay the
        cost of a real ``python -m venv`` call.
        """
        venvs_base = tmp_path / "venvs"
        pack_dir = tmp_path / "p1"
        os.makedirs(pack_dir)
        (pack_dir / "requirements.txt").write_text("foo>=1.0\n")

        fake_python = str(venvs_base / "p1" / "bin" / os.path.basename(sys.executable))
        m = PackageManager()
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))
        monkeypatch.setattr(m, "_ensure_pack_venv", lambda pid: fake_python)

        calls = []
        real_run = subprocess.run

        def fake_run(args, **kwargs):
            if any("pip" in str(a) for a in args):
                calls.append((args, kwargs))
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        m._install_pack_dependencies(str(pack_dir), "p1")

        assert len(calls) == 1
        pip_args = calls[0][0]
        assert "install" in pip_args
        assert str(pack_dir / "requirements.txt") in pip_args


class TestConflictingVersions:
    def test_install_two_packs_with_conflicting_pins(self, monkeypatch, tmp_path):
        venvs_base = tmp_path / "venvs"
        packs_dir = tmp_path / "packs"
        os.makedirs(packs_dir)

        src_a = tmp_path / "src_a"
        _make_pack_with_deps(src_a, "pack_a", "1.0.0", "foo==1.0.0\n")
        src_b = tmp_path / "src_b"
        _make_pack_with_deps(src_b, "pack_b", "1.0.0", "foo==2.0.0\n")

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", str(packs_dir))
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))
        monkeypatch.setattr(
            m,
            "_ensure_pack_venv",
            lambda pid: str(
                venvs_base / pid / "bin" / os.path.basename(sys.executable)
            ),
        )

        pip_calls = []
        real_run = subprocess.run

        def fake_run(args, **kwargs):
            if any("pip" in str(a) for a in args):
                pip_calls.append((args, kwargs))
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        m.install_pack(str(src_a))
        m.install_pack(str(src_b))

        assert len(pip_calls) == 2
        pip0 = pip_calls[0][0]
        pip1 = pip_calls[1][0]
        assert pip0[0] != pip1[0]

        req_paths = {str(pip_calls[i][0][-1]) for i in range(2)}
        assert all(r.endswith("requirements.txt") for r in req_paths)

    def test_isolated_site_packages_after_install(self, monkeypatch, tmp_path):
        venvs_base = tmp_path / "venvs"
        packs_dir = tmp_path / "packs"
        os.makedirs(packs_dir)

        src_a = tmp_path / "src_a"
        _make_pack_with_deps(src_a, "iso_a", "1.0.0", "foo==1.0")
        src_b = tmp_path / "src_b"
        _make_pack_with_deps(src_b, "iso_b", "1.0.0", "foo==2.0")

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", str(packs_dir))
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))
        monkeypatch.setattr(m, "_install_pack_dependencies", lambda *a: None)

        m.install_pack(str(src_a))
        m.install_pack(str(src_b))

        site_a = m._get_pack_site_packages("iso_a")
        site_b = m._get_pack_site_packages("iso_b")
        assert site_a != site_b


class TestNoDepsDoesNotCreateVenv:
    def test_pack_without_requirements(self, monkeypatch, tmp_path):
        venvs_base = tmp_path / "venvs"
        packs_dir = tmp_path / "packs"
        os.makedirs(packs_dir)

        src = tmp_path / "src"
        _make_pack_with_deps(src, "nopkg", "1.0.0")

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", str(packs_dir))
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))

        m.install_pack(str(src))
        assert not os.path.isdir(str(venvs_base / "nopkg"))


class TestFailedDependencyPreservesPack:
    def test_existing_pack_survives_failed_install(self, monkeypatch, tmp_path):
        venvs_base = tmp_path / "venvs"
        packs_dir = tmp_path / "packs"
        os.makedirs(packs_dir)

        src_old = tmp_path / "src_old"
        _make_pack_with_deps(src_old, "survivor", "1.0.0")
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", str(packs_dir))
        monkeypatch.setattr(m, "_get_pack_venv_dir", lambda pid: str(venvs_base / pid))
        monkeypatch.setattr(
            m,
            "_ensure_pack_venv",
            lambda pid: str(
                venvs_base / pid / "bin" / os.path.basename(sys.executable)
            ),
        )
        m.install_pack(str(src_old))
        old_manifest = json.loads(
            (packs_dir / "survivor" / "manifest.json").read_text()
        )
        assert old_manifest["version"] == "1.0.0"

        src_bad = tmp_path / "src_bad"
        _make_pack_with_deps(src_bad, "survivor", "2.0.0", "nonexistent_pkg==999\n")

        real_run = subprocess.run

        def fake_run(args, **kwargs):
            if any("pip" in str(a) for a in args):
                raise subprocess.CalledProcessError(
                    1, args, stderr="No matching distribution"
                )
            return real_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(RuntimeError, match="Failed to install dependencies"):
            m.install_pack(str(src_bad))

        surviving = json.loads((packs_dir / "survivor" / "manifest.json").read_text())
        assert surviving["version"] == "1.0.0"
