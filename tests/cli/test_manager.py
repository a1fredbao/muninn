"""Tests for src/cli/manager.py."""

import json
import os
import shutil

import pytest

from src.cli.manager import PackageManager

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _make_minimal_pack(path, pack_id="test-pack", version="1.0.0"):
    """Write a minimal valid pack (manifest.json + plugin.py) into *path*."""
    os.makedirs(path, exist_ok=True)
    manifest = {
        "id": pack_id,
        "name": f"{pack_id} Name",
        "author": "Tester",
        "version": version,
        "description": "Test pack",
    }
    with open(os.path.join(path, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)

    plugin_code = """from core.base_plugin import BaseRecitePlugin

class Plugin(BaseRecitePlugin):
    def load_data(self):
        self.ids = ["1", "2"]

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        return f"Q{problem_id}"

    def check_answer(self, problem_id, user_input):
        return user_input.strip() == problem_id

    def get_expected_display(self, problem_id):
        return f"A{problem_id}"
"""
    with open(os.path.join(path, "plugin.py"), "w", encoding="utf-8") as f:
        f.write(plugin_code)


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestCreateTemplate:
    def test_creates_expected_files(self, tmp_workspace):
        m = PackageManager()
        m.create_template("my-pack", tmp_workspace)
        pack_dir = os.path.join(tmp_workspace, "my-pack")
        assert os.path.isdir(pack_dir)
        assert os.path.isfile(os.path.join(pack_dir, "manifest.json"))
        assert os.path.isfile(os.path.join(pack_dir, "plugin.py"))

    def test_correct_manifest_content(self, tmp_workspace):
        m = PackageManager()
        m.create_template("my-pack", tmp_workspace)
        with open(os.path.join(tmp_workspace, "my-pack", "manifest.json")) as f:
            manifest = json.load(f)
        assert manifest["id"] == "my-pack"

    def test_raises_if_exists(self, tmp_workspace):
        m = PackageManager()
        m.create_template("dup", tmp_workspace)
        with pytest.raises(FileExistsError):
            m.create_template("dup", tmp_workspace)


class TestInstallLocal:
    def test_records_local_source(self, tmp_workspace, monkeypatch):
        src = os.path.join(tmp_workspace, "mypack")
        _make_minimal_pack(src, pack_id="mypack")
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        m.install_pack(src)

        # Verify source was recorded in the installed manifest
        installed = os.path.join(packs_dir, "mypack", "manifest.json")
        with open(installed) as f:
            manifest = json.load(f)
        assert manifest["source"] == f"local:{os.path.abspath(src)}"

    def test_install_overwrites_existing(self, tmp_workspace, monkeypatch):
        src = os.path.join(tmp_workspace, "mypack")
        _make_minimal_pack(src, pack_id="mypack")
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        m.install_pack(src)
        pack_id = m.install_pack(src)
        assert pack_id == "mypack"

    def test_raises_for_nonexistent_local_path(self):
        m = PackageManager()
        with pytest.raises(FileNotFoundError):
            m.install_pack("/nonexistent/path/to/pack")


class TestSourceDetection:
    def test_is_url(self):
        assert PackageManager._is_url("https://github.com/a/b")
        assert not PackageManager._is_url("./local-pack")
        assert not PackageManager._is_url("user/repo")

    def test_is_github_short(self):
        assert PackageManager._is_github_short("user/repo")
        assert PackageManager._is_github_short("a-b/c_d")
        assert PackageManager._is_github_short("user/repo@v1.0.0")
        assert not PackageManager._is_github_short("./local")

    def test_github_short_to_url(self):
        assert (
            PackageManager._github_short_to_url("user/repo")
            == "https://github.com/user/repo/archive/refs/heads/main.zip"
        )

    def test_resolve_download_url(self):
        url = PackageManager._resolve_download_url("https://github.com/user/repo")
        assert url == "https://github.com/user/repo/archive/refs/heads/main.zip"

        direct = "https://example.com/pack.zip"
        assert PackageManager._resolve_download_url(direct) == direct

    def test_github_source_key(self):
        assert (
            PackageManager._github_source_key("https://github.com/u/r") == "github:u/r"
        )
        assert (
            PackageManager._github_source_key("https://github.com/u/r@v1")
            == "github:u/r@v1"
        )


class TestUninstallPack:
    def test_uninstall_removes_directory(self, tmp_workspace, monkeypatch):
        src = os.path.join(tmp_workspace, "mypack")
        _make_minimal_pack(src, pack_id="mypack")
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)
        m.install_pack(src)
        assert os.path.isdir(os.path.join(packs_dir, "mypack"))
        m.uninstall_pack("mypack")
        assert not os.path.exists(os.path.join(packs_dir, "mypack"))

    def test_uninstall_nonexistent_pack_raises(self, monkeypatch, tmp_workspace):
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)
        with pytest.raises(FileNotFoundError, match="not installed"):
            m.uninstall_pack("nonexistent")


class TestUpgrade:
    def test_upgrade_no_source_skips(self, monkeypatch, tmp_workspace):
        """Pack without source field → skip."""
        packs_dir = os.path.join(tmp_workspace, "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        # Manually craft an installed pack without a source field
        pack_dir = os.path.join(packs_dir, "noid")
        _make_minimal_pack(pack_dir, "noid", "1.0.0")
        # Remove source key
        with open(os.path.join(pack_dir, "manifest.json"), "r+") as f:
            manifest = json.load(f)
            manifest.pop("source", None)
            f.seek(0)
            json.dump(manifest, f, indent=4)
            f.truncate()

        result = m.upgrade_pack("noid")
        assert result is False

    def test_upgrade_local_newer_version(self, monkeypatch, tmp_workspace):
        """Local source with a newer version → upgrade performed."""
        source_dir = os.path.join(tmp_workspace, "source")
        _make_minimal_pack(source_dir, "p1", "1.0.0")

        packs_dir = os.path.join(tmp_workspace, "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        # Install v1.0.0 from the source dir
        m.install_pack(source_dir)

        # Bump the source dir to v2.0.0
        with open(os.path.join(source_dir, "manifest.json"), "w") as f:
            manifest = {
                "id": "p1",
                "name": "p1 Name",
                "author": "Tester",
                "version": "2.0.0",
                "description": "Test pack",
            }
            json.dump(manifest, f, indent=4)

        # Read the installed manifest, bump source to v2.0.0
        source_path = os.path.join(packs_dir, "p1", "manifest.json")
        with open(source_path) as f:
            installed = json.load(f)
        assert installed["source"] == f"local:{os.path.abspath(source_dir)}"

        # Now the source dir has v2.0.0 → upgrade should trigger
        assert m.upgrade_pack("p1") is True

        # Verify installed version is now 2.0.0
        with open(source_path) as f:
            upgraded = json.load(f)
        assert upgraded["version"] == "2.0.0"

    def test_upgrade_local_missing_path(self, monkeypatch, tmp_workspace):
        """Local source path no longer exists → skipped gracefully."""
        source_dir = os.path.join(tmp_workspace, "srcdir")
        _make_minimal_pack(source_dir, "p2", "1.0.0")

        packs_dir = os.path.join(tmp_workspace, "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        m.install_pack(source_dir)

        # Now delete the source directory
        shutil.rmtree(source_dir)

        result = m.upgrade_pack("p2")
        assert result is False

    def test_upgrade_already_current(self, monkeypatch, tmp_workspace):
        """Same version → no upgrade."""
        source_dir = os.path.join(tmp_workspace, "srcdir")
        _make_minimal_pack(source_dir, "p3", "1.0.0")

        packs_dir = os.path.join(tmp_workspace, "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        m.install_pack(source_dir)
        assert m.upgrade_pack("p3") is False

    def test_upgrade_nonexistent_pack(self, tmp_workspace, monkeypatch):
        packs_dir = os.path.join(tmp_workspace, "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)
        with pytest.raises(FileNotFoundError):
            m.upgrade_pack("ghost")


class TestLoadPlugin:
    def test_loads_valid_plugin(self, tmp_workspace, monkeypatch):
        src = os.path.join(tmp_workspace, "mypack")
        _make_minimal_pack(src, pack_id="mypack")
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)
        m.install_pack(src)

        plugin = m.load_plugin("mypack")
        assert plugin.get_all_problem_ids() == ["1", "2"]
        assert plugin.render_statement("1") == "Q1"
        assert plugin.check_answer("1", "1")
        assert not plugin.check_answer("1", "wrong")

    def test_raises_for_nonexistent_pack(self):
        m = PackageManager()
        with pytest.raises(FileNotFoundError):
            m.load_plugin("nonexistent-pack")


class TestListPacks:
    def test_lists_installed_packs(self, tmp_workspace, monkeypatch):
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        src1 = os.path.join(tmp_workspace, "pack_a")
        src2 = os.path.join(tmp_workspace, "pack_b")
        _make_minimal_pack(src1, pack_id="pack_a")
        _make_minimal_pack(src2, pack_id="pack_b")
        m.install_pack(src1)
        m.install_pack(src2)

        packs = m.list_packs()
        ids = {p["id"] for p in packs}
        assert ids == {"pack_a", "pack_b"}


class TestVersion:
    def test_version_tuple(self):
        assert PackageManager._version_tuple("1.2.3") == (1, 2, 3)

    def test_is_newer(self):
        assert PackageManager._is_newer("2.0.0", "1.0.0")
        assert not PackageManager._is_newer("1.0.0", "1.0.0")
        assert not PackageManager._is_newer("0.9.0", "1.0.0")
        assert PackageManager._is_newer("1.0.1", "1.0.0")
        assert PackageManager._is_newer("1.1.0", "1.0.9")

    def test_version_tuple_corner_cases(self):
        # Prefix handling
        assert PackageManager._version_tuple("v1.0.0") == (1, 0, 0)
        assert PackageManager._version_tuple("V2.1.3") == (2, 1, 3)
        # Suffix handling
        assert PackageManager._version_tuple("1.0.0-beta") == (1, 0, 0)
        assert PackageManager._version_tuple("1.2.3.alpha4") == (1, 2, 3)
        # Short versions
        assert PackageManager._version_tuple("1.0") == (1, 0, 0)
        assert PackageManager._version_tuple("2") == (2, 0, 0)
        # Invalid / unexpected formats gracefully falling back
        assert PackageManager._version_tuple("v.1.0") == (0, 0, 0)
        assert PackageManager._version_tuple("version-1.0") == (0, 0, 0)
        assert PackageManager._version_tuple("1.b.c") == (1, 0, 0)


class TestLoadPluginCornerCases:
    def test_raises_if_no_valid_subclass(self, tmp_workspace, monkeypatch):
        src = os.path.join(tmp_workspace, "badpack")
        os.makedirs(src, exist_ok=True)
        manifest = {"id": "badpack", "version": "1.0.0"}
        with open(os.path.join(src, "manifest.json"), "w") as f:
            json.dump(manifest, f)

        # Plugin that doesn't subclass BaseRecitePlugin
        with open(os.path.join(src, "plugin.py"), "w") as f:
            f.write("class Plugin:\n    pass\n")

        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)
        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)
        m.install_pack(src)

        with pytest.raises(
            ValueError, match="No valid BaseRecitePlugin subclass found"
        ):
            m.load_plugin("badpack")
