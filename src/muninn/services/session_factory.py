"""Construction and cleanup of complete training sessions."""

from __future__ import annotations

import asyncio

from ..domain import TrainingGroup
from .catalog import CatalogService, QuestionTypeCatalogEntry
from .package_manager import PackageManager
from .training_session import QuestionRoute, TrainingSession


class SessionFactory:
    def __init__(
        self,
        package_manager: PackageManager | None = None,
        *,
        state_dir: str | None = None,
    ) -> None:
        self.package_manager = package_manager or PackageManager()
        self.state_dir = state_dir
        self.catalog = CatalogService(self.package_manager)

    async def create(self, pack_id: str) -> TrainingSession:
        """Create a single-pack session with every question type enabled."""

        loaded = await asyncio.to_thread(
            self.package_manager.load_plugin,
            pack_id,
        )
        adapter = await self.package_manager.create_plugin_adapter(loaded)
        try:
            descriptors = await adapter.list_question_types()
            routes = [
                QuestionRoute(
                    pack_id=pack_id,
                    question_type_id=descriptor.key,
                    plugin=adapter,
                )
                for descriptor in descriptors
            ]
            return await TrainingSession.create(
                routes,
                state_dir=self.state_dir,
            )
        except Exception:
            await adapter.aclose()
            raise

    async def create_group(self, group: TrainingGroup) -> TrainingSession:
        catalog_entries, errors = await self.catalog.list_question_types()
        selected = self._resolve_selections(group, catalog_entries)
        selected_keys = {
            (entry.pack_key, entry.question_type_key) for entry in selected
        }
        requested_keys = {
            (selection.pack_key, selection.question_type_key)
            for selection in group.selections
            if selection.enabled
        }
        missing_keys = requested_keys - selected_keys
        if missing_keys:
            errors.append(
                f"{len(missing_keys)} selected question type(s) are "
                "no longer available and will be skipped."
            )
        if not selected:
            detail = f" Errors: {'; '.join(errors)}" if errors else ""
            raise ValueError(
                "None of the selected question types are available." + detail
            )

        loaded_plugins, load_errors = await self.catalog.load_plugins(selected)
        if not loaded_plugins:
            detail = f" Errors: {'; '.join(load_errors)}" if load_errors else ""
            raise ValueError(
                "Unable to load any plugin for this training group." + detail
            )

        weight_by_key = {
            (selection.pack_key, selection.question_type_key): selection.weight
            for selection in group.selections
            if selection.enabled
        }
        routes: list[QuestionRoute] = []
        for loaded_plugin in loaded_plugins:
            for entry in loaded_plugin.entries:
                routes.append(
                    QuestionRoute(
                        pack_id=entry.pack_id,
                        question_type_id=entry.question_type_id,
                        plugin=loaded_plugin.adapter,
                        weight=weight_by_key.get(
                            (entry.pack_key, entry.question_type_key),
                            1.0,
                        ),
                    )
                )
        try:
            session = await TrainingSession.create(
                routes,
                state_dir=self.state_dir,
            )
        except Exception:
            for loaded_plugin in loaded_plugins:
                await loaded_plugin.adapter.aclose()
            raise
        if load_errors:
            session.warnings = tuple(load_errors)
        return session

    @staticmethod
    def _resolve_selections(
        group: TrainingGroup,
        entries: list[QuestionTypeCatalogEntry],
    ) -> list[QuestionTypeCatalogEntry]:
        selected_keys = {
            (selection.pack_key, selection.question_type_key)
            for selection in group.selections
            if selection.enabled
        }
        return [
            entry
            for entry in entries
            if (entry.pack_key, entry.question_type_key) in selected_keys
        ]
