"""Structured package-operation results and progress types."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class PackageProgress:
    """A user-facing progress update emitted by package operations."""

    message: str


class OperationCancelled(RuntimeError):
    """Raised when a cooperative cancellation request is observed."""


class CancellationToken:
    """Thread-safe cooperative cancellation primitive."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelled("Operation cancelled.")


@dataclass(frozen=True, slots=True)
class OperationResult[T]:
    """Consistent result shape for expected package-operation outcomes."""

    status: Literal["ok", "failed", "cancelled"]
    value: T | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @classmethod
    def success(cls, value: T) -> OperationResult[T]:
        return cls(status="ok", value=value)

    @classmethod
    def failure(cls, error: str) -> OperationResult[T]:
        return cls(status="failed", error=error)

    @classmethod
    def cancelled(cls) -> OperationResult[T]:
        return cls(status="cancelled", error="Operation cancelled.")


@dataclass(frozen=True, slots=True)
class UpgradeResult:
    """Structured result for one package upgrade."""

    pack_id: str
    status: str
    current_version: str | None = None
    remote_version: str | None = None
    error: str | None = None

    @property
    def upgraded(self) -> bool:
        return self.status == "upgraded"

    @property
    def failed(self) -> bool:
        return self.status == "failed"


ProgressCallback = Callable[[PackageProgress], None]


def emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(PackageProgress(message))
