"""Branch-neutral lifecycle, decision, and error records."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, strict=True),
]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]


class _CoreRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


class DecisionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


class ErrorCode(StrEnum):
    CONFIGURATION = "configuration_error"
    EXECUTION = "execution_error"
    VALIDATION = "validation_error"
    PERSISTENCE = "persistence_error"
    EXPORT = "export_error"


class RunCounters(_CoreRecord):
    total: NonNegativeInt = 0
    processed: NonNegativeInt = 0
    accepted: NonNegativeInt = 0
    rejected: NonNegativeInt = 0
    failed: NonNegativeInt = 0


class RunRecord(_CoreRecord):
    run_id: NonEmptyString
    status: RunStatus
    model_id: NonEmptyString
    dataset_id: NonEmptyString
    config_id: NonEmptyString
    counters: RunCounters = Field(default_factory=RunCounters)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskRecord(_CoreRecord):
    task_id: NonEmptyString
    run_id: NonEmptyString
    source_id: NonEmptyString | None = None
    task_type: NonEmptyString
    status: TaskStatus
    input_payload: dict[str, Any]
    error_type: NonEmptyString | None = None
    error_message: NonEmptyString | None = None
    error_traceback: NonEmptyString | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskFailure(_CoreRecord):
    error_type: NonEmptyString
    error_message: NonEmptyString
    error_traceback: NonEmptyString


class ResultRecord(_CoreRecord):
    task_id: NonEmptyString
    output_payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(_CoreRecord):
    check_id: NonEmptyString
    passed: StrictBool
    code: NonEmptyString | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SelectionDecision(_CoreRecord):
    task_id: NonEmptyString
    status: DecisionStatus
    output_payload: dict[str, Any] | None = None
    evidence: tuple[EvidenceRecord, ...] = ()
    failure_code: NonEmptyString | None = None
    failure_reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_failure_contract(self) -> "SelectionDecision":
        has_failure = self.failure_code is not None or self.failure_reason is not None
        if self.status is DecisionStatus.ACCEPTED and has_failure:
            raise ValueError("Accepted decisions cannot contain failure details")
        if self.status is not DecisionStatus.ACCEPTED and not has_failure:
            raise ValueError("Non-accepted decisions require failure details")
        return self


class CoreError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.context = dict(context or {})
