import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile

from ..core.base_plugin import BaseRecitePlugin


class PackageManager:
    def __init__(self):
        self.packs_dir = os.path.expanduser("~/.muninn/packs")
        os.makedirs(self.packs_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install_pack(self, source: str) -> str:
        """Install a pack from a local directory, a zip file, or a GitHub URL.

        Source formats::

            ./my-pack              # local directory (relative)
            /abs/path/to/pack      # local directory (absolute)
            ./my-pack.zip          # local zip file
            user/repo              # GitHub shorthand (default branch: main)
            user/repo@v1.0.0       # GitHub shorthand with tag/branch
            https://github.com/user/repo
        """
        if self._is_url(source):
            return self._install_remote(self._resolve_download_url(source))

        if self._is_github_short(source):
            return self._install_remote(self._github_short_to_url(source))

        return self._install_local(source)

    def uninstall_pack(self, pack_id: str):
        """Remove a pack from the local packs directory."""
        pack_dir = self._get_pack_dir(pack_id)
        if not os.path.exists(pack_dir):
            raise FileNotFoundError(f"Pack '{pack_id}' is not installed.")
        shutil.rmtree(pack_dir)
        print(f"🗑️  Pack '{pack_id}' has been uninstalled.")

    def load_plugin(self, pack_id: str) -> BaseRecitePlugin:
        """Dynamically load the plugin.py from the pack_id directory."""
        pack_dir = self._get_pack_dir(pack_id)
        if not os.path.exists(pack_dir):
            raise FileNotFoundError(f"Pack '{pack_id}' not found.")

        plugin_path = os.path.join(pack_dir, "plugin.py")
        if not os.path.exists(plugin_path):
            raise FileNotFoundError(f"plugin.py not found in {pack_id}.")

        src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        sys.path.insert(0, src_dir)

        try:
            spec = importlib.util.spec_from_file_location(
                f"muninn.plugins.{pack_id}", plugin_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and attr.__module__ == module.__name__
                    and any(b.__name__ == "BaseRecitePlugin" for b in attr.__mro__)
                    and attr.__name__ != "BaseRecitePlugin"
                ):
                    return attr(workspace_dir=pack_dir)

            raise ValueError(
                f"No valid BaseRecitePlugin subclass found in {plugin_path}"
            )
        finally:
            sys.path.pop(0)

    def list_packs(self):
        packs = []
        for pack_id in os.listdir(self.packs_dir):
            pack_dir = self._get_pack_dir(pack_id)
            if not os.path.isdir(pack_dir):
                continue
            manifest_path = os.path.join(pack_dir, "manifest.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
                    packs.append(manifest)
        return packs

    def create_template(self, pack_id: str, target_dir: str = "."):
        """Generate a new plugin template."""
        pack_dir = os.path.join(target_dir, pack_id)
        if os.path.exists(pack_dir):
            raise FileExistsError(f"Directory {pack_dir} already exists.")

        os.makedirs(pack_dir)

        manifest = {
            "id": pack_id,
            "name": f"{pack_id} Pack",
            "author": "Your Name",
            "version": "1.0.0",
            "description": "A new reciting pack for Muninn.",
        }
        with open(os.path.join(pack_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4, ensure_ascii=False)

        plugin_code = '''"""A minimal Muninn plugin using DataPlugin.

For flashcard-style packs (front/back), use FlashcardPlugin instead.
For full control, use the BaseRecitePlugin interface directly.
"""
from typing import ClassVar

from core.helpers import (
    DataPlugin,
    Matchers,
    QuestionType,
)


class Plugin(DataPlugin):
    QUESTION_TYPES: ClassVar[list[QuestionType]] = [
        # TODO: Define your question types here.
        # Each QuestionType needs a label, statement, answer, and matcher.
        # See the documentation for examples.
    ]
'''
        with open(os.path.join(pack_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write(plugin_code)

        print(f"✅ Template created at {pack_dir}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_pack_dir(self, pack_id: str) -> str:
        return os.path.join(self.packs_dir, pack_id)

    # -- source detection -------------------------------------------------

    @staticmethod
    def _is_url(source: str) -> bool:
        return source.startswith(("http://", "https://"))

    @staticmethod
    def _is_github_short(source: str) -> bool:
        """Detect ``owner/name`` or ``owner/name@ref`` patterns."""
        return bool(
            re.fullmatch(
                r"[a-zA-Z0-9](?:[\w.\-]*[a-zA-Z0-9])?/[a-zA-Z0-9](?:[\w.\-]*[a-zA-Z0-9])?(?:@[\w.\-/]+)?",
                source,
            )
        )

    # -- GitHub URL resolution --------------------------------------------

    @staticmethod
    def _github_short_to_url(source: str) -> str:
        """Convert ``owner/name[@ref]`` to a GitHub archive download URL."""
        if "@" in source:
            owner_repo, ref = source.split("@", 1)
        else:
            owner_repo, ref = source, "main"
        return f"https://github.com/{owner_repo}/archive/refs/heads/{ref}.zip"

    @staticmethod
    def _resolve_download_url(url: str) -> str:
        """Normalise a GitHub repository URL into an archive download URL.

        Handles:
        - ``https://github.com/user/repo``         → archive zip (main)
        - ``https://github.com/user/repo.git``     → archive zip (main)
        - ``https://github.com/user/repo@v1.0.0``  → archive zip (tag v1.0.0)
        - Direct file URLs                          → passed through as-is
        """
        match = re.match(
            r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?(?:@([\w.\-/]+))?/?$",
            url.rstrip("/"),
        )
        if match:
            owner, repo, ref = match.group(1), match.group(2), match.group(3)
            ref = ref or "main"
            return f"https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip"
        return url  # pass through: direct download URL, release asset, etc.

    # -- install backends --------------------------------------------------

    def _install_local(self, source: str) -> str:
        """Install from a local directory or zip file (existing logic)."""
        if not os.path.exists(source):
            raise FileNotFoundError(f"Path not found: {source}")

        if os.path.isdir(source):
            temp_dir = tempfile.mkdtemp(dir=self.packs_dir, prefix=".temp_")
            shutil.copytree(source, temp_dir, dirs_exist_ok=True)
            pack_id = self._finalise_install(temp_dir)
        elif zipfile.is_zipfile(source):
            temp_dir = tempfile.mkdtemp(dir=self.packs_dir, prefix=".temp_")
            with zipfile.ZipFile(source) as zf:
                zf.extractall(temp_dir)
            pack_id = self._finalise_install(temp_dir)
        else:
            raise ValueError(
                "Unsupported file format. Must be a directory or zip file."
            )

        print(f"✅ Successfully installed pack '{pack_id}'")
        return pack_id

    def _install_remote(self, url: str) -> str:
        """Download a remote zip and install it."""
        print(f"⬇️  Downloading {url} ...")
        temp_dir = tempfile.mkdtemp(dir=self.packs_dir, prefix=".temp_")
        zip_path = os.path.join(temp_dir, "pack.zip")

        try:
            with urllib.request.urlopen(url) as resp, open(zip_path, "wb") as f:
                shutil.copyfileobj(resp, f)
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to download from {url}: {exc}") from exc

        if not zipfile.is_zipfile(zip_path):
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError(
                "Downloaded file is not a valid zip. "
                "Make sure the URL points to a GitHub repository, not a web page."
            )

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(temp_dir)

        pack_id = self._finalise_install(temp_dir)
        print(f"✅ Successfully installed pack '{pack_id}'")
        return pack_id

    def _finalise_install(self, temp_dir: str) -> str:
        """Validate manifest and move *temp_dir* into place.  Returns pack_id."""
        # GitHub zip wraps everything in a top-level directory.
        # If the extracted temp_dir contains exactly one subdirectory and
        # no manifest at the root, peek inside it.
        entries = os.listdir(temp_dir)
        if (
            len(entries) == 1
            and os.path.isdir(os.path.join(temp_dir, entries[0]))
            and not os.path.exists(os.path.join(temp_dir, "manifest.json"))
        ):
            temp_dir = os.path.join(temp_dir, entries[0])

        manifest_path = os.path.join(temp_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError("manifest.json not found in the package.")

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        pack_id = manifest.get("id")
        if not pack_id:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError("Invalid manifest: missing 'id'")

        target_dir = self._get_pack_dir(pack_id)
        if os.path.exists(target_dir):
            print(f"🔄 Updating existing pack: {pack_id}")
            shutil.rmtree(target_dir)

        # Ensure temp_dir parent is writable for shutil.move
        shutil.move(temp_dir, target_dir)
        return pack_id
