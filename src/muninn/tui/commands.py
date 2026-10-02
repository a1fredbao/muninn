"""Command palette providers for packs, groups, and question types."""

from __future__ import annotations

from functools import partial

from textual.command import Hit, Hits, Provider


class MuninnCommandProvider(Provider):
    """Search Muninn resources from Textual's command palette."""

    async def startup(self) -> None:
        app = self.app
        self.packs = app.package_manager.list_pack_summaries()
        self.groups = list(app.config_store.load().groups)
        self.question_types, _ = await app.get_catalog_entries()

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        app = self.app

        for group in self.groups:
            label = f"training group {group.name}"
            score = matcher.match(label)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(label),
                    partial(app.run_group_from_palette, group.id),
                    help="Open and start this training group",
                )

        for entry in self.question_types:
            label = f"question type {entry.pack_name} {entry.label}"
            score = matcher.match(label)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(label),
                    partial(app.open_question_type_from_palette, entry),
                    help=(f"{entry.problem_count} problem(s) in {entry.pack_name}"),
                )

        for pack in self.packs:
            if not pack.valid:
                continue
            label = f"training pack {pack.name}"
            score = matcher.match(label)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(label),
                    partial(app.open_pack_from_palette, pack.pack_id),
                    help="Open all question types from this pack",
                )
