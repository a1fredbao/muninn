"""Isolated plugin process.

The worker keeps a plugin and its dependencies inside one process while the
host communicates through newline-delimited JSON messages.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

from .. import plugin_api
from ..plugin_api import PluginContext


def _load_plugin(
    *,
    pack_id: str,
    pack_dir: str,
    entrypoint: str,
) -> plugin_api.Plugin:
    module_name, separator, class_name = entrypoint.partition(":")
    if not separator or not module_name or not class_name:
        raise ValueError("entrypoint must use 'module:ClassName'")

    pack_path = Path(pack_dir).resolve()
    sys.path.insert(0, str(pack_path))
    module = importlib.import_module(module_name)

    plugin_class = getattr(module, class_name)
    if not isinstance(plugin_class, type):
        raise TypeError(f"Plugin entrypoint '{entrypoint}' is not a class")

    signature = inspect.signature(plugin_class)
    constructor_args: dict[str, str] = {}
    if "workspace_dir" in signature.parameters:
        constructor_args["workspace_dir"] = str(pack_path)
    if "pack_id" in signature.parameters:
        constructor_args["pack_id"] = pack_id
    plugin = plugin_class(**constructor_args)

    context = PluginContext(
        pack_id=pack_id,
        pack_dir=pack_path,
        workspace_dir=pack_path,
    )
    initialize = getattr(plugin, "initialize", None)
    if initialize is not None:
        result = initialize(context)
        if inspect.isawaitable(result):
            asyncio.run(result)
    return plugin


def _run_maybe_async(result: Any) -> Any:
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def _dispatch(
    plugin: plugin_api.Plugin,
    method: str,
    params: dict[str, Any],
) -> Any:
    if method == "get_all_problem_ids":
        result = _run_maybe_async(plugin.get_all_problem_ids())
        return [str(problem_id) for problem_id in result]
    if method == "render_statement":
        return str(_run_maybe_async(plugin.render_statement(params["problem_id"])))
    if method == "check_answer":
        return bool(
            _run_maybe_async(
                plugin.check_answer(params["problem_id"], params["user_input"])
            )
        )
    if method == "get_expected_display":
        return str(_run_maybe_async(plugin.get_expected_display(params["problem_id"])))
    if method == "get_expand_info":
        result = _run_maybe_async(plugin.get_expand_info(params["problem_id"]))
        return "" if result is None else str(result)
    if method == "get_legacy_problem_id_map":
        getter = getattr(plugin, "get_legacy_problem_id_map", None)
        return _run_maybe_async(getter()) if getter is not None else {}
    raise ValueError(f"Unknown plugin method: {method}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--pack-dir", required=True)
    parser.add_argument("--entrypoint", required=True)
    args = parser.parse_args()

    protocol = os.fdopen(
        os.dup(sys.stdout.fileno()),
        "w",
        buffering=1,
        encoding="utf-8",
    )
    sys.stdout = sys.stderr

    def send(payload: dict[str, Any]) -> None:
        protocol.write(json.dumps(payload, ensure_ascii=False) + "\n")
        protocol.flush()

    try:
        plugin = _load_plugin(
            pack_id=args.pack_id,
            pack_dir=args.pack_dir,
            entrypoint=args.entrypoint,
        )
    except Exception as exc:
        payload = {
            "id": None,
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        send(payload)
        raise SystemExit(1) from exc

    send({"id": None, "ok": True, "method": "ready"})
    try:
        for line in sys.stdin:
            request: dict[str, Any] = json.loads(line)
            request_id = request.get("id")
            try:
                result = _dispatch(
                    plugin,
                    str(request["method"]),
                    dict(request.get("params") or {}),
                )
                response = {"id": request_id, "ok": True, "result": result}
            except Exception as exc:  # noqa: BLE001
                response = {
                    "id": request_id,
                    "ok": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            send(response)
    finally:
        close = getattr(plugin, "close", None)
        if close is not None:
            _run_maybe_async(close())
        protocol.close()


if __name__ == "__main__":
    main()
