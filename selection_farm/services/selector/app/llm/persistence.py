"""LLM-owned persistence for accepted generation embeddings."""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import psycopg

from scripts.id_generator.embedding_id import issue_embedding_id

from ..core.schemas import CoreError, ErrorCode


class LLMEmbeddingPersistenceError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PERSISTENCE, message)


class EmbeddingIDProvider(Protocol):
    def issue_embedding_id(self) -> str: ...


class ProductionEmbeddingIDProvider:
    def issue_embedding_id(self) -> str:
        return issue_embedding_id()


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    embedding_id: str
    source_type: str
    source_id: str
    embedding_model_id: str


def _json(value: Mapping[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _vector_literal(values: Sequence[float]) -> str:
    vector = tuple(float(value) for value in values)
    if len(vector) != 768 or not all(math.isfinite(value) for value in vector):
        raise LLMEmbeddingPersistenceError(
            "LLM embedding evidence must contain exactly 768 finite values"
        )
    return f"[{','.join(str(value) for value in vector)}]"


class LLMEmbeddingRepository:
    def __init__(
        self,
        connection: psycopg.Connection,
        id_provider: EmbeddingIDProvider,
    ) -> None:
        self.connection = connection
        self.id_provider = id_provider

    def create_once(
        self,
        *,
        generation_id: str,
        model_id: str,
        values: Sequence[float],
        metadata: Mapping[str, Any] | None = None,
    ) -> EmbeddingRecord:
        vector = _vector_literal(values)
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"llm-embedding:{generation_id}",),
            )
            cursor.execute(
                """
                SELECT embedding_id, source_type, source_id, embedding_model_id
                FROM farm.embeddings
                WHERE source_type = 'generation' AND source_id = %s
                ORDER BY id LIMIT 1
                """,
                (generation_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                if row[3] != model_id:
                    raise LLMEmbeddingPersistenceError(
                        "Persisted embedding model identity conflicts with the active configuration"
                    )
                return EmbeddingRecord(*row)
            embedding_id = self.id_provider.issue_embedding_id()
            cursor.execute(
                """
                INSERT INTO farm.embeddings (
                    embedding_id, source_type, source_id, embedding_model_id,
                    embedding, metadata
                )
                VALUES (%s, 'generation', %s, %s, %s::vector, %s::jsonb)
                """,
                (
                    embedding_id,
                    generation_id,
                    model_id,
                    vector,
                    _json(metadata),
                ),
            )
        return EmbeddingRecord(embedding_id, "generation", generation_id, model_id)
