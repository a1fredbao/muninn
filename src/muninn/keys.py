"""Stable opaque keys used in persisted configuration and progress data."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def _digest(prefix: str, parts: Iterable[object], *, length: int = 24) -> str:
    digest = hashlib.sha256()
    digest.update(prefix.encode("utf-8"))
    for part in parts:
        encoded = str(part).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return f"{prefix}_{digest.hexdigest()[:length]}"


def pack_key(pack_id: str) -> str:
    return _digest("pack", (pack_id,))


def question_type_key(pack_id: str, question_type_id: str) -> str:
    return _digest("type", (pack_id, question_type_id))


def problem_key(
    pack_id: str,
    question_type_id: str,
    problem_id: str,
) -> str:
    return _digest(
        "problem",
        (pack_id, question_type_id, problem_id),
        length=32,
    )
