import os
import sys
import shutil
import zipfile
import json
import importlib.util
from typing import Optional

from ..core.base_plugin import BaseRecitePlugin


class PackageManager:
    def __init__(self):
        self.packs_dir = os.path.expanduser("~/.muninn/packs")
        os.makedirs(self.packs_dir, exist_ok=True)

    def _get_pack_dir(self, pack_id: str) -> str:
        return os.path.join(self.packs_dir, pack_id)

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

        # The template imports BaseRecitePlugin
        # When loaded dynamically, we will inject 'core.base_plugin' into sys.modules
        # so this import will resolve correctly.
        plugin_code = """from core.base_plugin import BaseRecitePlugin

class Plugin(BaseRecitePlugin):
    def load_data(self):
        # TODO: Load your static data here from self.workspace_dir
        self.problems = ["1", "2"]

    def get_all_problem_ids(self) -> list[str]:
        return self.problems

    def render_statement(self, problem_id: str) -> str:
        return f"This is problem {problem_id}"

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        return user_input.strip() == problem_id

    def get_expected_display(self, problem_id: str) -> str:
        return problem_id
"""
        with open(os.path.join(pack_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write(plugin_code)

        print(f"✅ Template created at {pack_dir}")

    def import_pack(self, source_path: str) -> str:
        """Import a pack from a directory or zip file."""
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Path not found: {source_path}")

        temp_dir = os.path.join(self.packs_dir, ".temp_import")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        if os.path.isdir(source_path):
            shutil.copytree(source_path, temp_dir)
        elif zipfile.is_zipfile(source_path):
            with zipfile.ZipFile(source_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
        else:
            raise ValueError(
                "Unsupported file format. Must be a directory or zip file."
            )

        # Find manifest.json
        manifest_path = os.path.join(temp_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            shutil.rmtree(temp_dir)
            raise FileNotFoundError("manifest.json not found in the package.")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        pack_id = manifest.get("id")
        if not pack_id:
            shutil.rmtree(temp_dir)
            raise ValueError("Invalid manifest: missing 'id'")

        target_dir = self._get_pack_dir(pack_id)
        if os.path.exists(target_dir):
            print(f"🔄 Updating existing pack: {pack_id}")
            shutil.rmtree(target_dir)

        shutil.move(temp_dir, target_dir)
        print(f"✅ Successfully imported pack '{pack_id}'")
        return pack_id

    def load_plugin(self, pack_id: str) -> BaseRecitePlugin:
        """Dynamically load the plugin.py from the pack_id directory."""
        pack_dir = self._get_pack_dir(pack_id)
        if not os.path.exists(pack_dir):
            raise FileNotFoundError(f"Pack '{pack_id}' not found.")

        plugin_path = os.path.join(pack_dir, "plugin.py")
        if not os.path.exists(plugin_path):
            raise FileNotFoundError(f"plugin.py not found in {pack_id}.")

        # To allow plugins to easily import BaseRecitePlugin without knowing the exact package path,
        # we will alias our internal 'muninn.core' to just 'core' for the plugin's namespace if needed.
        # Actually, adding our 'src' directory to sys.path temporarily is an easy way.
        src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        sys.path.insert(0, src_dir)

        try:
            spec = importlib.util.spec_from_file_location(
                f"muninn.plugins.{pack_id}", plugin_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find the class that inherits from BaseRecitePlugin
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseRecitePlugin)
                    and attr is not BaseRecitePlugin
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
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                    packs.append(manifest)
        return packs
