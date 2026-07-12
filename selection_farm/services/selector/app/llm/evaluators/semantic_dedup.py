"""LLM-only semantic duplicate evaluator and accepted-sample pgvector lookup."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import psycopg

from ...core.schemas import CoreError, ErrorCode, EvidenceRecord
from ..config import EmbeddingSettings, SemanticDedupSettings
from ..interfaces import LLMRuntimeAdapter
from ..output_contracts.structured_json import ParsedStructuredJSON
from ..schemas import CapabilityDescriptor, ComponentKind


class SemanticDedupError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.VALIDATION, message)


@dataclass(frozen=True, slots=True)
class NearestAcceptedEmbedding:
    sample_id: str
    cosine_distance: float


class AcceptedEmbeddingLookup(Protocol):
    def find_nearest(
        self,
        *,
        dataset_id: str,
        embedding_model_id: str,
        candidate: Sequence[float],
    ) -> NearestAcceptedEmbedding | None: ...


def _vector_literal(values: Sequence[float]) -> str:
    vector = tuple(float(value) for value in values)
    if len(vector) != 768 or not all(math.isfinite(value) for value in vector):
        raise SemanticDedupError("Candidate embedding must contain exactly 768 finite values")
    return f"[{','.join(str(value) for value in vector)}]"


class PostgresAcceptedEmbeddingLookup:
    """Query only accepted samples in the same LLM dataset and embedding space."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def find_nearest(
        self,
        *,
        dataset_id: str,
        embedding_model_id: str,
        candidate: Sequence[float],
    ) -> NearestAcceptedEmbedding | None:
        vector = _vector_literal(candidate)
        try:
            with self.connection.transaction(), self.connection.cursor() as cursor:
                cursor.execute(
                    """
                SELECT sample.sample_id,
                       embedding.embedding <=> %s::vector AS cosine_distance
                FROM farm.samples AS sample
                JOIN farm.model_registry AS model
                  ON model.model_id = sample.model_id
                JOIN farm.embeddings AS embedding
                  ON embedding.source_type = 'generation'
                 AND embedding.source_id = sample.generation_id
                WHERE sample.status = 'accepted'
                  AND sample.dataset_id = %s
                  AND model.model_type = 'llm'
                  AND embedding.embedding_model_id = %s
                ORDER BY embedding.embedding <=> %s::vector, sample.sample_id
                LIMIT 1
                """,
                    (vector, dataset_id, embedding_model_id, vector),
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            raise SemanticDedupError("Semantic duplicate lookup failed") from exc

        if row is None:
            return None
        try:
            distance = float(row[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise SemanticDedupError("Database returned an invalid cosine distance") from exc
        if not math.isfinite(distance) or not 0.0 <= distance <= 2.0:
            raise SemanticDedupError("Database returned an invalid cosine distance")
        return NearestAcceptedEmbedding(sample_id=row[0], cosine_distance=distance)


@dataclass(frozen=True, slots=True)
class SemanticDedupResult:
    evidence: EvidenceRecord
    embedding: tuple[float, ...]


class SemanticDedupEvaluator:
    descriptor = CapabilityDescriptor(
        component_id="semantic_dedup",
        kind=ComponentKind.EVALUATOR,
        capabilities=frozenset({"embedding", "pgvector_cosine"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    def evaluate(
        self,
        candidate: ParsedStructuredJSON,
        *,
        dataset_id: str,
        runtime: LLMRuntimeAdapter,
        lookup: AcceptedEmbeddingLookup,
        embedding_settings: EmbeddingSettings,
        dedup_settings: SemanticDedupSettings,
    ) -> SemanticDedupResult:
        embedded = runtime.embed(
            (candidate.canonical_text,),
            model=embedding_settings.model,
            expected_dimension=embedding_settings.dimension,
        )
        if len(embedded.vectors) != 1:
            raise SemanticDedupError("Embedding runtime returned an invalid vector count")
        vector = embedded.vectors[0]
        _vector_literal(vector)

        nearest = lookup.find_nearest(
            dataset_id=dataset_id,
            embedding_model_id=embedding_settings.model,
            candidate=vector,
        )
        if nearest is None:
            evidence = EvidenceRecord(
                check_id=self.descriptor.component_id,
                passed=True,
                details={
                    "embedding_model_id": embedding_settings.model,
                    "nearest_sample_id": None,
                    "cosine_distance": None,
                    "max_cosine_distance": dedup_settings.max_cosine_distance,
                },
            )
        else:
            if not math.isfinite(nearest.cosine_distance) or not (
                0.0 <= nearest.cosine_distance <= 2.0
            ):
                raise SemanticDedupError("Duplicate lookup returned an invalid cosine distance")
            duplicate = nearest.cosine_distance <= dedup_settings.max_cosine_distance
            evidence = EvidenceRecord(
                check_id=self.descriptor.component_id,
                passed=not duplicate,
                code="duplicate_sample" if duplicate else None,
                details={
                    "embedding_model_id": embedding_settings.model,
                    "nearest_sample_id": nearest.sample_id,
                    "cosine_distance": nearest.cosine_distance,
                    "max_cosine_distance": dedup_settings.max_cosine_distance,
                },
            )
        return SemanticDedupResult(evidence=evidence, embedding=vector)
