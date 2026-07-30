"""Tests for src/cli/manager.py."""

import json
import os

import pytest

from src.cli.manager import PackageManager

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _make_minimal_pack(path, pack_id="test-pack"):
    """Write a minimal valid pack (manifest.json + plugin.py) into *path*."""
    os.makedirs(path, exist_ok=True)
    manifest = {
        "id": pack_id,
        "name": f"{pack_id} Name",
        "author": "Tester",
        "version": "1.0.0",
        "description": "Test pack",
    }
    with open(os.path.join(path, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)

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


class TestInstallPack:
    def test_install_local_directory(self, tmp_workspace, monkeypatch):
        src = os.path.join(tmp_workspace, "mypack")
        _make_minimal_pack(src, pack_id="mypack")

        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        pack_id = m.install_pack(src)
        assert pack_id == "mypack"
        assert os.path.isdir(os.path.join(packs_dir, "mypack"))

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


class TestRemoteDetection:
    def test_is_url(self):
        assert PackageManager._is_url("https://github.com/a/b")
        assert not PackageManager._is_url("http://example.com/pkg.zip")
        assert not PackageManager._is_url("./local-pack")
        assert not PackageManager._is_url("user/repo")

    def test_is_github_short(self):
        assert PackageManager._is_github_short("user/repo")
        assert PackageManager._is_github_short("a-b/c_d")
        assert PackageManager._is_github_short("a.b/c")
        assert PackageManager._is_github_short("user/repo@v1.0.0")
        assert not PackageManager._is_github_short("./local")

    def test_github_short_to_url(self):
        assert (
            PackageManager._github_short_to_url("user/repo")
            == "https://github.com/user/repo/archive/refs/heads/main.zip"
        )
        assert (
            PackageManager._github_short_to_url("user/repo@v2.0")
            == "https://github.com/user/repo/archive/refs/heads/v2.0.zip"
        )

    def test_resolve_download_url(self):
        url = PackageManager._resolve_download_url("https://github.com/user/repo")
        assert url == "https://github.com/user/repo/archive/refs/heads/main.zip"

        url = PackageManager._resolve_download_url(
            "https://github.com/user/repo@v1.0.0"
        )
        assert url == "https://github.com/user/repo/archive/refs/heads/v1.0.0.zip"

        # Direct file URL passes through unchanged
        direct = "https://example.com/pack.zip"
        assert PackageManager._resolve_download_url(direct) == direct

    def test_dispatch_local_dir(self, tmp_workspace, monkeypatch):
        src = os.path.join(tmp_workspace, "mypack")
        _make_minimal_pack(src, "mypack")
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)
        # Local path – should hit _install_local (no network)
        pid = m.install_pack(src)
        assert pid == "mypack"


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


class TestWrappedArchiveInstall:
    """Regression test for wrapped GitHub-style archives.

    GitHub archives wrap contents in a top-level directory (e.g., repo-branch/).
    This tests that _install_remote correctly handles such archives by ensuring
    the staging directory is clean (no leftover zip file) so _finalise_install's
    wrapper-directory normalization logic can detect and unwrap the single directory.
    """

    def test_install_wrapped_zip_archive(self, tmp_workspace, monkeypatch):
        """Test installing a zip archive with contents wrapped in a single directory.

        This test exercises _install_remote (not _install_local) by mocking
        urllib.request.urlopen to simulate downloading a GitHub-style wrapped archive.
        """
        import io
        import zipfile
        from unittest.mock import MagicMock

        # Create a pack inside a wrapper directory (simulating GitHub archive structure)
        wrapper_name = "test-pack-main"
        pack_content_dir = os.path.join(tmp_workspace, wrapper_name)
        _make_minimal_pack(pack_content_dir, pack_id="test-pack")

        # Create a zip file with the wrapped structure
        zip_path = os.path.join(tmp_workspace, "wrapped.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, dirs, files in os.walk(pack_content_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, tmp_workspace)
                    zf.write(file_path, arcname)

        # Read the zip file bytes for mocking
        with open(zip_path, "rb") as f:
            zip_bytes = f.read()

        # Mock urllib.request.urlopen to return the wrapped zip bytes
        def mock_urlopen(url, timeout=None):
            """Mock urlopen that returns a context manager yielding BytesIO."""
            mock_response = MagicMock()
            mock_response.__enter__ = lambda self: io.BytesIO(zip_bytes)
            mock_response.__exit__ = lambda self, *args: None
            return mock_response

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        # Set up packs directory
        packs_dir = os.path.join(tmp_workspace, "fake_muninn", "packs")
        os.makedirs(packs_dir, exist_ok=True)

        m = PackageManager()
        monkeypatch.setattr(m, "packs_dir", packs_dir)

        # Install via URL (this exercises _install_remote, not _install_local)
        pack_id = m.install_pack("https://github.com/someuser/test-pack")
        assert pack_id == "test-pack"

        # Verify manifest.json is at the root of the installed pack (not nested)
        installed_manifest = os.path.join(packs_dir, "test-pack", "manifest.json")
        assert os.path.exists(installed_manifest)

        # Verify the wrapper directory was stripped
        wrapper_path = os.path.join(packs_dir, "test-pack", wrapper_name)
        assert not os.path.exists(wrapper_path)
