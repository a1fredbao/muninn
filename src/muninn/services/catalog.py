"""Installed pack and question-type discovery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..keys import pack_key as make_pack_key
from ..keys import question_type_key as make_question_type_key
from .package_manager import PackageManager
from .plugin_loader import LoadedPlugin, PluginProtocolError, WorkerPluginAdapter


@dataclass(frozen=True, slots=True)
class QuestionTypeCatalogEntry:
    pack_id: str
    pack_name: str
    pack_key: str
    question_type_id: str
    question_type_key: str
    label: str
    description: str
    problem_count: int


@dataclass(slots=True)
class LoadedCatalogPlugin:
    loaded: LoadedPlugin
    adapter: WorkerPluginAdapter
    entries: list[QuestionTypeCatalogEntry]


class CatalogService:
    """Load installed plugins and expose a searchable question-type catalog."""

    def __init__(self, package_manager: PackageManager) -> None:
        self.package_manager = package_manager

    async def list_question_types(
        self,
    ) -> tuple[list[QuestionTypeCatalogEntry], list[str]]:
        entries: list[QuestionTypeCatalogEntry] = []
        errors: list[str] = []
        summaries = self.package_manager.list_pack_summaries()
        for summary in summaries:
            if not summary.valid:
                errors.append(f"{summary.pack_id}: {summary.error}")
                continue
            try:
                loaded = await asyncio.to_thread(
                    self.package_manager.load_plugin,
                    summary.pack_id,
                )
                adapter = await self.package_manager.create_plugin_adapter(loaded)
                try:
                    descriptors = await adapter.list_question_types()
                finally:
                    await adapter.aclose()
            except (PluginProtocolError, OSError, RuntimeError, ValueError) as exc:
                errors.append(f"{summary.pack_id}: {exc}")
                continue

            pack_hash = make_pack_key(summary.pack_id)
            entries.extend(
                QuestionTypeCatalogEntry(
                    pack_id=summary.pack_id,
                    pack_name=summary.name,
                    pack_key=pack_hash,
                    question_type_id=descriptor.key,
                    question_type_key=make_question_type_key(
                        summary.pack_id,
                        descriptor.key,
                    ),
                    label=descriptor.label,
                    description=descriptor.description,
                    problem_count=descriptor.problem_count,
                )
                for descriptor in descriptors
            )
        return entries, errors

    async def load_plugins(
        self,
        question_type_entries: list[QuestionTypeCatalogEntry],
    ) -> tuple[list[LoadedCatalogPlugin], list[str]]:
        """Load one worker per selected pack and retain it for a session."""

        errors: list[str] = []
        loaded_plugins: list[LoadedCatalogPlugin] = []
        by_pack: dict[str, list[QuestionTypeCatalogEntry]] = {}
        for entry in question_type_entries:
            by_pack.setdefault(entry.pack_id, []).append(entry)

        for pack_id, pack_entries in by_pack.items():
            try:
                loaded = await asyncio.to_thread(
                    self.package_manager.load_plugin,
                    pack_id,
                )
                adapter = await self.package_manager.create_plugin_adapter(loaded)
                descriptors = {
                    descriptor.key: descriptor
                    for descriptor in await adapter.list_question_types()
                }
            except (PluginProtocolError, OSError, RuntimeError, ValueError) as exc:
                errors.append(f"{pack_id}: {exc}")
                continue

            missing = [
                entry.question_type_id
                for entry in pack_entries
                if entry.question_type_id not in descriptors
            ]
            if missing:
                await adapter.aclose()
                errors.append(f"{pack_id}: missing question types {', '.join(missing)}")
                continue
            loaded_plugins.append(
                LoadedCatalogPlugin(
                    loaded=loaded,
                    adapter=adapter,
                    entries=pack_entries,
                )
            )
        return loaded_plugins, errors
