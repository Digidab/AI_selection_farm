"""Explicit LLM Selector assembly and command-line entrypoint."""

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.db import GenerationRecord, SelectorRepository
from ..core.export import connect_export_database
from ..core.ids import ProductionIDProvider
from ..core.pipeline import ExecutionEvidence, SelectorPipeline
from ..core.schemas import DecisionStatus, SelectionDecision, TaskRecord
from .config import DEFAULT_LLM_CONFIG_PATH, LLMBranchSettings, load_llm_config
from .evaluators import LLMCandidateEvaluator
from .evaluators.json_schema import JSONSchemaEvaluator
from .evaluators.semantic_dedup import PostgresAcceptedEmbeddingLookup, SemanticDedupEvaluator
from .persistence import (
    EmbeddingIDProvider,
    LLMEmbeddingRepository,
    ProductionEmbeddingIDProvider,
)
from .registry import LLMComponentRegistry, ResolvedLLMComponents, build_reference_registry
from .runtimes.ollama import OllamaRuntimeAdapter
from .schemas import LLMTask, load_llm_tasks

SELECTOR_VERSION = "selector_llm_v001"


@dataclass(frozen=True, slots=True)
class _LLMEvaluation:
    decision_status: DecisionStatus
    output_payload: dict[str, Any] | None
    evidence: tuple[dict[str, Any], ...]
    completion: str
    score: float | None
    failure_code: str | None
    failure_reason: str | None
    metadata: dict[str, Any]
    embedding: tuple[float, ...] | None


class LLMSelectorBranch:
    branch_id = "llm"
    selector_version = SELECTOR_VERSION
    task_type = "selector_llm"

    def __init__(
        self,
        *,
        settings: LLMBranchSettings,
        components: ResolvedLLMComponents,
        lookup: PostgresAcceptedEmbeddingLookup,
        embedding_repository: LLMEmbeddingRepository,
    ) -> None:
        self.settings = settings
        self.components = components
        self.lookup = lookup
        self.embedding_repository = embedding_repository
        self.model_id = settings.model_id
        self.dataset_id = settings.dataset_id
        self.config_id = settings.config_id
        self._tasks = load_llm_tasks(settings.tasks_path)
        self._evaluator = LLMCandidateEvaluator(
            output_contract=components.output_contract,
            json_schema=next(
                item for item in components.evaluators if isinstance(item, JSONSchemaEvaluator)
            ),
            semantic_dedup=next(
                item for item in components.evaluators if isinstance(item, SemanticDedupEvaluator)
            ),
        )

    def source_items(self) -> tuple[tuple[str, dict[str, Any]], ...]:
        return tuple(
            (
                task.task_id,
                task.model_dump(mode="json", exclude={"task_id"}, exclude_none=True),
            )
            for task in self._tasks
        )

    @staticmethod
    def _task(record: TaskRecord) -> LLMTask:
        return LLMTask.model_validate(
            {"task_id": record.metadata["source_id"], **record.input_payload}
        )

    def execute(self, task: TaskRecord) -> ExecutionEvidence:
        started = time.perf_counter()
        result = self.components.pipeline.run(
            self._task(task),
            runtime=self.components.runtime,
            modality=self.components.modalities[0],
            settings=self.settings.generation,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        return ExecutionEvidence(
            raw_output=result.text,
            output_payload=None,
            completion=result.text,
            latency_ms=latency_ms,
            metadata={
                "pipeline_id": self.settings.components.pipeline_id,
                "runtime_id": self.settings.components.runtime_id,
                "model": result.model,
            },
        )

    def evaluate(self, task: TaskRecord, execution: GenerationRecord) -> _LLMEvaluation:
        candidate = self._evaluator.evaluate(
            execution.raw_output,
            expected_schema=self._task(task).expected_schema,
            dataset_id=self.dataset_id,
            runtime=self.components.runtime,
            lookup=self.lookup,
            output_settings=self.settings.output,
            embedding_settings=self.settings.embedding,
            dedup_settings=self.settings.semantic_dedup,
        )
        status = DecisionStatus.ACCEPTED if candidate.accepted else DecisionStatus.REJECTED
        return _LLMEvaluation(
            decision_status=status,
            output_payload=candidate.parsed_output,
            evidence=tuple(item.model_dump(mode="json") for item in candidate.evidence),
            completion=execution.raw_output,
            score=None,
            failure_code=candidate.failure_code,
            failure_reason=candidate.failure_reason,
            metadata={
                "component_profile": self.settings.components.model_dump(mode="json"),
                "output_contract_id": candidate.output_contract_id,
            },
            embedding=candidate.embedding,
        )

    def persist_auxiliary(
        self,
        repository: SelectorRepository,
        generation_id: str,
        result: _LLMEvaluation,
    ) -> None:
        if result.decision_status is DecisionStatus.ACCEPTED and result.embedding is not None:
            self.embedding_repository.create_once(
                generation_id=generation_id,
                model_id=self.settings.embedding.model,
                values=result.embedding,
                metadata={"branch_id": self.branch_id},
            )

    def decision(self, task: TaskRecord, result: _LLMEvaluation) -> SelectionDecision:
        return SelectionDecision(
            task_id=task.task_id,
            status=result.decision_status,
            output_payload=result.output_payload,
            evidence=tuple(result.evidence),
            failure_code=result.failure_code,
            failure_reason=result.failure_reason,
        )


def build_branch(
    settings: LLMBranchSettings,
    connection: Any,
    *,
    registry: LLMComponentRegistry | None = None,
    embedding_id_provider: EmbeddingIDProvider | None = None,
) -> LLMSelectorBranch:
    if registry is None:
        runtime = OllamaRuntimeAdapter.from_settings(settings.runtime)
        registry = build_reference_registry(runtime)
    components = registry.resolve(settings.components)
    return LLMSelectorBranch(
        settings=settings,
        components=components,
        lookup=PostgresAcceptedEmbeddingLookup(connection),
        embedding_repository=LLMEmbeddingRepository(
            connection,
            embedding_id_provider or ProductionEmbeddingIDProvider(),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the isolated LLM Selector pipeline")
    parser.add_argument("--config", type=Path, default=DEFAULT_LLM_CONFIG_PATH)
    parser.add_argument("--common-config", type=Path, default=None)
    args = parser.parse_args(argv)
    config = (
        load_llm_config(args.config)
        if args.common_config is None
        else load_llm_config(args.config, common_path=args.common_config)
    )
    connection = connect_export_database(config.common)
    try:
        branch = build_branch(config.llm, connection)
        SelectorPipeline(SelectorRepository(connection, ProductionIDProvider())).run(branch)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
