from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from services.selector.app.core.db import GenerationRecord, ValidationRecord
from services.selector.app.core.pipeline import (
    EvaluationEvidence,
    EvidenceState,
    ExecutionEvidence,
    PipelineError,
    SelectorPipeline,
)
from services.selector.app.core.schemas import (
    DecisionStatus,
    RunCounters,
    RunRecord,
    RunStatus,
    TaskRecord,
    TaskStatus,
)


class MemoryRepository:
    def __init__(self, model_type: str, *, resumable: bool = False) -> None:
        self.model_type = model_type
        self.run: RunRecord | None = None
        self.tasks: dict[str, TaskRecord] = {}
        self.generations: dict[str, GenerationRecord] = {}
        self.validations: dict[str, ValidationRecord] = {}
        self.states: dict[str, EvidenceState] = {}
        self.created_runs = 0
        self.accepted = 0
        self.rejected = 0
        self.failed = 0
        if resumable:
            self.run = self._run("run-resume", RunStatus.RUNNING, total=1)

    @staticmethod
    def _run(run_id: str, status: RunStatus, *, total: int) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            status=status,
            model_id="model",
            dataset_id="dataset",
            config_id="config",
            counters=RunCounters(total=total),
        )

    def get_model_type(self, model_id: str) -> str | None:
        return self.model_type

    def find_resumable_run(self, **values: Any) -> RunRecord | None:
        return self.run

    def create_run(self, *, total_items: int, **values: Any) -> RunRecord:
        self.created_runs += 1
        self.run = self._run("run-new", RunStatus.CREATED, total=total_items)
        return self.run

    def load_run(self, run_id: str) -> RunRecord:
        assert self.run is not None and self.run.run_id == run_id
        return self.run

    def create_task_once(
        self, *, run_id: str, source_id: str, task_type: str, input_payload, metadata
    ) -> TaskRecord:
        task_id = f"task-{source_id}"
        if task_id not in self.tasks:
            self.tasks[task_id] = TaskRecord(
                task_id=task_id,
                run_id=run_id,
                task_type=task_type,
                status=TaskStatus.PENDING,
                input_payload=dict(input_payload),
                metadata=dict(metadata),
            )
            self.states[task_id] = EvidenceState()
        return self.tasks[task_id]

    def transition_run(self, run_id: str, target: RunStatus) -> RunStatus:
        assert self.run is not None
        self.run = self.run.model_copy(update={"status": target})
        return target

    def transition_task(self, task_id: str, target: TaskStatus) -> TaskStatus:
        self.tasks[task_id] = self.tasks[task_id].model_copy(update={"status": target})
        return target

    def list_resume_items(self, run_id: str):
        return tuple(
            SimpleNamespace(task=task, evidence=self.states[task_id])
            for task_id, task in self.tasks.items()
            if task.status not in {TaskStatus.ACCEPTED, TaskStatus.REJECTED, TaskStatus.FAILED}
        )

    def create_generation_once(self, *, task_id: str, run_id: str, model_id: str, **values):
        generation = GenerationRecord(
            generation_id=f"generation-{task_id}",
            task_id=task_id,
            run_id=run_id,
            model_id=model_id,
            raw_output=values["raw_output"],
            parsed_output=values["parsed_output"],
            latency_ms=values["latency_ms"],
            metadata=values["metadata"],
        )
        self.generations[generation.generation_id] = generation
        self.states[task_id] = EvidenceState(generation_id=generation.generation_id)
        return generation

    def load_generation(self, generation_id: str) -> GenerationRecord:
        return self.generations[generation_id]

    def create_validation_once(self, *, generation_id: str, is_valid: bool, **values):
        validation = ValidationRecord(
            validation_id=f"validation-{generation_id}",
            generation_id=generation_id,
            is_valid=is_valid,
            score=values["score"],
            failure_code=values["failure_code"],
            failure_reason=values["failure_reason"],
            details=values["details"],
        )
        self.validations[validation.validation_id] = validation
        task_id = self.generations[generation_id].task_id
        self.states[task_id] = EvidenceState(
            generation_id=generation_id, validation_id=validation.validation_id
        )
        return validation

    def load_validation(self, validation_id: str) -> ValidationRecord:
        return self.validations[validation_id]

    def finalize_task_once(self, *, task_id: str, status: str, **values):
        target = TaskStatus(status)
        self.tasks[task_id] = self.tasks[task_id].model_copy(update={"status": target})
        self.accepted += status == "accepted"
        self.rejected += status == "rejected"
        assert self.run is not None
        self.run = self.run.model_copy(
            update={
                "counters": self.run.counters.model_copy(
                    update={
                        "processed": self.run.counters.processed + 1,
                        "accepted": self.run.counters.accepted + (status == "accepted"),
                        "rejected": self.run.counters.rejected + (status == "rejected"),
                    }
                )
            }
        )

    def fail_task_once(self, *, task_id: str, run_id: str) -> None:
        self.tasks[task_id] = self.tasks[task_id].model_copy(update={"status": TaskStatus.FAILED})
        self.failed += 1


@dataclass
class FakeBranch:
    branch_id: str
    accepted: bool
    fail_execution: bool = False
    model_id: str = "model"
    dataset_id: str = "dataset"
    config_id: str = "config"
    selector_version: str = "selector_v001"
    task_type: str = "fixture"
    execute_calls: int = 0
    evaluate_calls: int = 0
    auxiliary_calls: int = 0

    def source_items(self):
        return (("source", {"value": self.branch_id}),)

    def execute(self, task: TaskRecord) -> ExecutionEvidence:
        self.execute_calls += 1
        if self.fail_execution:
            raise RuntimeError("fixture failure")
        return ExecutionEvidence("raw", {"value": 1}, "completion")

    def evaluate(self, task: TaskRecord, execution: GenerationRecord) -> EvaluationEvidence:
        self.evaluate_calls += 1
        return EvaluationEvidence(
            decision_status=(DecisionStatus.ACCEPTED if self.accepted else DecisionStatus.REJECTED),
            output_payload={"value": 1},
            evidence=({"check_id": self.branch_id, "passed": self.accepted},),
            completion=execution.raw_output,
            failure_code=None if self.accepted else "rejected",
            failure_reason=None if self.accepted else "fixture rejection",
        )

    def persist_auxiliary(self, repository, generation_id: str, result) -> None:
        self.auxiliary_calls += 1


@pytest.mark.parametrize("branch_id", ["llm", "ml"])
@pytest.mark.parametrize("accepted", [True, False])
def test_branches_accept_and_reject_independently(branch_id: str, accepted: bool) -> None:
    repository = MemoryRepository(branch_id)
    branch = FakeBranch(branch_id, accepted)

    result = SelectorPipeline(repository).run(branch)

    assert repository.run is not None and repository.run.status is RunStatus.COMPLETED
    assert (repository.accepted, repository.rejected) == ((1, 0) if accepted else (0, 1))
    assert branch.execute_calls == branch.evaluate_calls == branch.auxiliary_calls == 1
    assert result.status is RunStatus.COMPLETED
    assert result.counters.processed == 1


@pytest.mark.parametrize("branch_id", ["llm", "ml"])
def test_branches_resume_from_persisted_generation(branch_id: str) -> None:
    repository = MemoryRepository(branch_id, resumable=True)
    branch = FakeBranch(branch_id, True)
    task = repository.create_task_once(
        run_id="run-resume",
        source_id="source",
        task_type="fixture",
        input_payload={"value": branch_id},
        metadata={"source_id": "source"},
    )
    repository.transition_task(task.task_id, TaskStatus.GENERATING)
    repository.create_generation_once(
        task_id=task.task_id,
        run_id="run-resume",
        model_id="model",
        raw_output="persisted",
        parsed_output={"value": 1},
        latency_ms=1,
        metadata={},
    )
    repository.transition_task(task.task_id, TaskStatus.VALIDATING)

    SelectorPipeline(repository).run(branch)

    assert branch.execute_calls == 0
    assert branch.evaluate_calls == branch.auxiliary_calls == 1
    assert repository.accepted == 1


def test_wrong_model_type_fails_before_run_creation() -> None:
    repository = MemoryRepository("ml")

    with pytest.raises(PipelineError, match="Model type mismatch"):
        SelectorPipeline(repository).run(FakeBranch("llm", True))

    assert repository.created_runs == 0
    assert repository.tasks == {}


def test_partial_failure_is_counted_and_run_is_not_reported_as_success() -> None:
    repository = MemoryRepository("ml")

    with pytest.raises(PipelineError, match="failed for 1 item"):
        SelectorPipeline(repository).run(FakeBranch("ml", True, fail_execution=True))

    assert repository.failed == 1
    assert repository.run is not None and repository.run.status is RunStatus.FAILED
