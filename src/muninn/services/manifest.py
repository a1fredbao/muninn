"""Pack manifest parsing and validation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

SUPPORTED_API_VERSIONS = {"0", "1"}
PACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class ManifestError(ValueError):
    """Raised when a pack manifest does not satisfy the pack schema."""


def validate_pack_id(pack_id: object) -> str:
    if not isinstance(pack_id, str):
        raise ManifestError(f"pack_id must be a string, got {type(pack_id).__name__}")
    if not pack_id:
        raise ManifestError("pack_id cannot be empty")
    if pack_id in {".", ".."}:
        raise ManifestError(f"Invalid pack_id: {pack_id!r}")
    if os.sep in pack_id or "/" in pack_id or "\\" in pack_id:
        raise ManifestError("pack_id must not contain path separators")
    if not PACK_ID_PATTERN.fullmatch(pack_id):
        raise ManifestError(
            "pack_id must contain only alphanumeric characters, dots, "
            "underscores, and hyphens"
        )
    return pack_id


@dataclass(frozen=True, slots=True)
class PackManifest:
    id: str
    name: str
    version: str
    author: str | None = None
    description: str = ""
    source: str | None = None
    entrypoint: str = "plugin:Plugin"
    api_version: str = "0"

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        strict: bool = True,
    ) -> PackManifest:
        pack_id = validate_pack_id(data.get("id"))

        name = data.get("name")
        if strict and (not isinstance(name, str) or not name.strip()):
            raise ManifestError("manifest field 'name' must be a non-empty string")

        version = data.get("version")
        if strict and not isinstance(version, str):
            raise ManifestError("manifest field 'version' must be a string")
        if isinstance(version, str):
            try:
                Version(version)
            except InvalidVersion as exc:
                raise ManifestError(
                    f"manifest field 'version' is not valid: {version!r}"
                ) from exc

        entrypoint = data.get("entrypoint", "plugin:Plugin")
        if not isinstance(entrypoint, str) or ":" not in entrypoint:
            raise ManifestError(
                "manifest field 'entrypoint' must use 'module:ClassName'"
            )

        api_version = str(data.get("api_version", "0"))
        if api_version not in SUPPORTED_API_VERSIONS:
            raise ManifestError(
                f"unsupported plugin api_version {api_version!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_API_VERSIONS))}"
            )

        return cls(
            id=pack_id,
            name=str(name or pack_id),
            version=str(version or "0.0.0"),
            author=(
                str(data["author"]).strip() if data.get("author") is not None else None
            ),
            description=str(data.get("description") or ""),
            source=(
                str(data["source"]).strip() if data.get("source") is not None else None
            ),
            entrypoint=entrypoint,
            api_version=api_version,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> PackManifest:
        try:
            with open(path, encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"Unable to read manifest '{path}': {exc}") from exc
        if not isinstance(raw, dict):
            raise ManifestError("manifest root must be a JSON object")
        return cls.from_dict(raw)

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    def with_source(self, source: str) -> PackManifest:
        return PackManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            author=self.author,
            description=self.description,
            source=source,
            entrypoint=self.entrypoint,
            api_version=self.api_version,
        )


@dataclass(frozen=True, slots=True)
class PackSummary:
    pack_id: str
    manifest: PackManifest | None
    error: str | None = None

    @property
    def valid(self) -> bool:
        return self.manifest is not None and self.error is None

    @property
    def name(self) -> str:
        return self.manifest.name if self.manifest else self.pack_id

    @property
    def version(self) -> str:
        return self.manifest.version if self.manifest else ""

    @property
    def author(self) -> str:
        return self.manifest.author or "" if self.manifest else ""

    @property
    def description(self) -> str:
        return self.manifest.description if self.manifest else ""

    @property
    def source(self) -> str:
        return self.manifest.source or "" if self.manifest else ""


def load_manifest_summaries(packs_dir: str | os.PathLike[str]) -> list[PackSummary]:
    summaries: list[PackSummary] = []
    root = Path(packs_dir)
    if not root.exists():
        return summaries

    for pack_dir in sorted(root.iterdir(), key=lambda item: item.name):
        if not pack_dir.is_dir() or pack_dir.name.startswith("."):
            continue
        manifest_path = pack_dir / "manifest.json"
        if not manifest_path.exists():
            summaries.append(
                PackSummary(
                    pack_id=pack_dir.name,
                    manifest=None,
                    error="manifest.json not found",
                )
            )
            continue
        try:
            manifest = PackManifest.from_path(manifest_path)
        except ManifestError as exc:
            summaries.append(
                PackSummary(
                    pack_id=pack_dir.name,
                    manifest=None,
                    error=str(exc),
                )
            )
        else:
            summaries.append(PackSummary(pack_id=manifest.id, manifest=manifest))
    return summaries
