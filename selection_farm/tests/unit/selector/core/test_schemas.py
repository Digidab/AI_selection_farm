import pytest
from pydantic import ValidationError

from services.selector.app.core.schemas import (
    CoreError,
    DecisionStatus,
    ErrorCode,
    EvidenceRecord,
    RunCounters,
    SelectionDecision,
)


def test_accepted_decision_keeps_neutral_evidence() -> None:
    decision = SelectionDecision(
        task_id="TA_TEST",
        status=DecisionStatus.ACCEPTED,
        output_payload={"value": 1},
        evidence=(EvidenceRecord(check_id="contract", passed=True),),
    )

    assert decision.evidence[0].passed is True
    assert decision.failure_code is None


def test_non_accepted_decision_requires_failure_details() -> None:
    with pytest.raises(ValidationError):
        SelectionDecision(task_id="TA_TEST", status=DecisionStatus.REJECTED)


def test_accepted_decision_rejects_failure_details() -> None:
    with pytest.raises(ValidationError):
        SelectionDecision(
            task_id="TA_TEST",
            status=DecisionStatus.ACCEPTED,
            failure_code="unexpected",
        )


def test_records_reject_unknown_fields_and_negative_counters() -> None:
    with pytest.raises(ValidationError):
        RunCounters(total=0, unknown=1)

    with pytest.raises(ValidationError):
        RunCounters(failed=-1)


def test_core_error_preserves_typed_context() -> None:
    error = CoreError(
        ErrorCode.EXECUTION,
        "failed",
        retryable=True,
        context={"task_id": "TA_TEST"},
    )

    assert error.code is ErrorCode.EXECUTION
    assert error.retryable is True
    assert error.context == {"task_id": "TA_TEST"}
