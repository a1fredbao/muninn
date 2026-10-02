"""Shared domain types used across the application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NewType

ProblemId = NewType("ProblemId", str)
PackKey = NewType("PackKey", str)
QuestionTypeKey = NewType("QuestionTypeKey", str)


@dataclass(frozen=True, slots=True)
class ProblemRef:
    """A problem uniquely identified across packs and question types."""

    key: ProblemId
    pack_id: str
    pack_key: PackKey
    question_type_id: str
    question_type_key: QuestionTypeKey
    local_problem_id: str


@dataclass(frozen=True, slots=True)
class ProblemMetadata:
    """Optional scheduling metadata supplied by a question type."""

    tags: tuple[str, ...] = ()
    difficulty: float | None = None
    estimated_seconds: float | None = None
    data: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProblemStats:
    """Persistent statistics for one problem."""

    ac_count: int = 0
    total_count: int = 0
    total_ac_time: float = 0.0

    @property
    def accuracy(self) -> float:
        return self.ac_count / self.total_count if self.total_count else 0.0

    @property
    def average_ac_time(self) -> float:
        return self.total_ac_time / self.ac_count if self.ac_count else 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "ac_count": self.ac_count,
            "total_count": self.total_count,
            "total_ac_time": self.total_ac_time,
        }


@dataclass(frozen=True, slots=True)
class SchedulingContext:
    """Stable context supplied to a scheduling policy."""

    selection_weight: float
    metadata: ProblemMetadata


@dataclass(frozen=True, slots=True)
class SchedulingCandidate:
    """A scheduler candidate composed from host and plugin-owned data."""

    problem: ProblemRef
    stats: ProblemStats
    context: SchedulingContext


@dataclass(frozen=True, slots=True)
class GroupSelection:
    """One selected question type inside a training group."""

    pack_key: PackKey
    question_type_key: QuestionTypeKey
    weight: float = 1.0
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class TrainingGroup:
    """A persisted, named collection of question types."""

    id: str
    name: str
    selections: tuple[GroupSelection, ...] = ()


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """The durable result of one answer attempt."""

    problem_id: ProblemId
    user_input: str
    is_correct: bool
    time_spent: float


@dataclass(frozen=True, slots=True)
class AttemptResult:
    """The attempt outcome and persisted state after recording it."""

    outcome: AttemptOutcome
    stats: ProblemStats


@dataclass(frozen=True, slots=True)
class ProgressAggregate:
    """Aggregate progress for the active problems in a session."""

    distinct_ac: int
    ac_count: int
    total_count: int
    total_ac_time: float

    @property
    def accuracy(self) -> float:
        return self.ac_count / self.total_count if self.total_count else 0.0

    @property
    def average_ac_time(self) -> float:
        return self.total_ac_time / self.ac_count if self.ac_count else 0.0
