"""Branch-neutral Selector orchestration boundary."""

from .config import CommonConfig, CommonConfigError, load_common_config, resolve_project_path
from .db import RepositoryError, SelectorRepository
from .ids import IDProvider, ProductionIDProvider
from .interfaces import SelectorBranch
from .logging_config import configure_logging, correlation_context, get_correlation_id, get_logger
from .pipeline import (
    EvaluationEvidence,
    EvidenceState,
    ExecutionEvidence,
    LifecycleError,
    PipelineError,
    ResumeStage,
    SelectorPipeline,
    ensure_run_transition,
    ensure_task_transition,
    resume_stage,
)
from .schemas import (
    CoreError,
    DecisionStatus,
    ErrorCode,
    EvidenceRecord,
    ResultRecord,
    RunCounters,
    RunRecord,
    RunStatus,
    SelectionDecision,
    TaskRecord,
    TaskStatus,
)

__all__ = (
    "CommonConfig",
    "CommonConfigError",
    "CoreError",
    "DecisionStatus",
    "ErrorCode",
    "EvidenceRecord",
    "EvidenceState",
    "EvaluationEvidence",
    "ExecutionEvidence",
    "IDProvider",
    "LifecycleError",
    "PipelineError",
    "ProductionIDProvider",
    "RepositoryError",
    "ResultRecord",
    "ResumeStage",
    "RunCounters",
    "RunRecord",
    "RunStatus",
    "SelectionDecision",
    "SelectorRepository",
    "SelectorBranch",
    "SelectorPipeline",
    "TaskRecord",
    "TaskStatus",
    "configure_logging",
    "correlation_context",
    "ensure_run_transition",
    "ensure_task_transition",
    "get_correlation_id",
    "get_logger",
    "load_common_config",
    "resume_stage",
    "resolve_project_path",
)
