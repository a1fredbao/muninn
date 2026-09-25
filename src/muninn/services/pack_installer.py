"""Pack source resolution and transactional installation."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from typing import Literal

from .dependency import DependencyEnvironment
from .manifest import ManifestError, PackManifest, load_manifest_summaries
from .operations import (
    CancellationToken,
    ProgressCallback,
    emit,
)

DOWNLOAD_TIMEOUT = 30


@dataclass(frozen=True, slots=True)
class ResolvedPackSource:
    kind: Literal["local-directory", "local-zip", "remote-zip", "direct-url"]
    location: str
    source_info: str


class PackSourceResolver:
    """Turn user input into one explicit source description."""

    @staticmethod
    def _is_url(source: str) -> bool:
        return source.startswith("https://")

    @staticmethod
    def _is_github_short(source: str) -> bool:
        return bool(
            re.fullmatch(
                r"[a-zA-Z0-9](?:[\w.\-]*[a-zA-Z0-9])?/"
                r"[a-zA-Z0-9](?:[\w.\-]*[a-zA-Z0-9])?"
                r"(?:@[\w.\-/]+)?",
                source,
            )
        )

    @staticmethod
    def github_short_to_url(source: str) -> str:
        if "@" in source:
            owner_repo, ref = source.split("@", 1)
        else:
            owner_repo, ref = source, "main"
        return f"https://github.com/{owner_repo}/archive/refs/heads/{ref}.zip"

    @staticmethod
    def resolve_download_url(url: str) -> str:
        match = re.match(
            r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)"
            r"(?:\.git)?(?:@([\w.\-/]+))?/?$",
            url.rstrip("/"),
        )
        if match:
            owner, repo, ref = match.group(1), match.group(2), match.group(3)
            ref = ref or "main"
            return f"https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip"
        return url

    @staticmethod
    def github_source_key(url: str) -> str:
        match = re.match(
            r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)"
            r"(?:\.git)?(?:@([\w.\-/]+))?/?$",
            url.rstrip("/"),
        )
        if not match:
            return url
        ref = match.group(3)
        key = f"github:{match.group(1)}/{match.group(2)}"
        if ref:
            key += f"@{ref}"
        return key

    def resolve(self, source: str) -> ResolvedPackSource:
        if self._is_url(source):
            resolved = self.resolve_download_url(source)
            kind: Literal["remote-zip", "direct-url"] = (
                "remote-zip" if resolved.endswith(".zip") else "direct-url"
            )
            return ResolvedPackSource(
                kind=kind,
                location=resolved,
                source_info=self.github_source_key(source),
            )

        if self._is_github_short(source):
            return ResolvedPackSource(
                kind="remote-zip",
                location=self.github_short_to_url(source),
                source_info=f"github:{source}",
            )

        abs_path = os.path.abspath(source)
        if os.path.isdir(abs_path):
            return ResolvedPackSource(
                kind="local-directory",
                location=abs_path,
                source_info=f"local:{abs_path}",
            )
        if os.path.isfile(abs_path) and zipfile.is_zipfile(abs_path):
            return ResolvedPackSource(
                kind="local-zip",
                location=abs_path,
                source_info=f"local:{abs_path}",
            )
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Path not found: {source}")
        raise ValueError("Unsupported file format. Must be a directory or zip file.")


@dataclass(slots=True)
class StagedPack:
    """A fully prepared pack and dependency environment."""

    manifest: PackManifest
    temp_dir: str
    staging_dir: str
    environment_temp_dir: str | None
    packs_dir: str
    venvs_dir: str
    source_info: str
    committed: bool = False

    @property
    def pack_id(self) -> str:
        return self.manifest.id

    @property
    def target_dir(self) -> str:
        return os.path.join(self.packs_dir, self.pack_id)

    @property
    def target_environment_dir(self) -> str:
        return os.path.join(self.venvs_dir, self.pack_id, self.manifest.version)

    def cleanup(self) -> None:
        if self.staging_dir and os.path.exists(self.staging_dir):
            shutil.rmtree(self.staging_dir, ignore_errors=True)
        if self.environment_temp_dir and os.path.exists(self.environment_temp_dir):
            shutil.rmtree(self.environment_temp_dir, ignore_errors=True)

    def commit(self) -> None:
        """Atomically switch pack and versioned environment into place."""

        if self.committed:
            return

        token = uuid.uuid4().hex
        pack_backup = f"{self.target_dir}.backup-{token}"
        env_backup = f"{self.target_environment_dir}.backup-{token}"
        target_exists = os.path.exists(self.target_dir)
        env_exists = os.path.exists(self.target_environment_dir)

        try:
            if target_exists:
                os.replace(self.target_dir, pack_backup)
            if self.environment_temp_dir:
                os.makedirs(os.path.dirname(self.target_environment_dir), exist_ok=True)
                if env_exists:
                    os.replace(
                        self.target_environment_dir,
                        env_backup,
                    )
                os.replace(self.environment_temp_dir, self.target_environment_dir)
            os.replace(self.temp_dir, self.target_dir)
        except Exception:
            if os.path.exists(self.target_dir):
                shutil.rmtree(self.target_dir, ignore_errors=True)
            if os.path.exists(pack_backup):
                os.replace(pack_backup, self.target_dir)
            if self.environment_temp_dir and os.path.exists(
                self.target_environment_dir
            ):
                shutil.rmtree(self.target_environment_dir, ignore_errors=True)
            if os.path.exists(env_backup):
                os.replace(env_backup, self.target_environment_dir)
            raise
        else:
            shutil.rmtree(pack_backup, ignore_errors=True)
            shutil.rmtree(env_backup, ignore_errors=True)
            if self.environment_temp_dir is None and env_exists:
                shutil.rmtree(
                    self.target_environment_dir,
                    ignore_errors=True,
                )
            self.temp_dir = ""
            self.staging_dir = ""
            self.environment_temp_dir = None
            self.committed = True


class PackInstaller:
    """Prepare and commit a pack without exposing intermediate paths."""

    def __init__(
        self,
        *,
        packs_dir: str | None = None,
        dependency_environment: DependencyEnvironment | None = None,
    ) -> None:
        self.packs_dir = os.path.abspath(
            packs_dir or os.path.expanduser("~/.muninn/packs")
        )
        os.makedirs(self.packs_dir, exist_ok=True)
        self.dependencies = dependency_environment or DependencyEnvironment()
        self.venvs_dir = self.dependencies.venvs_dir
        self.sources = PackSourceResolver()

    def install(
        self,
        source: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> str:
        resolved = self.sources.resolve(source)
        staged = self.stage(resolved, progress, cancel_token)
        try:
            self._raise_if_cancelled(cancel_token)
            staged.commit()
        finally:
            staged.cleanup()
        return staged.pack_id

    def stage(
        self,
        source: ResolvedPackSource,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> StagedPack:
        self._raise_if_cancelled(cancel_token)
        emit(progress, f"Installing pack from '{source.location}'.")
        temp_dir = self._stage_source(source, progress, cancel_token)
        try:
            root = self._normalise_package_root(temp_dir)
            manifest = self._read_staged_manifest(root, source.source_info)
            environment_temp_dir = self.dependencies.prepare(
                root,
                manifest.id,
                manifest.version,
                progress,
                cancel_token,
            )
            self._raise_if_cancelled(cancel_token)
            return StagedPack(
                manifest=manifest,
                temp_dir=root,
                staging_dir=temp_dir,
                environment_temp_dir=environment_temp_dir,
                packs_dir=self.packs_dir,
                venvs_dir=self.venvs_dir,
                source_info=source.source_info,
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def list_summaries(self):
        return load_manifest_summaries(self.packs_dir)

    def _stage_source(
        self,
        source: ResolvedPackSource,
        progress: ProgressCallback | None,
        cancel_token: CancellationToken | None,
    ) -> str:
        temp_dir = tempfile.mkdtemp(dir=self.packs_dir, prefix=".temp_")
        try:
            if source.kind == "local-directory":
                shutil.copytree(source.location, temp_dir, dirs_exist_ok=True)
            elif source.kind == "local-zip":
                with zipfile.ZipFile(source.location) as archive:
                    archive.extractall(temp_dir)
            else:
                zip_path = self._download(
                    source.location,
                    progress=progress,
                    cancel_token=cancel_token,
                )
                try:
                    with zipfile.ZipFile(zip_path) as archive:
                        archive.extractall(temp_dir)
                finally:
                    os.unlink(zip_path)
            return temp_dir
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _download(
        self,
        url: str,
        progress: ProgressCallback | None,
        cancel_token: CancellationToken | None,
    ) -> str:
        emit(progress, f"Downloading {url}")
        zip_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix=".pack_")
        try:
            with (
                os.fdopen(zip_fd, "wb") as file,
                urllib.request.urlopen(
                    url,
                    timeout=DOWNLOAD_TIMEOUT,
                ) as response,
            ):
                while chunk := response.read(64 * 1024):
                    self._raise_if_cancelled(cancel_token)
                    file.write(chunk)
            if not zipfile.is_zipfile(zip_path):
                raise ValueError(
                    "Downloaded file is not a valid zip. "
                    "Make sure the URL points to a GitHub repository."
                )
            return zip_path
        except Exception:
            if os.path.exists(zip_path):
                os.unlink(zip_path)
            raise

    @staticmethod
    def _normalise_package_root(temp_dir: str) -> str:
        entries = os.listdir(temp_dir)
        if (
            len(entries) == 1
            and os.path.isdir(os.path.join(temp_dir, entries[0]))
            and not os.path.exists(os.path.join(temp_dir, "manifest.json"))
        ):
            return os.path.join(temp_dir, entries[0])
        return temp_dir

    @staticmethod
    def _read_staged_manifest(
        root: str,
        source_info: str,
    ) -> PackManifest:
        manifest_path = os.path.join(root, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("manifest.json not found in the package.")
        try:
            manifest = PackManifest.from_path(manifest_path)
        except ManifestError as exc:
            raise ValueError(f"Invalid manifest: {exc}") from exc

        manifest = manifest.with_source(source_info) if source_info else manifest
        with open(manifest_path, "w", encoding="utf-8") as file:
            json.dump(manifest.to_dict(), file, indent=4, ensure_ascii=False)
        return manifest

    @staticmethod
    def _raise_if_cancelled(cancel_token: CancellationToken | None) -> None:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
