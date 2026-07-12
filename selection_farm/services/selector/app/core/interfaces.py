"""Branch-neutral protocols used by Core orchestration."""

from typing import Protocol, runtime_checkable

from .schemas import SelectionDecision, TaskRecord


@runtime_checkable
class SelectorBranch(Protocol):
    @property
    def branch_id(self) -> str: ...

    def evaluate(self, task: TaskRecord) -> SelectionDecision: ...
