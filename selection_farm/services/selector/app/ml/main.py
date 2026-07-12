"""Explicit ML Selector assembly and command-line entrypoint."""

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson

from ..core.db import GenerationRecord, SelectorRepository
from ..core.export import connect_export_database
from ..core.ids import ProductionIDProvider
from ..core.pipeline import ExecutionEvidence, SelectorPipeline
from ..core.schemas import DecisionStatus, SelectionDecision, TaskRecord
from .config import DEFAULT_ML_CONFIG_PATH, MLBranchSettings, load_ml_config
from .deduplicator import MLExactDeduplicator, PostgresAcceptedMLInputLookup
from .pipelines.interfaces import ClassProbability, MLPrediction, PredictionEvidence
from .pipelines.registry import MLPipelineRegistry, build_reference_registry
from .producer import MLProducer
from .schemas import MLTask, PredictionMode, load_ml_tasks
from .validators import MLCandidateEvaluator, MLDecisionValidator

SELECTOR_VERSION = "selector_ml_v001"


@dataclass(frozen=True, slots=True)
class _MLEvaluation:
    decision_status: DecisionStatus
    output_payload: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    completion: str
    score: float | None
    failure_code: str | None
    failure_reason: str | None
    metadata: dict[str, Any]


class MLSelectorBranch:
    branch_id = "ml"
    selector_version = SELECTOR_VERSION
    task_type = "selector_ml"

    def __init__(
        self,
        *,
        settings: MLBranchSettings,
        registry: MLPipelineRegistry,
        lookup: PostgresAcceptedMLInputLookup,
    ) -> None:
        self.settings = settings
        self.model_id = settings.model_id
        self.dataset_id = settings.dataset_id
        self.config_id = settings.config_id
        self._tasks = load_ml_tasks(settings.tasks_path, settings.features)
        self._producer = MLProducer(registry)
        self._lookup = lookup
        self._evaluator = MLCandidateEvaluator(
            validator=MLDecisionValidator(),
            deduplicator=MLExactDeduplicator(),
        )

    def source_items(self) -> tuple[tuple[str, dict[str, Any]], ...]:
        return tuple((task.task_id, task.features) for task in self._tasks)

    @staticmethod
    def _task(record: TaskRecord) -> MLTask:
        return MLTask(task_id=record.metadata["source_id"], features=record.input_payload)

    def execute(self, task: TaskRecord) -> ExecutionEvidence:
        started = time.perf_counter()
        result = self._producer.produce(self._task(task), self.settings)
        payload = {
            "mode": result.mode.value,
            "prediction": result.prediction,
            "probabilities": (
                None
                if result.probabilities is None
                else [
                    {"label": item.label, "probability": item.probability}
                    for item in result.probabilities
                ]
            ),
            "evidence": {
                "pipeline_id": result.evidence.pipeline_id,
                "feature_order": list(result.evidence.feature_order),
                "used_probability_api": result.evidence.used_probability_api,
            },
        }
        completion = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8")
        return ExecutionEvidence(
            raw_output=completion,
            output_payload=payload,
            completion=completion,
            latency_ms=round((time.perf_counter() - started) * 1000),
            metadata={
                "pipeline_id": self.settings.pipeline_id,
                "artifact_identity": self.settings.artifact_path.name,
            },
        )

    @staticmethod
    def _prediction(task: TaskRecord, generation: GenerationRecord) -> MLPrediction:
        payload = generation.parsed_output
        if payload is None:
            raise ValueError("Persisted ML execution payload is missing")
        probabilities = payload["probabilities"]
        return MLPrediction(
            task_id=task.metadata["source_id"],
            mode=PredictionMode(payload["mode"]),
            prediction=payload["prediction"],
            probabilities=(
                None
                if probabilities is None
                else tuple(ClassProbability(**item) for item in probabilities)
            ),
            evidence=PredictionEvidence(
                pipeline_id=payload["evidence"]["pipeline_id"],
                feature_order=tuple(payload["evidence"]["feature_order"]),
                used_probability_api=payload["evidence"]["used_probability_api"],
            ),
        )

    def evaluate(self, task: TaskRecord, execution: GenerationRecord) -> _MLEvaluation:
        candidate = self._evaluator.evaluate(
            self._prediction(task, execution),
            self._task(task),
            self.settings,
            self._lookup,
        )
        status = DecisionStatus.ACCEPTED if candidate.accepted else DecisionStatus.REJECTED
        return _MLEvaluation(
            decision_status=status,
            output_payload={"prediction": candidate.prediction},
            evidence=tuple(item.model_dump(mode="json") for item in candidate.evidence),
            completion=execution.raw_output,
            score=candidate.score,
            failure_code=candidate.failure_code,
            failure_reason=candidate.failure_reason,
            metadata={
                "pipeline_id": self.settings.pipeline_id,
                "artifact_identity": self.settings.artifact_path.name,
                "canonical_input": candidate.canonical_input,
            },
        )

    def persist_auxiliary(
        self,
        repository: SelectorRepository,
        generation_id: str,
        result: _MLEvaluation,
    ) -> None:
        return None

    def decision(self, task: TaskRecord, result: _MLEvaluation) -> SelectionDecision:
        return SelectionDecision(
            task_id=task.task_id,
            status=result.decision_status,
            output_payload=result.output_payload,
            evidence=tuple(result.evidence),
            failure_code=result.failure_code,
            failure_reason=result.failure_reason,
        )


def build_branch(
    settings: MLBranchSettings,
    connection: Any,
    *,
    registry: MLPipelineRegistry | None = None,
) -> MLSelectorBranch:
    resolved_registry = registry or build_reference_registry()
    resolved_registry.resolve(settings.pipeline_id)
    return MLSelectorBranch(
        settings=settings,
        registry=resolved_registry,
        lookup=PostgresAcceptedMLInputLookup(connection),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the isolated ML Selector pipeline")
    parser.add_argument("--config", type=Path, default=DEFAULT_ML_CONFIG_PATH)
    parser.add_argument("--common-config", type=Path, default=None)
    args = parser.parse_args(argv)
    config = (
        load_ml_config(args.config)
        if args.common_config is None
        else load_ml_config(args.config, common_path=args.common_config)
    )
    connection = connect_export_database(config.common)
    try:
        branch = build_branch(config.ml, connection)
        SelectorPipeline(SelectorRepository(connection, ProductionIDProvider())).run(branch)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
