"""Exact canonical-input duplicate policy for the isolated ML branch."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import psycopg

from ..core.schemas import CoreError, ErrorCode, EvidenceRecord
from .schemas import FeatureDefinition, MLTask, canonical_feature_json


class MLExactDedupError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.VALIDATION, message)


@dataclass(frozen=True, slots=True)
class DuplicateMLInput:
    sample_id: str
    task_id: str


class AcceptedMLInputLookup(Protocol):
    def find_duplicate(
        self,
        *,
        dataset_id: str,
        canonical_input: str,
    ) -> DuplicateMLInput | None: ...


class PostgresAcceptedMLInputLookup:
    """Find exact accepted ML input identity in one dataset."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def find_duplicate(
        self,
        *,
        dataset_id: str,
        canonical_input: str,
    ) -> DuplicateMLInput | None:
        try:
            with self.connection.transaction(), self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sample.sample_id, task.task_id
                    FROM farm.samples AS sample
                    JOIN farm.tasks AS task
                      ON task.task_id = sample.task_id
                    JOIN farm.model_registry AS model
                      ON model.model_id = sample.model_id
                    WHERE sample.status = 'accepted'
                      AND sample.dataset_id = %s
                      AND model.model_type = 'ml'
                      AND task.input_payload = %s::jsonb
                    ORDER BY sample.sample_id
                    LIMIT 1
                    """,
                    (dataset_id, canonical_input),
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            raise MLExactDedupError("Exact ML duplicate lookup failed") from exc
        return None if row is None else DuplicateMLInput(sample_id=row[0], task_id=row[1])


@dataclass(frozen=True, slots=True)
class MLDedupResult:
    evidence: EvidenceRecord
    canonical_input: str


class MLExactDeduplicator:
    def evaluate(
        self,
        task: MLTask,
        *,
        feature_contract: Sequence[FeatureDefinition],
        dataset_id: str,
        lookup: AcceptedMLInputLookup,
    ) -> MLDedupResult:
        canonical_input = canonical_feature_json(task, feature_contract).decode("utf-8")
        duplicate = lookup.find_duplicate(
            dataset_id=dataset_id,
            canonical_input=canonical_input,
        )
        evidence = EvidenceRecord(
            check_id="ml_exact_dedup",
            passed=duplicate is None,
            code="duplicate_sample" if duplicate is not None else None,
            details={
                "message": (
                    "Canonical ML input is unique"
                    if duplicate is None
                    else "Canonical ML input matches an accepted sample"
                ),
                "canonical_input": canonical_input,
                "duplicate_sample_id": None if duplicate is None else duplicate.sample_id,
                "duplicate_task_id": None if duplicate is None else duplicate.task_id,
            },
        )
        return MLDedupResult(evidence=evidence, canonical_input=canonical_input)
