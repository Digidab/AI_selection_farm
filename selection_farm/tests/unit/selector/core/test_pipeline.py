import pytest

from services.selector.app.core.pipeline import (
    EvidenceState,
    LifecycleError,
    ResumeStage,
    ensure_run_transition,
    ensure_task_transition,
    resume_stage,
)
from services.selector.app.core.schemas import RunStatus, TaskStatus


def test_legal_lifecycle_transitions_pass() -> None:
    ensure_run_transition(RunStatus.CREATED, RunStatus.RUNNING)
    ensure_run_transition(RunStatus.RUNNING, RunStatus.COMPLETED)
    ensure_task_transition(TaskStatus.PENDING, TaskStatus.GENERATING)
    ensure_task_transition(TaskStatus.GENERATING, TaskStatus.VALIDATING)
    ensure_task_transition(TaskStatus.VALIDATING, TaskStatus.ACCEPTED)


def test_illegal_lifecycle_transitions_fail() -> None:
    with pytest.raises(LifecycleError):
        ensure_run_transition(RunStatus.COMPLETED, RunStatus.RUNNING)
    with pytest.raises(LifecycleError):
        ensure_task_transition(TaskStatus.PENDING, TaskStatus.ACCEPTED)


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        (EvidenceState(), ResumeStage.EXECUTE),
        (EvidenceState(generation_id="GN"), ResumeStage.VALIDATE),
        (
            EvidenceState(generation_id="GN", validation_id="VA"),
            ResumeStage.FINALIZE,
        ),
        (
            EvidenceState(generation_id="GN", validation_id="VA", sample_id="SA"),
            ResumeStage.COMPLETE,
        ),
    ],
)
def test_resume_stage_uses_persisted_evidence(
    evidence: EvidenceState,
    expected: ResumeStage,
) -> None:
    assert resume_stage(evidence) is expected
