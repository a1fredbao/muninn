"""Tests for isolated per-pack dependency environments."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from muninn.services.dependency import DependencyEnvironment
from muninn.services.manifest import PackManifest
from muninn.services.package_manager import PackageManager
from muninn.services.plugin_loader import PluginLoader


def _write_manifest(path: Path, pack_id: str, version: str = "1.0.0") -> None:
    path.mkdir(parents=True, exist_ok=True)
    manifest = PackManifest(
        id=pack_id,
        name=pack_id,
        version=version,
        entrypoint="plugin:Plugin",
        api_version="1",
    )
    (path / "manifest.json").write_text(
        __import__("json").dumps(manifest.to_dict()),
        encoding="utf-8",
    )
    (path / "plugin.py").write_text(
        "class Plugin:\n    pass\n",
        encoding="utf-8",
    )


class TestDependencyEnvironment:
    def test_noop_without_requirements(self, tmp_path):
        environment = DependencyEnvironment(str(tmp_path / "venvs"))
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()

        assert environment.prepare(str(pack_dir), "pack", "1.0.0") is None

    def test_noop_with_empty_requirements(self, tmp_path):
        environment = DependencyEnvironment(str(tmp_path / "venvs"))
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "requirements.txt").write_text("", encoding="utf-8")

        assert environment.prepare(str(pack_dir), "pack", "1.0.0") is None

    def test_versioned_environments_have_distinct_paths(self, tmp_path):
        environment = DependencyEnvironment(str(tmp_path / "venvs"))
        assert environment.get_pack_venv_dir("pack", "1.0.0") != (
            environment.get_pack_venv_dir("pack", "2.0.0")
        )
        assert environment.get_site_packages("a", "1.0.0") != (
            environment.get_site_packages("b", "1.0.0")
        )

    def test_prepare_installs_requirements_in_staging_environment(
        self,
        tmp_path,
        monkeypatch,
    ):
        environment = DependencyEnvironment(str(tmp_path / "venvs"))
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "requirements.txt").write_text(
            "demo-package==1.0\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(environment, "_run_subprocess", fake_run)

        staged = environment.prepare(str(pack_dir), "pack", "1.0.0")

        assert staged is not None
        assert len(calls) == 2
        assert calls[1][1:4] == ["install", "--quiet", "-r"]
        assert calls[1][-1] == str(pack_dir / "requirements.txt")

    def test_failed_dependency_preparation_preserves_existing_pack(
        self,
        tmp_path,
        monkeypatch,
    ):
        packs_dir = tmp_path / "packs"
        source = tmp_path / "source"
        _write_manifest(source, "pack")
        manager = PackageManager(
            packs_dir=str(packs_dir),
            venvs_dir=str(tmp_path / "venvs"),
        )
        manager.install_pack(str(source))

        manifest = PackManifest.from_path(packs_dir / "pack" / "manifest.json")
        assert manifest.version == "1.0.0"

        def fail_prepare(*args, **kwargs):
            raise RuntimeError("dependency failure")

        monkeypatch.setattr(manager.dependencies, "prepare", fail_prepare)
        _write_manifest(source, "pack", "2.0.0")

        with pytest.raises(RuntimeError, match="dependency failure"):
            manager.install_pack(str(source))

        installed = PackManifest.from_path(packs_dir / "pack" / "manifest.json")
        assert installed.version == "1.0.0"


class TestPluginEnvironment:
    def test_loader_prepends_versioned_site_packages(self, tmp_path):
        packs_dir = tmp_path / "packs"
        venvs_dir = tmp_path / "venvs"
        _write_manifest(packs_dir / "pack", "pack", "1.2.3")
        environment = DependencyEnvironment(str(venvs_dir))
        site_packages = environment.get_site_packages("pack", "1.2.3")
        os.makedirs(site_packages)

        loader = PluginLoader(
            str(packs_dir),
            dependency_environment=environment,
        )
        loaded = loader.load("pack")

        assert site_packages in loaded.environment["PYTHONPATH"].split(os.pathsep)
