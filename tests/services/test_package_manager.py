"""Tests for the package-management facade and its subsystems."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from muninn.services.manifest import PackManifest
from muninn.services.pack_installer import PackSourceResolver
from muninn.services.package_manager import PackageManager


def _write_pack(
    path: Path,
    pack_id: str = "test-pack",
    version: str = "1.0.0",
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    manifest = PackManifest(
        id=pack_id,
        name=f"{pack_id} Name",
        author="Tester",
        version=version,
        description="Test pack",
        entrypoint="plugin:Plugin",
        api_version="1",
    )
    (path / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=4),
        encoding="utf-8",
    )
    (path / "plugin.py").write_text(
        """from muninn.plugin_api import BaseTrainingPlugin


class Plugin(BaseTrainingPlugin):
    def load_data(self):
        self.ids = ["1", "2"]

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        print("plugin debug")
        return f"Q{problem_id}"

    def check_answer(self, problem_id, user_input):
        return user_input.strip() == problem_id

    def get_expected_display(self, problem_id):
        return f"A{problem_id}"
""",
        encoding="utf-8",
    )


@pytest.fixture
def manager(tmp_path):
    return PackageManager(
        packs_dir=str(tmp_path / "packs"),
        venvs_dir=str(tmp_path / "venvs"),
    )


class TestCreateTemplate:
    def test_creates_expected_files_and_contract(self, tmp_path):
        manager = PackageManager(
            packs_dir=str(tmp_path / "packs"),
            venvs_dir=str(tmp_path / "venvs"),
        )
        pack_dir = Path(manager.create_template("my-pack", str(tmp_path)))

        manifest = json.loads((pack_dir / "manifest.json").read_text())
        plugin_code = (pack_dir / "plugin.py").read_text()

        assert manifest["entrypoint"] == "plugin:Plugin"
        assert manifest["api_version"] == "1"
        assert "muninn.core.helpers" in plugin_code

    def test_raises_if_exists(self, manager, tmp_path):
        manager.create_template("dup", str(tmp_path))
        with pytest.raises(FileExistsError):
            manager.create_template("dup", str(tmp_path))


class TestInstallAndUninstall:
    def test_records_local_source_and_overwrites(self, manager, tmp_path):
        source = tmp_path / "source"
        _write_pack(source, "mypack")

        assert manager.install_pack(str(source)) == "mypack"
        manifest = json.loads(
            (Path(manager.packs_dir) / "mypack" / "manifest.json").read_text()
        )
        assert manifest["source"] == f"local:{source.resolve()}"

        assert manager.install_pack(str(source)) == "mypack"

    def test_raises_for_nonexistent_path(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.install_pack("/nonexistent/path/to/pack")

    def test_uninstall_removes_pack_and_environment(self, manager, tmp_path):
        source = tmp_path / "source"
        _write_pack(source, "mypack")
        manager.install_pack(str(source))

        versioned_env = Path(manager.dependencies.venvs_dir) / "mypack" / "1.0.0"
        versioned_env.mkdir(parents=True)

        manager.uninstall_pack("mypack")

        assert not (Path(manager.packs_dir) / "mypack").exists()
        assert not (Path(manager.dependencies.venvs_dir) / "mypack").exists()

    def test_uninstall_missing_pack_raises(self, manager):
        with pytest.raises(FileNotFoundError, match="not installed"):
            manager.uninstall_pack("nonexistent")

    def test_commit_rolls_back_when_pack_switch_fails(
        self,
        manager,
        tmp_path,
        monkeypatch,
    ):
        old_source = tmp_path / "old"
        _write_pack(old_source, "transaction", "1.0.0")
        manager.install_pack(str(old_source))

        new_source = tmp_path / "new"
        _write_pack(new_source, "transaction", "2.0.0")
        resolved = manager.installer.sources.resolve(str(new_source))
        staged = manager.installer.stage(resolved)
        real_replace = os.replace
        replace_count = 0

        def flaky_replace(source, destination):
            nonlocal replace_count
            replace_count += 1
            if replace_count == 2:
                raise OSError("simulated commit failure")
            return real_replace(source, destination)

        monkeypatch.setattr(os, "replace", flaky_replace)
        try:
            with pytest.raises(OSError, match="simulated commit failure"):
                staged.commit()
        finally:
            staged.cleanup()

        installed = PackManifest.from_path(
            Path(manager.packs_dir) / "transaction" / "manifest.json"
        )
        assert installed.version == "1.0.0"


class TestSourceResolution:
    def test_resolves_github_and_local_sources(self, tmp_path):
        resolver = PackSourceResolver()

        remote = resolver.resolve("user/repo@dev")
        assert remote.kind == "remote-zip"
        assert remote.location.endswith("/dev.zip")
        assert remote.source_info == "github:user/repo@dev"

        local = tmp_path / "pack"
        _write_pack(local)
        resolved_local = resolver.resolve(str(local))
        assert resolved_local.kind == "local-directory"
        assert resolved_local.source_info == f"local:{local.resolve()}"


class TestUpgrade:
    def test_upgrade_local_newer_version(self, manager, tmp_path):
        source = tmp_path / "source"
        _write_pack(source, "p1", "1.0.0")
        manager.install_pack(str(source))

        _write_pack(source, "p1", "2.0.0")
        assert manager.upgrade_pack("p1") is True

        manifest = json.loads(
            (Path(manager.packs_dir) / "p1" / "manifest.json").read_text()
        )
        assert manifest["version"] == "2.0.0"

    def test_upgrade_missing_source_returns_failure(self, manager, tmp_path):
        source = tmp_path / "source"
        _write_pack(source, "p2", "1.0.0")
        manager.install_pack(str(source))
        source.rename(tmp_path / "moved")

        result = manager.upgrade_pack_result("p2")
        assert result.status == "failed"

    def test_upgrade_no_source_is_skipped(self, manager):
        pack_dir = Path(manager.packs_dir) / "nosource" / "manifest.json"
        pack_dir.parent.mkdir(parents=True)
        pack_dir.write_text(
            json.dumps(
                {
                    "id": "nosource",
                    "name": "No Source",
                    "version": "1.0.0",
                }
            )
        )

        result = manager.upgrade_pack_result("nosource")
        assert result.status == "skipped"

    def test_nonexistent_pack_raises(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.upgrade_pack("ghost")


class TestListingAndLoading:
    def test_lists_installed_packs_and_keeps_invalid_entries(
        self,
        manager,
    ):
        source = Path(manager.packs_dir) / "source"
        _write_pack(source, "valid")
        manager.install_pack(str(source))

        invalid = Path(manager.packs_dir) / "invalid"
        invalid.mkdir()
        (invalid / "manifest.json").write_text("{")

        summaries = manager.list_pack_summaries()
        assert {summary.pack_id for summary in summaries} == {"valid", "invalid"}
        assert next(s for s in summaries if s.pack_id == "invalid").error

    def test_load_plugin_returns_worker_configuration(self, manager, tmp_path):
        source = tmp_path / "mypack"
        _write_pack(source, "mypack")
        manager.install_pack(str(source))

        loaded = manager.load_plugin("mypack")
        assert loaded.pack_id == "mypack"
        assert loaded.entrypoint == "plugin:Plugin"

    def test_plugin_adapter_runs_in_isolated_worker(self, manager, tmp_path):
        source = tmp_path / "mypack"
        _write_pack(source, "mypack")
        manager.install_pack(str(source))
        loaded = manager.load_plugin("mypack")

        async def exercise():
            adapter = await manager.create_plugin_adapter(loaded)
            try:
                assert await adapter.get_all_problem_ids() == ["1", "2"]
                assert await adapter.render_statement("1") == "Q1"
                assert await adapter.check_answer("1", "1")
            finally:
                await adapter.aclose()

        asyncio.run(exercise())

    def test_plugin_workers_isolate_same_named_local_modules(
        self,
        manager,
        tmp_path,
    ):
        for pack_id, value in (("pack-a", "A"), ("pack-b", "B")):
            source = tmp_path / pack_id
            _write_pack(source, pack_id)
            (source / "shared_dep.py").write_text(
                f"VALUE = {value!r}\n",
                encoding="utf-8",
            )
            (source / "plugin.py").write_text(
                """from muninn.plugin_api import BaseTrainingPlugin


class Plugin(BaseTrainingPlugin):
    def load_data(self):
        self.ids = ["1"]

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        import shared_dep
        return shared_dep.VALUE

    def check_answer(self, problem_id, user_input):
        return True

    def get_expected_display(self, problem_id):
        return "A"
""",
                encoding="utf-8",
            )
            manager.install_pack(str(source))

        async def exercise():
            adapters = []
            try:
                for pack_id in ("pack-a", "pack-b"):
                    loaded = manager.load_plugin(pack_id)
                    adapters.append(await manager.create_plugin_adapter(loaded))
                values = [await adapter.render_statement("1") for adapter in adapters]
                assert values == ["A", "B"]
            finally:
                for adapter in adapters:
                    await adapter.aclose()

        asyncio.run(exercise())


class TestVersionAndValidation:
    def test_version_comparison_is_semver_aware(self):
        assert PackageManager._is_newer("1.0.0", "1.0.0-beta")
        assert PackageManager._is_newer("2.0.0", "1.9.9")
        assert not PackageManager._is_newer("1.0.0", "1.0.0")

    @pytest.mark.parametrize(
        "pack_id",
        ["my-pack", "my_pack", "my.pack", "MyPack123", "pack-1.0.0"],
    )
    def test_valid_pack_ids(self, manager, pack_id):
        manager._validate_pack_id(pack_id)

    @pytest.mark.parametrize(
        "pack_id",
        ["", ".", "..", "../bad", "path/to", "path\\to", "bad name", "bad$id"],
    )
    def test_invalid_pack_ids(self, manager, pack_id):
        with pytest.raises(ValueError):
            manager._validate_pack_id(pack_id)

    def test_install_rejects_invalid_manifest(self, manager, tmp_path):
        source = tmp_path / "bad"
        source.mkdir()
        (source / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "../escape",
                    "name": "Bad",
                    "version": "1.0.0",
                }
            )
        )
        with pytest.raises(ValueError, match="Invalid manifest"):
            manager.install_pack(str(source))
