"""Package-management facade used by the CLI and TUI."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from .dependency import DependencyEnvironment
from .manifest import PackManifest, PackSummary, validate_pack_id
from .operations import (
    CancellationToken,
    OperationCancelled,
    OperationResult,
    PackageProgress,
    ProgressCallback,
    UpgradeResult,
)
from .pack_installer import (
    PackInstaller,
    PackSourceResolver,
)
from .plugin_loader import LoadedPlugin, PluginLoader, WorkerPluginAdapter
from .upgrade import UpgradeService, is_newer

__all__ = [
    "CancellationToken",
    "OperationCancelled",
    "PackageManager",
    "PackageProgress",
    "ProgressCallback",
    "UpgradeResult",
]


class PackageManager:
    """Compatibility facade over the package subsystems."""

    def __init__(
        self,
        *,
        packs_dir: str | None = None,
        venvs_dir: str | None = None,
    ):
        self.packs_dir = os.path.abspath(
            packs_dir or os.path.expanduser("~/.muninn/packs")
        )
        os.makedirs(self.packs_dir, exist_ok=True)
        self.dependencies = DependencyEnvironment(venvs_dir)
        self.installer = PackInstaller(
            packs_dir=self.packs_dir,
            dependency_environment=self.dependencies,
        )
        self.upgrades = UpgradeService(self.packs_dir, self.installer)
        self.plugin_loader = PluginLoader(
            self.packs_dir,
            self.dependencies,
        )

    @staticmethod
    def _validate_pack_id(pack_id: str) -> None:
        validate_pack_id(pack_id)

    def install_pack(
        self,
        source: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> str:
        return self.installer.install(source, progress, cancel_token)

    def uninstall_pack(
        self,
        pack_id: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> None:
        validate_pack_id(pack_id)
        if progress is not None:
            progress(PackageProgress(f"Uninstalling pack '{pack_id}'."))
        self._raise_if_cancelled(cancel_token)
        pack_dir = self._get_pack_dir(pack_id)
        if not os.path.exists(pack_dir):
            raise FileNotFoundError(f"Pack '{pack_id}' is not installed.")
        shutil.rmtree(pack_dir)
        self.dependencies.remove_pack(pack_id)

    def install_pack_result(
        self,
        source: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> OperationResult[str]:
        try:
            return OperationResult.success(
                self.install_pack(source, progress, cancel_token)
            )
        except OperationCancelled:
            return OperationResult.cancelled()
        except (OSError, ValueError, RuntimeError) as exc:
            return OperationResult.failure(str(exc))

    def uninstall_pack_result(
        self,
        pack_id: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> OperationResult[str]:
        try:
            self.uninstall_pack(pack_id, progress, cancel_token)
            return OperationResult.success(pack_id)
        except OperationCancelled:
            return OperationResult.cancelled()
        except (OSError, ValueError) as exc:
            return OperationResult.failure(str(exc))

    def create_template_result(
        self,
        pack_id: str,
        target_dir: str = ".",
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> OperationResult[str]:
        try:
            return OperationResult.success(
                self.create_template(
                    pack_id,
                    target_dir,
                    progress,
                    cancel_token,
                )
            )
        except OperationCancelled:
            return OperationResult.cancelled()
        except (OSError, ValueError) as exc:
            return OperationResult.failure(str(exc))

    def upgrade_pack(
        self,
        pack_id: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> bool:
        return self.upgrade_pack_result(
            pack_id,
            progress,
            cancel_token,
        ).upgraded

    def upgrade_pack_result(
        self,
        pack_id: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> UpgradeResult:
        validate_pack_id(pack_id)
        self._raise_if_cancelled(cancel_token)
        return self.upgrades.upgrade_pack_result(
            pack_id,
            progress,
            cancel_token,
        )

    def upgrade_all_results(
        self,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> dict[str, UpgradeResult]:
        return self.upgrades.upgrade_all_results(progress, cancel_token)

    def upgrade_all(
        self,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> dict[str, bool]:
        return {
            pack_id: result.upgraded
            for pack_id, result in self.upgrade_all_results(
                progress,
                cancel_token,
            ).items()
        }

    def load_plugin(self, pack_id: str) -> LoadedPlugin:
        """Return the isolated worker configuration for a pack."""

        return self.plugin_loader.load(pack_id)

    async def create_plugin_adapter(
        self,
        loaded: LoadedPlugin,
    ) -> WorkerPluginAdapter:
        return await self.plugin_loader.create_adapter(loaded)

    def ensure_pack_installed(self, pack_id: str) -> None:
        validate_pack_id(pack_id)
        pack_dir = self._get_pack_dir(pack_id)
        if not os.path.isdir(pack_dir):
            raise FileNotFoundError(f"Pack '{pack_id}' not found.")
        if not os.path.isfile(os.path.join(pack_dir, "plugin.py")):
            raise FileNotFoundError(f"plugin.py not found in '{pack_id}'.")

    def list_pack_summaries(self) -> list[PackSummary]:
        return self.installer.list_summaries()

    def list_packs(
        self,
        progress: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Backward-compatible dictionary view for existing presenters."""

        packs: list[dict[str, Any]] = []
        for summary in self.list_pack_summaries():
            if summary.valid and summary.manifest is not None:
                packs.append(summary.manifest.to_dict())
                continue
            if progress is not None:
                progress(
                    PackageProgress(
                        f"Skipping invalid manifest for "
                        f"'{summary.pack_id}': {summary.error}"
                    )
                )
        return packs

    def list_packs_with_errors(self) -> list[PackSummary]:
        return self.list_pack_summaries()

    def create_template(
        self,
        pack_id: str,
        target_dir: str = ".",
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> str:
        validate_pack_id(pack_id)
        pack_dir = os.path.join(target_dir, pack_id)
        if os.path.exists(pack_dir):
            raise FileExistsError(f"Directory {pack_dir} already exists.")

        self._raise_if_cancelled(cancel_token)
        if progress is not None:
            progress(PackageProgress(f"Creating template at {pack_dir}."))
        os.makedirs(pack_dir)

        manifest = PackManifest(
            id=pack_id,
            name=f"{pack_id} Pack",
            author="Your Name",
            version="1.0.0",
            description="A new training pack for Muninn.",
            entrypoint="plugin:Plugin",
            api_version="1",
        )
        with open(
            os.path.join(pack_dir, "manifest.json"),
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(manifest.to_dict(), file, indent=4, ensure_ascii=False)

        plugin_code = '''"""A minimal Muninn plugin using DataPlugin."""

from typing import ClassVar

from muninn.core.helpers import DataPlugin, QuestionType


class Plugin(DataPlugin):
    QUESTION_TYPES: ClassVar[list[QuestionType]] = [
        # Define question directions here.
    ]

    def load_records(self) -> list[dict]:
        # Return records loaded from files in self.workspace_dir.
        return []
'''
        with open(
            os.path.join(pack_dir, "plugin.py"),
            "w",
            encoding="utf-8",
        ) as file:
            file.write(plugin_code)
        return pack_dir

    def _get_pack_dir(self, pack_id: str) -> str:
        return os.path.join(self.packs_dir, pack_id)

    def _get_pack_venv_dir(self, pack_id: str) -> str:
        return self.dependencies.get_pack_venv_dir(pack_id)

    def _get_pack_site_packages(self, pack_id: str) -> str:
        manifest = self._read_installed_manifest_object(pack_id)
        if manifest is not None:
            versioned = self.dependencies.get_site_packages(
                pack_id,
                manifest.version,
            )
            if os.path.isdir(versioned):
                return versioned
        return self.dependencies.get_site_packages(pack_id)

    def _ensure_pack_venv(
        self,
        pack_id: str,
        cancel_token: CancellationToken | None = None,
    ) -> str:
        """Compatibility helper for callers that explicitly manage a venv."""

        venv_dir = self._get_pack_venv_dir(pack_id)
        return self.dependencies._create_venv(venv_dir, cancel_token)

    def _install_pack_dependencies(
        self,
        pack_dir: str,
        pack_id: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> None:
        manifest_path = os.path.join(pack_dir, "manifest.json")
        manifest = PackManifest.from_path(manifest_path)
        temp_env = self.dependencies.prepare(
            pack_dir,
            pack_id,
            manifest.version,
            progress,
            cancel_token,
        )
        if temp_env is None:
            return
        target = self.dependencies.get_pack_venv_dir(pack_id, manifest.version)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target):
            shutil.rmtree(target)
        os.replace(temp_env, target)

    def _run_subprocess(self, args, *, timeout, cancel_token=None):
        return self.dependencies._run_subprocess(
            args,
            timeout=timeout,
            cancel_token=cancel_token,
        )

    @staticmethod
    def _version_tuple(version_str: str) -> tuple[int, ...]:
        try:
            version = Version(version_str)
        except InvalidVersion:
            return (0, 0, 0)
        return (version.major, version.minor, version.micro)

    @staticmethod
    def _is_newer(remote_ver: str, local_ver: str) -> bool:
        return is_newer(remote_ver, local_ver)

    @staticmethod
    def _is_url(source: str) -> bool:
        return PackSourceResolver._is_url(source)

    @staticmethod
    def _is_github_short(source: str) -> bool:
        return PackSourceResolver._is_github_short(source)

    @staticmethod
    def _github_short_to_url(source: str) -> str:
        return PackSourceResolver.github_short_to_url(source)

    @staticmethod
    def _resolve_download_url(url: str) -> str:
        return PackSourceResolver.resolve_download_url(url)

    @staticmethod
    def _github_source_key(url: str) -> str:
        return PackSourceResolver.github_source_key(url)

    def _fetch_remote_manifest(
        self,
        source: str,
        cancel_token: CancellationToken | None = None,
    ) -> PackManifest | None:
        self._raise_if_cancelled(cancel_token)
        manifest = self.upgrades._fetch_source_manifest(source)
        self._raise_if_cancelled(cancel_token)
        return manifest

    def _read_installed_manifest_object(
        self,
        pack_id: str,
    ) -> PackManifest | None:
        path = Path(self._get_pack_dir(pack_id)) / "manifest.json"
        if not path.exists():
            return None
        return PackManifest.from_path(path)

    @staticmethod
    def _raise_if_cancelled(cancel_token: CancellationToken | None) -> None:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
