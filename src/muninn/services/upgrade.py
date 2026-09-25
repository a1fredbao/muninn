"""Pack upgrade policy and source refresh."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .manifest import PackManifest
from .operations import (
    CancellationToken,
    OperationCancelled,
    ProgressCallback,
    UpgradeResult,
    emit,
)
from .pack_installer import PackInstaller

DOWNLOAD_TIMEOUT = 30


def parse_version(version: str) -> Version:
    try:
        return Version(version)
    except InvalidVersion as exc:
        raise ValueError(f"Invalid semantic version: {version!r}") from exc


def is_newer(remote_version: str, local_version: str) -> bool:
    return parse_version(remote_version) > parse_version(local_version)


class UpgradeService:
    def __init__(self, packs_dir: str, installer: PackInstaller) -> None:
        self.packs_dir = Path(packs_dir)
        self.installer = installer

    def upgrade_pack_result(
        self,
        pack_id: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> UpgradeResult:
        manifest_path = self.packs_dir / pack_id / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Pack '{pack_id}' is not installed.")
        manifest = PackManifest.from_path(manifest_path)
        source = manifest.source
        current_version = manifest.version

        if not source:
            message = f"Pack '{pack_id}' has no source recorded; cannot upgrade."
            emit(progress, message)
            return UpgradeResult(
                pack_id=pack_id,
                status="skipped",
                current_version=current_version,
                error=message,
            )

        remote_manifest = self._fetch_source_manifest(source)
        if remote_manifest is None:
            message = (
                f"Could not fetch remote manifest for '{pack_id}'; "
                "network error, missing path, or unsupported source."
            )
            emit(progress, message)
            return UpgradeResult(
                pack_id=pack_id,
                status="failed",
                current_version=current_version,
                error=message,
            )

        try:
            newer = is_newer(remote_manifest.version, current_version)
        except ValueError as exc:
            message = str(exc)
            emit(progress, message)
            return UpgradeResult(
                pack_id=pack_id,
                status="failed",
                current_version=current_version,
                remote_version=remote_manifest.version,
                error=message,
            )

        if not newer:
            emit(progress, f"Pack '{pack_id}' ({current_version}) is up to date.")
            return UpgradeResult(
                pack_id=pack_id,
                status="current",
                current_version=current_version,
                remote_version=remote_manifest.version,
            )

        emit(
            progress,
            f"Upgrading '{pack_id}': {current_version} -> {remote_manifest.version}",
        )
        source_arg = remove_source_prefix(source)
        try:
            self.installer.install(source_arg, progress, cancel_token)
        except OperationCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            return UpgradeResult(
                pack_id=pack_id,
                status="failed",
                current_version=current_version,
                remote_version=remote_manifest.version,
                error=str(exc),
            )
        return UpgradeResult(
            pack_id=pack_id,
            status="upgraded",
            current_version=current_version,
            remote_version=remote_manifest.version,
        )

    def upgrade_all_results(
        self,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> dict[str, UpgradeResult]:
        results: dict[str, UpgradeResult] = {}
        for summary in self.installer.list_summaries():
            if not summary.valid:
                results[summary.pack_id] = UpgradeResult(
                    pack_id=summary.pack_id,
                    status="failed",
                    error=summary.error,
                )
                continue
            try:
                results[summary.pack_id] = self.upgrade_pack_result(
                    summary.pack_id,
                    progress,
                    cancel_token,
                )
            except OperationCancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                results[summary.pack_id] = UpgradeResult(
                    pack_id=summary.pack_id,
                    status="failed",
                    error=f"Failed to upgrade '{summary.pack_id}': {exc}",
                )
        return results

    def _fetch_source_manifest(self, source: str) -> PackManifest | None:
        try:
            if source.startswith("github:"):
                return self._fetch_github_manifest(source)
            if source.startswith("local:"):
                path = source.removeprefix("local:")
                manifest_path = os.path.join(path, "manifest.json")
                if not os.path.exists(manifest_path):
                    return None
                return PackManifest.from_path(manifest_path)
        except (OSError, ValueError):
            return None
        return None

    @staticmethod
    def _fetch_github_manifest(source: str) -> PackManifest | None:
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
                with urllib.request.urlopen(
                    url,
                    timeout=DOWNLOAD_TIMEOUT,
                ) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                return PackManifest.from_dict(raw)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        return None


def remove_source_prefix(source: str) -> str:
    if source.startswith("github:"):
        return source.removeprefix("github:")
    if source.startswith("local:"):
        return source.removeprefix("local:")
    return source
