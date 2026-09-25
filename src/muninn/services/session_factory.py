"""Construction and cleanup of complete training sessions."""

from __future__ import annotations

import asyncio

from ..core.state import StateManager
from .package_manager import PackageManager
from .training_session import TrainingSession


class SessionFactory:
    def __init__(
        self,
        package_manager: PackageManager | None = None,
        *,
        state_dir: str | None = None,
    ) -> None:
        self.package_manager = package_manager or PackageManager()
        self.state_dir = state_dir

    async def create(self, pack_id: str) -> TrainingSession:
        loaded = await asyncio.to_thread(
            self.package_manager.load_plugin,
            pack_id,
        )
        adapter = await self.package_manager.create_plugin_adapter(loaded)
        progress_store: StateManager | None = None
        try:
            progress_store = StateManager(pack_id, self.state_dir)
            return await TrainingSession.create(
                pack_id,
                adapter,
                progress_store,
            )
        except Exception:
            await adapter.aclose()
            if progress_store is not None:
                progress_store.close()
            raise
