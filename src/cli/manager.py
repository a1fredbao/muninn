import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import urllib.request
import zipfile

from ..core.base_plugin import BaseRecitePlugin

# Timeout for remote pack downloads (in seconds)
DOWNLOAD_TIMEOUT = 30

# Timeout for subprocess operations (venv creation, pip install) in seconds
SUBPROCESS_TIMEOUT = 300


class PackageManager:
    def __init__(self):
        self.packs_dir = os.path.expanduser("~/.muninn/packs")
        os.makedirs(self.packs_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_pack_id(pack_id: str) -> None:
        """Validate that pack_id is safe to use in filesystem paths.

        Raises ValueError if pack_id contains path traversal sequences
        or other unsafe characters.
        """
        if not isinstance(pack_id, str):
            raise ValueError(f"pack_id must be a string, got {type(pack_id).__name__}")

        if not pack_id:
            raise ValueError("pack_id cannot be empty")

        # Check for path traversal attempts
        if pack_id in (".", ".."):
            raise ValueError(f"Invalid pack_id: '{pack_id}' is not allowed")

        # Check for path separators
        if os.sep in pack_id or "/" in pack_id or "\\" in pack_id:
            raise ValueError(f"Invalid pack_id: '{pack_id}' must not contain path separators")

        # Enforce alphanumeric, dots, underscores, and hyphens only
        if not re.match(r"^[A-Za-z0-9._-]+$", pack_id):
            raise ValueError(
                f"Invalid pack_id: '{pack_id}' must contain only alphanumeric characters, "
                "dots, underscores, and hyphens"
            )

    def install_pack(self, source: str) -> str:
        """Install a pack from a local directory, a zip file, or a GitHub URL.

        Source formats::

            ./my-pack              # local directory (relative)
            /abs/path/to/pack      # local directory (absolute)
            ./my-pack.zip          # local zip file
            user/repo              # GitHub shorthand (default branch: main)
            user/repo@v1.0.0       # GitHub shorthand with tag/branch
            https://github.com/user/repo
                Records the source in the installed packs manifest.json
        so that ``upgrade_pack()`` knows where to fetch updates from.
        """
        if self._is_url(source):
            resolved = self._resolve_download_url(source)
            source_info = self._github_source_key(source)
            return self._install_remote(resolved, source_info)

        if self._is_github_short(source):
            url = self._github_short_to_url(source)
            source_info = f"github:{source}"
            return self._install_remote(url, source_info)

        abs_path = os.path.abspath(source)
        source_info = f"local:{abs_path}"
        return self._install_local(source, source_info)

    def uninstall_pack(self, pack_id: str):
        """Remove a pack from the local packs directory."""
        self._validate_pack_id(pack_id)
        pack_dir = self._get_pack_dir(pack_id)
        if not os.path.exists(pack_dir):
            raise FileNotFoundError(f"Pack '{pack_id}' is not installed.")
        shutil.rmtree(pack_dir)

        # Also remove the per-pack virtual environment if it exists
        venv_dir = self._get_pack_venv_dir(pack_id)
        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)

        print(f"🗑️  Pack '{pack_id}' has been uninstalled.")

    def upgrade_pack(self, pack_id: str) -> bool:
        """Upgrade *pack_id* if a newer version is available.

        Returns ``True`` if an upgrade was performed, ``False`` otherwise.
        """
        self._validate_pack_id(pack_id)
        manifest = self._read_installed_manifest(pack_id)
        if manifest is None:
            raise FileNotFoundError(f"Pack '{pack_id}' is not installed.")

        source = manifest.get("source")
        if not source:
            print(f"⚠️  '{pack_id}' has no source recorded — cannot upgrade.")
            return False

        current_ver = manifest.get("version")
        if not current_ver:
            print(f"⚠️  '{pack_id}' has no version in manifest — cannot upgrade.")
            return False

        remote_manifest = self._fetch_remote_manifest(source)

        if remote_manifest is None:
            print(
                f"⚠️  Could not fetch remote manifest for '{pack_id}' — network error, missing path, or unsupported source."
            )
            return False

        remote_ver = remote_manifest.get("version")
        if not remote_ver:
            print(
                f"⚠️  Remote manifest for '{pack_id}' has no version — cannot upgrade."
            )
            return False
        if self._is_newer(remote_ver, current_ver):
            old_ver = current_ver
            new_ver = remote_ver
            print(f"⬆️  Upgrading '{pack_id}': {old_ver} → {new_ver}")
            return self._reinstall_from_source(pack_id, source)

        print(f"✅ '{pack_id}' ({current_ver}) is already up to date.")
        return False

    def upgrade_all(self) -> dict[str, bool]:
        """Upgrade every installed pack that has a newer version available.

        Returns a mapping of ``pack_id → upgraded (bool)``.
        """
        results: dict[str, bool] = {}
        for pack in self.list_packs():
            try:
                pid = pack["id"]
                results[pid] = self.upgrade_pack(pid)
            except Exception as exc:  # noqa: BLE001
                pid = pack.get("id", "unknown")
                print(f"❌ Failed to upgrade '{pid}': {exc}")
                if pid != "unknown":
                    results[pid] = False
        return results

    def load_plugin(self, pack_id: str) -> BaseRecitePlugin:
        """Dynamically load the plugin.py from the pack_id directory."""
        self._validate_pack_id(pack_id)
        pack_dir = self._get_pack_dir(pack_id)
        if not os.path.exists(pack_dir):
            raise FileNotFoundError(f"Pack '{pack_id}' not found.")

        plugin_path = os.path.join(pack_dir, "plugin.py")
        if not os.path.exists(plugin_path):
            raise FileNotFoundError(f"plugin.py not found in {pack_id}.")

        orig_sys_path = sys.path.copy()
        # Make packages from the pack's isolated virtual environment importable (e.g. openai, httpx)
        venv_site = self._get_pack_site_packages(pack_id)
        if os.path.isdir(venv_site):
            sys.path.insert(0, venv_site)

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
            sys.path[:] = orig_sys_path

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
        return source.startswith("https://")

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

    @staticmethod
    def _github_source_key(url: str) -> str:
        """Extract ``github:owner/repo`` from a GitHub URL."""
        match = re.match(
            r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?(?:@([\w.\-/]+))?/?$",
            url.rstrip("/"),
        )
        if match:
            ref = match.group(3)
            key = f"github:{match.group(1)}/{match.group(2)}"
            if ref:
                key += f"@{ref}"
            return key
        return url

    # -- install backends --------------------------------------------------

    def _install_local(self, source: str, source_info: str = "") -> str:
        """Install from a local directory or zip file (existing logic)."""
        if not os.path.exists(source):
            raise FileNotFoundError(f"Path not found: {source}")

        temp_dir = None
        if os.path.isdir(source):
            temp_dir = tempfile.mkdtemp(dir=self.packs_dir, prefix=".temp_")
            try:
                shutil.copytree(source, temp_dir, dirs_exist_ok=True)
                pack_id = self._finalise_install(temp_dir, source_info)
                temp_dir = None  # Successfully finalized, don't clean up
            finally:
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        elif zipfile.is_zipfile(source):
            temp_dir = tempfile.mkdtemp(dir=self.packs_dir, prefix=".temp_")
            try:
                with zipfile.ZipFile(source) as zf:
                    zf.extractall(temp_dir)
                pack_id = self._finalise_install(temp_dir, source_info)
                temp_dir = None  # Successfully finalized, don't clean up
            finally:
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            raise ValueError(
                "Unsupported file format. Must be a directory or zip file."
            )

        print(f"✅ Successfully installed pack '{pack_id}'")
        return pack_id

    def _install_remote(self, url: str, source_info: str = "") -> str:
        """Download a remote zip and install it."""
        print(f"⬇️  Downloading {url} ...")

        # Download to a separate temporary file (not inside the staging directory)
        zip_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix=".pack_")
        temp_dir = None

        try:
            try:
                with (
                    urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as resp,
                    os.fdopen(zip_fd, "wb") as f,
                ):
                    shutil.copyfileobj(resp, f)
            except Exception as exc:
                raise RuntimeError(f"Failed to download from {url}: {exc}") from exc

            if not zipfile.is_zipfile(zip_path):
                raise ValueError(
                    "Downloaded file is not a valid zip. "
                    "Make sure the URL points to a GitHub repository, not a web page."
                )

            # Create a clean staging directory for extraction
            temp_dir = tempfile.mkdtemp(dir=self.packs_dir, prefix=".temp_")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(temp_dir)

            pack_id = self._finalise_install(temp_dir, source_info)
            temp_dir = None  # Successfully finalized, don't clean up
            print(f"✅ Successfully installed pack '{pack_id}'")
            return pack_id
        finally:
            # Clean up the downloaded zip file
            if os.path.exists(zip_path):
                os.unlink(zip_path)
            # Clean up staging directory on failure
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _finalise_install(self, temp_dir: str, source_info: str = "") -> str:
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

        # Validate pack_id to prevent path traversal attacks
        try:
            self._validate_pack_id(pack_id)
        except ValueError as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError(f"Invalid manifest: {e}") from e

        # Inject source tracking info before writing
        if source_info:
            manifest["source"] = source_info
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=4, ensure_ascii=False)

        # Install dependencies *before* replacing the existing pack so
        # that a failed pip install does not leave the pack in a broken
        # state or destroy the previous version.
        self._install_pack_dependencies(temp_dir, pack_id)

        target_dir = self._get_pack_dir(pack_id)
        if os.path.exists(target_dir):
            print(f"🔄 Updating existing pack: {pack_id}")
            shutil.rmtree(target_dir)

        # Ensure temp_dir parent is writable for shutil.move
        shutil.move(temp_dir, target_dir)

        return pack_id

    # ------------------------------------------------------------------
    # Internal: per-pack dependency management
    # ------------------------------------------------------------------
    # Each pack that declares a ``requirements.txt`` gets its own
    # isolated venv under ``~/.muninn/venvs/<pack_id>/``.  This
    # prevents version conflicts between packs.

    def _get_pack_venv_dir(self, pack_id: str) -> str:
        """Return the path to the isolated venv for *pack_id*."""
        return os.path.join(os.path.expanduser("~/.muninn/venvs"), pack_id)

    def _ensure_pack_venv(self, pack_id: str) -> str:
        """Return the path to the Python interpreter inside *pack_id*'s
        isolated venv, creating the venv if it doesn't already exist."""
        venv_dir = self._get_pack_venv_dir(pack_id)
        exe_name = os.path.basename(sys.executable)
        python_exe = os.path.join(
            venv_dir,
            "Scripts" if os.name == "nt" else "bin",
            exe_name,
        )
        if os.path.isfile(python_exe):
            return python_exe

        try:
            subprocess.run(
                [sys.executable, "-m", "venv", "--clear", venv_dir],
                check=True,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Timed out creating dependency environment at '{venv_dir}' "
                f"after {SUBPROCESS_TIMEOUT} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Failed to create dependency environment at "
                f"'{venv_dir}'.  Your Python installation may "
                "not include 'venv' (try 'apt install python3-venv' "
                f"on Debian/Ubuntu).  Original error: {exc.stderr.strip()}"
            ) from exc
        return python_exe

    def _get_pack_site_packages(self, pack_id: str) -> str:
        """Return the site-packages directory for *pack_id*'s venv."""
        return sysconfig.get_path(
            "purelib",
            scheme="venv",
            vars={"base": self._get_pack_venv_dir(pack_id)},
        )

    def _install_pack_dependencies(self, pack_dir: str, pack_id: str) -> None:
        """If *pack_dir* contains a ``requirements.txt``, install its
        contents into the pack's isolated venv."""
        req_path = os.path.join(pack_dir, "requirements.txt")
        if not os.path.isfile(req_path):
            return

        # Skip empty requirements files --- venv creation would be wasteful.
        if os.path.getsize(req_path) == 0:
            return

        venv_python = self._ensure_pack_venv(pack_id)
        pip = os.path.join(os.path.dirname(venv_python), "pip")

        print(f"📦 Installing dependencies for '{pack_id}' ...")
        try:
            subprocess.run(
                [pip, "install", "--quiet", "-r", req_path],
                check=True,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Timed out installing dependencies for '{pack_id}' after {SUBPROCESS_TIMEOUT} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Failed to install dependencies for '{pack_id}': {exc.stderr.strip()}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal: upgrade helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------

    def _read_installed_manifest(self, pack_id: str) -> dict | None:
        manifest_path = os.path.join(self._get_pack_dir(pack_id), "manifest.json")
        if not os.path.exists(manifest_path):
            return None
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def _fetch_remote_manifest(self, source: str) -> dict | None:
        """Fetch the remote manifest.json for *source*.

        Returns ``None`` when the source is unavailable (missing local
        path, network error, 404, etc.).
        """
        if source.startswith("github:"):
            return self._fetch_github_manifest(source)
        if source.startswith("local:"):
            return self._read_local_source_manifest(source)
        return None

    def _fetch_github_manifest(self, source: str) -> dict | None:
        """Fetch ``manifest.json`` from a ``github:owner/repo[@ref]`` source."""
        key = source.removeprefix("github:")
        if "@" in key:
            owner_repo, ref = key.rsplit("@", 1)
        else:
            owner_repo, ref = key, "main"

        candidates = [ref] if ref != "main" else ["main", "master"]
        for branch in candidates:
            url = (
                f"https://raw.githubusercontent.com/{owner_repo}/{branch}/manifest.json"
            )
            try:
                with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

        return None

    @staticmethod
    def _read_local_source_manifest(source: str) -> dict | None:
        """Read ``manifest.json`` from a ``local:/path`` source."""
        path = source.removeprefix("local:")
        manifest_path = os.path.join(path, "manifest.json")
        if not os.path.exists(manifest_path):
            return None
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _version_tuple(version_str: str) -> tuple[int, ...]:
        """Parse version string to normalized tuple, handling prefixes/suffixes.

        Examples:
            "1.0.0" -> (1, 0, 0)
            "v1.0.0" -> (1, 0, 0)
            "1.0.0-beta" -> (1, 0, 0)
            "1.0" -> (1, 0, 0)
        """
        # Strip common prefixes
        cleaned = version_str.lstrip("vV")

        # Extract numeric parts before any non-numeric suffix
        numeric_parts = []
        for part in cleaned.split("."):
            # Take only leading digits from each part
            match = re.match(r"(\d+)", part)
            if match:
                numeric_parts.append(int(match.group(1)))
            else:
                break

        # Normalize to at least 3 parts for consistent comparison
        while len(numeric_parts) < 3:
            numeric_parts.append(0)

        return tuple(numeric_parts)

    @staticmethod
    def _is_newer(remote_ver: str, local_ver: str) -> bool:
        return PackageManager._version_tuple(
            remote_ver
        ) > PackageManager._version_tuple(local_ver)

    def _reinstall_from_source(self, pack_id: str, source: str) -> bool:
        """Re-install *pack_id* from its recorded *source*.

        Returns True if reinstallation succeeded, False otherwise.
        """
        if source.startswith("github:"):
            src = source.removeprefix("github:")
            self.install_pack(src)
            return True
        elif source.startswith("local:"):
            path = source.removeprefix("local:")
            if not os.path.exists(path):
                print(f"⚠️  Source path '{path}' no longer exists — skipping.")
                return False
            self.install_pack(path)
            return True
        else:
            print(f"⚠️  Unknown source format for '{pack_id}': {source}")
            return False
