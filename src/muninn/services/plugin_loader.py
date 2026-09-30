"""Plugin discovery and host-side adapters."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain import ProblemMetadata, ProblemRef
from ..plugin_api import (
    Plugin,
    PluginContext,
    QuestionTypeDescriptor,
    coerce_problem_metadata,
)
from .dependency import DependencyEnvironment
from .manifest import ManifestError, PackManifest, validate_pack_id

PLUGIN_CALL_TIMEOUT = 30.0


class PluginProtocolError(RuntimeError):
    """Raised when a plugin worker violates the host protocol."""


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    """Everything needed to start one isolated plugin process."""

    pack_id: str
    pack_dir: Path
    manifest: PackManifest
    entrypoint: str
    environment: dict[str, str]


class PluginLoader:
    def __init__(
        self,
        packs_dir: str | None = None,
        dependency_environment: DependencyEnvironment | None = None,
    ) -> None:
        self.packs_dir = Path(packs_dir or os.path.expanduser("~/.muninn/packs"))
        self.dependencies = dependency_environment or DependencyEnvironment()

    def load(self, pack_id: str) -> LoadedPlugin:
        validate_pack_id(pack_id)
        pack_dir = self.packs_dir / pack_id
        if not pack_dir.is_dir():
            raise FileNotFoundError(f"Pack '{pack_id}' not found.")

        manifest_path = pack_dir / "manifest.json"
        try:
            manifest = PackManifest.from_path(manifest_path)
        except ManifestError as exc:
            raise PluginProtocolError(str(exc)) from exc

        environment = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[2])
        python_paths: list[str] = [package_root]
        versioned_site = self.dependencies.get_site_packages(
            pack_id,
            manifest.version,
        )
        if os.path.isdir(versioned_site):
            python_paths.append(versioned_site)
        legacy_site = self.dependencies.get_site_packages(pack_id)
        if os.path.isdir(legacy_site) and legacy_site != versioned_site:
            python_paths.append(legacy_site)
        if python_paths:
            existing = environment.get("PYTHONPATH")
            if existing:
                python_paths.append(existing)
            environment["PYTHONPATH"] = os.pathsep.join(python_paths)

        return LoadedPlugin(
            pack_id=pack_id,
            pack_dir=pack_dir,
            manifest=manifest,
            entrypoint=manifest.entrypoint,
            environment=environment,
        )

    async def create_adapter(self, loaded: LoadedPlugin) -> WorkerPluginAdapter:
        return await WorkerPluginAdapter.start(loaded)

    def create_in_process_adapter(
        self,
        loaded: LoadedPlugin,
        plugin: Plugin,
    ) -> InProcessPluginAdapter:
        return InProcessPluginAdapter(loaded, plugin)


class WorkerPluginAdapter:
    """Normalize worker communication behind the plugin interface."""

    def __init__(
        self,
        loaded: LoadedPlugin,
        process: asyncio.subprocess.Process,
    ) -> None:
        self.loaded = loaded
        self.process = process
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._closed = False
        self._stderr_lines: list[str] = []
        self._stderr_task: asyncio.Task[None] | None = None

    @classmethod
    async def start(cls, loaded: LoadedPlugin) -> WorkerPluginAdapter:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "muninn.services.plugin_worker",
            "--pack-id",
            loaded.pack_id,
            "--pack-dir",
            str(loaded.pack_dir),
            "--entrypoint",
            loaded.entrypoint,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=loaded.environment,
        )
        adapter = cls(loaded, process)
        adapter._stderr_task = asyncio.create_task(adapter._drain_stderr())
        try:
            ready = await adapter._read_message(timeout=PLUGIN_CALL_TIMEOUT)
        except Exception:
            await adapter.aclose()
            raise
        if ready is None or not ready.get("ok"):
            error = (ready or {}).get("error") or {}
            await adapter.aclose()
            stderr = "\n".join(adapter._stderr_lines[-20:]).strip()
            detail = error.get("message") or stderr or "Plugin worker failed to start."
            raise PluginProtocolError(detail)
        return adapter

    async def _drain_stderr(self) -> None:
        if self.process.stderr is None:
            return
        while line := await self.process.stderr.readline():
            self._stderr_lines.append(line.decode(errors="replace").rstrip())
            if len(self._stderr_lines) > 100:
                del self._stderr_lines[:50]

    async def _read_message(
        self,
        *,
        timeout: float,
    ) -> dict[str, Any] | None:
        if self.process.stdout is None:
            raise PluginProtocolError("Plugin worker stdout is unavailable.")
        try:
            line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise PluginProtocolError(
                f"Plugin worker did not respond within {timeout:.0f} seconds."
            ) from exc
        if not line:
            return None
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PluginProtocolError("Plugin worker returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise PluginProtocolError("Plugin worker response must be an object.")
        return payload

    async def _request(self, method: str, **params: Any) -> Any:
        if self._closed:
            raise PluginProtocolError("Plugin worker is closed.")
        async with self._lock:
            self._request_id += 1
            request_id = self._request_id
            if self.process.stdin is None:
                raise PluginProtocolError("Plugin worker stdin is unavailable.")
            request = {
                "id": request_id,
                "method": method,
                "params": params,
            }
            self.process.stdin.write(
                (json.dumps(request, ensure_ascii=False) + "\n").encode()
            )
            await self.process.stdin.drain()
            response = await self._read_message(timeout=PLUGIN_CALL_TIMEOUT)
            if response is None:
                code = self.process.returncode
                raise PluginProtocolError(
                    f"Plugin worker exited before responding (code {code})."
                )
            if response.get("id") != request_id:
                raise PluginProtocolError(
                    "Plugin worker returned a response for the wrong request."
                )
            if not response.get("ok"):
                error = response.get("error") or {}
                error_type = error.get("type") or "PluginError"
                message = error.get("message") or "Unknown plugin error."
                raise PluginProtocolError(f"{error_type}: {message}")
            return response.get("result")

    async def list_question_types(self) -> list[QuestionTypeDescriptor]:
        result = await self._request("list_question_types")
        return [
            QuestionTypeDescriptor(
                key=str(item["key"]),
                label=str(item.get("label") or item["key"]),
                description=str(item.get("description") or ""),
                problem_count=int(item.get("problem_count") or 0),
            )
            for item in result
        ]

    async def get_all_problem_ids(self, problem: ProblemRef) -> list[str]:
        result = await self._request(
            "get_all_problem_ids",
            question_type=problem.question_type_id,
        )
        return [str(problem_id) for problem_id in result]

    async def describe_problem(self, problem: ProblemRef) -> ProblemMetadata:
        result = await self._request(
            "describe_problem",
            question_type=problem.question_type_id,
            problem_id=problem.local_problem_id,
        )
        return coerce_problem_metadata(result)

    async def render_statement(self, problem: ProblemRef) -> str:
        return str(
            await self._request(
                "render_statement",
                question_type=problem.question_type_id,
                problem_id=problem.local_problem_id,
            )
        )

    async def check_answer(self, problem: ProblemRef, user_input: str) -> bool:
        return bool(
            await self._request(
                "check_answer",
                question_type=problem.question_type_id,
                problem_id=problem.local_problem_id,
                user_input=user_input,
            )
        )

    async def get_expected_display(self, problem: ProblemRef) -> str:
        return str(
            await self._request(
                "get_expected_display",
                question_type=problem.question_type_id,
                problem_id=problem.local_problem_id,
            )
        )

    async def get_expand_info(self, problem: ProblemRef) -> str:
        result = await self._request(
            "get_expand_info",
            question_type=problem.question_type_id,
            problem_id=problem.local_problem_id,
        )
        return "" if result is None else str(result)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process.returncode is None:
            self.process.terminate()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._stderr_task is not None:
            await self._stderr_task


class InProcessPluginAdapter:
    """Adapter for tests and explicitly in-process integrations."""

    def __init__(self, loaded: LoadedPlugin, plugin: Plugin) -> None:
        self.loaded = loaded
        self.plugin = plugin
        self._closed = False
        initialize = getattr(plugin, "initialize", None)
        if initialize is not None:
            initialize(
                PluginContext(
                    pack_id=loaded.pack_id,
                    pack_dir=loaded.pack_dir,
                    workspace_dir=loaded.pack_dir,
                )
            )
        question_types = plugin.get_question_types()
        if inspect.isawaitable(question_types):
            raise TypeError(
                "InProcessPluginAdapter cannot await get_question_types in "
                "its constructor; use WorkerPluginAdapter for async plugins."
            )
        self._question_types = {
            question_type.key: question_type for question_type in question_types
        }

    @staticmethod
    async def _invoke(callable_obj: Any, *args: Any) -> Any:
        if inspect.iscoroutinefunction(callable_obj):
            return await callable_obj(*args)
        result = await asyncio.to_thread(callable_obj, *args)
        if inspect.isawaitable(result):
            return await result
        return result

    def _question_type(self, problem: ProblemRef):
        try:
            return self._question_types[problem.question_type_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown question type: {problem.question_type_id!r}"
            ) from exc

    async def list_question_types(self) -> list[QuestionTypeDescriptor]:
        descriptors: list[QuestionTypeDescriptor] = []
        for question_type in self._question_types.values():
            problem_ids = await self._invoke(question_type.get_all_problem_ids)
            descriptors.append(
                QuestionTypeDescriptor(
                    key=question_type.key,
                    label=question_type.label,
                    description=question_type.description,
                    problem_count=len(problem_ids),
                )
            )
        return descriptors

    async def get_all_problem_ids(self, problem: ProblemRef) -> list[str]:
        question_type = self._question_type(problem)
        result = await self._invoke(question_type.get_all_problem_ids)
        return [str(problem_id) for problem_id in result]

    async def describe_problem(self, problem: ProblemRef) -> ProblemMetadata:
        question_type = self._question_type(problem)
        result = await self._invoke(
            question_type.describe_problem,
            problem.local_problem_id,
        )
        return coerce_problem_metadata(result)

    async def render_statement(self, problem: ProblemRef) -> str:
        question_type = self._question_type(problem)
        return str(
            await self._invoke(
                question_type.render_statement,
                problem.local_problem_id,
            )
        )

    async def check_answer(self, problem: ProblemRef, user_input: str) -> bool:
        question_type = self._question_type(problem)
        return bool(
            await self._invoke(
                question_type.check_answer,
                problem.local_problem_id,
                user_input,
            )
        )

    async def get_expected_display(self, problem: ProblemRef) -> str:
        question_type = self._question_type(problem)
        return str(
            await self._invoke(
                question_type.get_expected_display,
                problem.local_problem_id,
            )
        )

    async def get_expand_info(self, problem: ProblemRef) -> str:
        question_type = self._question_type(problem)
        result = await self._invoke(
            question_type.get_expand_info,
            problem.local_problem_id,
        )
        return "" if result is None else str(result)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self.plugin, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                asyncio.run(result)
