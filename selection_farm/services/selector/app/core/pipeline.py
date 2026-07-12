"""Branch-neutral lifecycle, orchestration, and resume handling."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .schemas import (
    CoreError,
    DecisionStatus,
    ErrorCode,
    RunRecord,
    RunStatus,
    TaskRecord,
    TaskStatus,
)

RUN_TRANSITIONS = {
    RunStatus.CREATED: frozenset({RunStatus.RUNNING, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
}
TASK_TRANSITIONS = {
    TaskStatus.PENDING: frozenset({TaskStatus.GENERATING, TaskStatus.FAILED}),
    TaskStatus.GENERATING: frozenset({TaskStatus.VALIDATING, TaskStatus.FAILED}),
    TaskStatus.VALIDATING: frozenset({TaskStatus.ACCEPTED, TaskStatus.REJECTED, TaskStatus.FAILED}),
    TaskStatus.ACCEPTED: frozenset(),
    TaskStatus.REJECTED: frozenset(),
    TaskStatus.FAILED: frozenset(),
}


class LifecycleError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PERSISTENCE, message)


class PipelineError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.EXECUTION, message)


class ResumeStage(StrEnum):
    EXECUTE = "execute"
    VALIDATE = "validate"
    FINALIZE = "finalize"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class EvidenceState:
    generation_id: str | None = None
    validation_id: str | None = None
    sample_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    raw_output: str
    output_payload: Mapping[str, Any] | None
    completion: str
    latency_ms: int | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EvaluationEvidence:
    decision_status: DecisionStatus
    output_payload: Mapping[str, Any] | None
    evidence: tuple[Mapping[str, Any], ...]
    completion: str
    score: float | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    metadata: Mapping[str, Any] | None = None


class PipelineRepository(Protocol):
    def get_model_type(self, model_id: str) -> str | None: ...

    def find_resumable_run(
        self, *, model_id: str, dataset_id: str, config_id: str
    ) -> RunRecord | None: ...

    def create_run(self, **values: Any) -> RunRecord: ...

    def load_run(self, run_id: str) -> RunRecord: ...

    def create_task_once(self, **values: Any) -> TaskRecord: ...

    def transition_run(self, run_id: str, target: RunStatus) -> RunStatus: ...

    def transition_task(self, task_id: str, target: TaskStatus) -> TaskStatus: ...

    def list_resume_items(self, run_id: str) -> tuple[Any, ...]: ...

    def create_generation_once(self, **values: Any) -> Any: ...

    def load_generation(self, generation_id: str) -> Any: ...

    def create_validation_once(self, **values: Any) -> Any: ...

    def load_validation(self, validation_id: str) -> Any: ...

    def finalize_task_once(self, **values: Any) -> Any: ...

    def fail_task_once(self, *, task_id: str, run_id: str) -> None: ...


class PipelineBranch(Protocol):
    branch_id: str
    model_id: str
    dataset_id: str
    config_id: str
    selector_version: str
    task_type: str

    def source_items(self) -> tuple[tuple[str, Mapping[str, Any]], ...]: ...

    def execute(self, task: TaskRecord) -> Any: ...

    def evaluate(self, task: TaskRecord, execution: Any) -> Any: ...

    def persist_auxiliary(self, repository: Any, generation_id: str, result: Any) -> None: ...


def ensure_run_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in RUN_TRANSITIONS[current]:
        raise LifecycleError(f"Illegal run transition: {current.value} -> {target.value}")


def ensure_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if target not in TASK_TRANSITIONS[current]:
        raise LifecycleError(f"Illegal task transition: {current.value} -> {target.value}")


def resume_stage(evidence: EvidenceState) -> ResumeStage:
    if evidence.sample_id is not None:
        return ResumeStage.COMPLETE
    if evidence.validation_id is not None:
        return ResumeStage.FINALIZE
    if evidence.generation_id is not None:
        return ResumeStage.VALIDATE
    return ResumeStage.EXECUTE


class SelectorPipeline:
    """Execute one injected branch and persist each durable checkpoint."""

    def __init__(self, repository: PipelineRepository) -> None:
        self.repository = repository

    def run(self, branch: PipelineBranch) -> RunRecord:
        items = branch.source_items()
        actual_type = self.repository.get_model_type(branch.model_id)
        if actual_type != branch.branch_id:
            raise PipelineError(
                f"Model type mismatch: expected {branch.branch_id}, got {actual_type or 'missing'}"
            )

        run = self.repository.find_resumable_run(
            model_id=branch.model_id,
            dataset_id=branch.dataset_id,
            config_id=branch.config_id,
        )
        if run is None:
            run = self.repository.create_run(
                model_id=branch.model_id,
                dataset_id=branch.dataset_id,
                config_id=branch.config_id,
                total_items=len(items),
                metadata={"branch_id": branch.branch_id},
            )
        elif run.counters.total != len(items):
            raise PipelineError("Resumable run item count does not match the configured source")
        for source_id, payload in items:
            self.repository.create_task_once(
                run_id=run.run_id,
                source_id=source_id,
                task_type=branch.task_type,
                input_payload=payload,
                metadata={"source_id": source_id, "branch_id": branch.branch_id},
            )
        if run.status is RunStatus.CREATED:
            self.repository.transition_run(run.run_id, RunStatus.RUNNING)

        failures = 0
        for item in self.repository.list_resume_items(run.run_id):
            try:
                self._process(branch, run, item.task, item.evidence)
            except Exception:
                failures += 1
                self.repository.fail_task_once(task_id=item.task.task_id, run_id=run.run_id)

        if failures:
            self.repository.transition_run(run.run_id, RunStatus.FAILED)
            raise PipelineError(f"Selector run {run.run_id} failed for {failures} item(s)")
        self.repository.transition_run(run.run_id, RunStatus.COMPLETED)
        return self.repository.load_run(run.run_id)

    def _process(
        self,
        branch: PipelineBranch,
        run: RunRecord,
        task: TaskRecord,
        state: EvidenceState,
    ) -> None:
        stage = resume_stage(state)
        generation_id = state.generation_id
        validation_id = state.validation_id

        if (
            stage in {ResumeStage.VALIDATE, ResumeStage.FINALIZE, ResumeStage.COMPLETE}
            and task.status is TaskStatus.GENERATING
        ):
            self.repository.transition_task(task.task_id, TaskStatus.VALIDATING)
        if stage is ResumeStage.COMPLETE:
            stage = ResumeStage.FINALIZE

        if stage is ResumeStage.EXECUTE:
            if task.status is TaskStatus.PENDING:
                self.repository.transition_task(task.task_id, TaskStatus.GENERATING)
            execution: ExecutionEvidence = branch.execute(task)
            generation = self.repository.create_generation_once(
                task_id=task.task_id,
                run_id=run.run_id,
                model_id=branch.model_id,
                raw_output=execution.raw_output,
                parsed_output=execution.output_payload,
                latency_ms=execution.latency_ms,
                metadata=execution.metadata,
            )
            generation_id = generation.generation_id
            self.repository.transition_task(task.task_id, TaskStatus.VALIDATING)
            stage = ResumeStage.VALIDATE

        if stage is ResumeStage.VALIDATE:
            assert generation_id is not None
            generation = self.repository.load_generation(generation_id)
            result: EvaluationEvidence = branch.evaluate(task, generation)
            branch.persist_auxiliary(self.repository, generation_id, result)
            validation = self.repository.create_validation_once(
                generation_id=generation_id,
                validator_version=branch.selector_version,
                is_valid=result.decision_status is DecisionStatus.ACCEPTED,
                score=result.score,
                failure_code=result.failure_code,
                failure_reason=result.failure_reason,
                details={
                    "decision_status": result.decision_status.value,
                    "output_payload": result.output_payload,
                    "evidence": list(result.evidence),
                    "completion": result.completion,
                    "metadata": dict(result.metadata or {}),
                },
            )
            validation_id = validation.validation_id
            stage = ResumeStage.FINALIZE

        if stage is ResumeStage.FINALIZE:
            assert generation_id is not None and validation_id is not None
            validation = self.repository.load_validation(validation_id)
            details = validation.details
            if details is None:
                raise PipelineError("Persisted validation details are missing")
            status = DecisionStatus(details["decision_status"])
            if status not in {DecisionStatus.ACCEPTED, DecisionStatus.REJECTED}:
                raise PipelineError("A failed decision cannot be finalized as a sample")
            self.repository.finalize_task_once(
                validation_id=validation_id,
                task_id=task.task_id,
                generation_id=generation_id,
                run_id=run.run_id,
                model_id=branch.model_id,
                dataset_id=branch.dataset_id,
                status=status.value,
                completion=details["completion"],
                selector_version=branch.selector_version,
                score=validation.score,
                failure_code=validation.failure_code,
                failure_reason=validation.failure_reason,
                metadata=details.get("metadata", {}),
            )
