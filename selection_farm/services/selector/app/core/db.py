"""Typed PostgreSQL repository for branch-neutral Selector evidence."""

import json
import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg

from .ids import IDProvider
from .pipeline import EvidenceState, ensure_run_transition, ensure_task_transition
from .schemas import CoreError, ErrorCode, RunCounters, RunRecord, RunStatus, TaskRecord, TaskStatus


class RepositoryError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PERSISTENCE, message)


@dataclass(frozen=True, slots=True)
class GenerationRecord:
    generation_id: str
    task_id: str
    run_id: str
    model_id: str
    raw_output: str = ""
    parsed_output: dict[str, Any] | None = None
    latency_ms: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    validation_id: str
    generation_id: str
    is_valid: bool
    score: float | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SampleRecord:
    sample_id: str
    generation_id: str
    status: str


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    embedding_id: str
    source_type: str
    source_id: str


@dataclass(frozen=True, slots=True)
class ResumeItem:
    task: TaskRecord
    evidence: EvidenceState


def _json(value: Mapping[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _vector_literal(values: Sequence[float]) -> str:
    vector = tuple(float(value) for value in values)
    if not vector or not all(math.isfinite(value) for value in vector):
        raise RepositoryError("Vector evidence must contain finite values")
    return f"[{','.join(str(value) for value in vector)}]"


class SelectorRepository:
    def __init__(self, connection: psycopg.Connection, id_provider: IDProvider) -> None:
        self.connection = connection
        self.id_provider = id_provider

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.connection.transaction():
            yield

    def _lock(self, cursor: psycopg.Cursor, key: str) -> None:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))

    @staticmethod
    def _reconcile_run_counters(cursor: psycopg.Cursor, run_id: str) -> None:
        cursor.execute(
            """
            UPDATE farm.runs AS run
            SET processed_items = totals.processed,
                accepted_items = totals.accepted,
                rejected_items = totals.rejected,
                failed_items = totals.failed
            FROM (
                SELECT
                    count(*) FILTER (WHERE status IN ('accepted', 'rejected', 'failed')) AS processed,
                    count(*) FILTER (WHERE status = 'accepted') AS accepted,
                    count(*) FILTER (WHERE status = 'rejected') AS rejected,
                    count(*) FILTER (WHERE status = 'failed') AS failed
                FROM farm.tasks WHERE run_id = %s
            ) AS totals
            WHERE run.run_id = %s AND totals.processed <= run.total_items
            """,
            (run_id, run_id),
        )
        if cursor.rowcount != 1:
            raise RepositoryError("Run counters would violate lifecycle totals")

    def get_model_type(self, model_id: str) -> str | None:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT model_type FROM farm.model_registry WHERE model_id = %s",
                (model_id,),
            )
            row = cursor.fetchone()
        return None if row is None else row[0]

    def find_resumable_run(
        self,
        *,
        model_id: str,
        dataset_id: str,
        config_id: str,
    ) -> RunRecord | None:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, status, total_items, processed_items, accepted_items,
                       rejected_items, failed_items, metadata
                FROM farm.runs
                WHERE run_type = 'selector' AND model_id = %s AND dataset_id = %s
                  AND config_id = %s AND status IN ('created', 'running')
                ORDER BY id DESC LIMIT 1
                """,
                (model_id, dataset_id, config_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=row[0],
            status=RunStatus(row[1]),
            model_id=model_id,
            dataset_id=dataset_id,
            config_id=config_id,
            counters=RunCounters(
                total=row[2],
                processed=row[3],
                accepted=row[4],
                rejected=row[5],
                failed=row[6],
            ),
            metadata=row[7],
        )

    def create_run(
        self,
        *,
        model_id: str,
        dataset_id: str,
        config_id: str,
        total_items: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> RunRecord:
        run_id = self.id_provider.issue_run_id()
        record = RunRecord(
            run_id=run_id,
            status=RunStatus.CREATED,
            model_id=model_id,
            dataset_id=dataset_id,
            config_id=config_id,
            counters=RunCounters(total=total_items),
            metadata=dict(metadata or {}),
        )
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO farm.runs (
                    run_id, run_type, status, model_id, dataset_id, config_id,
                    total_items, metadata
                )
                VALUES (%s, 'selector', %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    run_id,
                    RunStatus.CREATED.value,
                    model_id,
                    dataset_id,
                    config_id,
                    total_items,
                    _json(metadata),
                ),
            )
        return record

    def create_task(
        self,
        *,
        run_id: str,
        task_type: str,
        input_payload: Mapping[str, Any],
        priority: int = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskRecord:
        task_id = self.id_provider.issue_task_id()
        record = TaskRecord(
            task_id=task_id,
            run_id=run_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            input_payload=dict(input_payload),
            metadata=dict(metadata or {}),
        )
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO farm.tasks (
                    task_id, run_id, task_type, input_payload, status, priority, metadata
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                """,
                (
                    task_id,
                    run_id,
                    task_type,
                    _json(input_payload),
                    TaskStatus.PENDING.value,
                    priority,
                    _json(metadata),
                ),
            )
        return record

    def create_task_once(
        self,
        *,
        run_id: str,
        source_id: str,
        task_type: str,
        input_payload: Mapping[str, Any],
        priority: int = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskRecord:
        with self.transaction(), self.connection.cursor() as cursor:
            self._lock(cursor, f"task:{run_id}:{source_id}")
            cursor.execute(
                """
                SELECT task_id, run_id, task_type, status, input_payload, metadata
                FROM farm.tasks
                WHERE run_id = %s AND metadata ->> 'source_id' = %s
                ORDER BY id LIMIT 1
                """,
                (run_id, source_id),
            )
            row = cursor.fetchone()
            if row is not None:
                return TaskRecord(
                    task_id=row[0],
                    run_id=row[1],
                    task_type=row[2],
                    status=TaskStatus(row[3]),
                    input_payload=row[4],
                    metadata=row[5],
                )
            task_id = self.id_provider.issue_task_id()
            task_metadata = {**dict(metadata or {}), "source_id": source_id}
            cursor.execute(
                """
                INSERT INTO farm.tasks (
                    task_id, run_id, task_type, input_payload, status, priority, metadata
                )
                VALUES (%s, %s, %s, %s::jsonb, 'pending', %s, %s::jsonb)
                """,
                (task_id, run_id, task_type, _json(input_payload), priority, _json(task_metadata)),
            )
        return TaskRecord(
            task_id=task_id,
            run_id=run_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            input_payload=dict(input_payload),
            metadata=task_metadata,
        )

    def transition_run(self, run_id: str, target: RunStatus) -> RunStatus:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute("SELECT status FROM farm.runs WHERE run_id = %s FOR UPDATE", (run_id,))
            row = cursor.fetchone()
            if row is None:
                raise RepositoryError(f"Unknown run_id: {run_id}")
            current = RunStatus(row[0])
            ensure_run_transition(current, target)
            cursor.execute(
                """
                UPDATE farm.runs
                SET status = %s,
                    finished_at = CASE WHEN %s IN ('completed', 'failed') THEN now() ELSE NULL END
                WHERE run_id = %s
                """,
                (target.value, target.value, run_id),
            )
        return target

    def transition_task(self, task_id: str, target: TaskStatus) -> TaskStatus:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM farm.tasks WHERE task_id = %s FOR UPDATE", (task_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise RepositoryError(f"Unknown task_id: {task_id}")
            current = TaskStatus(row[0])
            ensure_task_transition(current, target)
            cursor.execute(
                "UPDATE farm.tasks SET status = %s, updated_at = now() WHERE task_id = %s",
                (target.value, task_id),
            )
        return target

    def update_run_counters(
        self,
        run_id: str,
        *,
        processed: int = 0,
        accepted: int = 0,
        rejected: int = 0,
        failed: int = 0,
    ) -> RunCounters:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT total_items, processed_items, accepted_items, rejected_items, failed_items
                FROM farm.runs WHERE run_id = %s FOR UPDATE
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RepositoryError(f"Unknown run_id: {run_id}")
            counters = RunCounters(
                total=row[0],
                processed=row[1] + processed,
                accepted=row[2] + accepted,
                rejected=row[3] + rejected,
                failed=row[4] + failed,
            )
            terminal = counters.accepted + counters.rejected + counters.failed
            if counters.processed > counters.total or terminal > counters.processed:
                raise RepositoryError("Run counters would violate lifecycle totals")
            cursor.execute(
                """
                UPDATE farm.runs
                SET processed_items = %s, accepted_items = %s,
                    rejected_items = %s, failed_items = %s
                WHERE run_id = %s
                """,
                (
                    counters.processed,
                    counters.accepted,
                    counters.rejected,
                    counters.failed,
                    run_id,
                ),
            )
        return counters

    def create_generation_once(
        self,
        *,
        task_id: str,
        run_id: str,
        model_id: str,
        raw_output: str,
        parsed_output: Mapping[str, Any] | None = None,
        latency_ms: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> GenerationRecord:
        with self.transaction(), self.connection.cursor() as cursor:
            self._lock(cursor, f"generation:{task_id}")
            cursor.execute(
                """
                SELECT generation_id, task_id, run_id, model_id
                FROM farm.generations WHERE task_id = %s ORDER BY id LIMIT 1
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                return GenerationRecord(*row)
            generation_id = self.id_provider.issue_generation_id()
            cursor.execute(
                """
                INSERT INTO farm.generations (
                    generation_id, task_id, run_id, model_id, raw_output,
                    parsed_output, latency_ms, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                """,
                (
                    generation_id,
                    task_id,
                    run_id,
                    model_id,
                    raw_output,
                    None if parsed_output is None else _json(parsed_output),
                    latency_ms,
                    _json(metadata),
                ),
            )
            return GenerationRecord(generation_id, task_id, run_id, model_id)

    def load_generation(self, generation_id: str) -> GenerationRecord:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT generation_id, task_id, run_id, model_id, raw_output,
                       parsed_output, latency_ms, metadata
                FROM farm.generations WHERE generation_id = %s
                """,
                (generation_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RepositoryError(f"Unknown generation_id: {generation_id}")
        return GenerationRecord(*row)

    def create_validation_once(
        self,
        *,
        generation_id: str,
        validator_version: str,
        is_valid: bool,
        score: float | None = None,
        failure_code: str | None = None,
        failure_reason: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> ValidationRecord:
        with self.transaction(), self.connection.cursor() as cursor:
            self._lock(cursor, f"validation:{generation_id}")
            cursor.execute(
                """
                SELECT validation_id, generation_id, is_valid
                FROM farm.validation_results WHERE generation_id = %s ORDER BY id LIMIT 1
                """,
                (generation_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                return ValidationRecord(*row)
            validation_id = self.id_provider.issue_validation_id()
            cursor.execute(
                """
                INSERT INTO farm.validation_results (
                    validation_id, generation_id, validator_version, is_valid,
                    score, failure_code, failure_reason, validation_details
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    validation_id,
                    generation_id,
                    validator_version,
                    is_valid,
                    score,
                    failure_code,
                    failure_reason,
                    None if details is None else _json(details),
                ),
            )
            return ValidationRecord(validation_id, generation_id, is_valid)

    def load_validation(self, validation_id: str) -> ValidationRecord:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT validation_id, generation_id, is_valid, score, failure_code,
                       failure_reason, validation_details
                FROM farm.validation_results WHERE validation_id = %s
                """,
                (validation_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RepositoryError(f"Unknown validation_id: {validation_id}")
        return ValidationRecord(*row)

    def create_sample_once(
        self,
        *,
        validation_id: str,
        task_id: str,
        generation_id: str,
        run_id: str,
        model_id: str,
        dataset_id: str,
        status: str,
        completion: str,
        selector_version: str,
        score: float | None = None,
        failure_code: str | None = None,
        failure_reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SampleRecord:
        if status not in {"accepted", "rejected"}:
            raise RepositoryError(f"Unsupported sample status: {status}")
        with self.transaction(), self.connection.cursor() as cursor:
            self._lock(cursor, f"sample:{generation_id}")
            cursor.execute(
                """
                SELECT sample_id, generation_id, status
                FROM farm.samples WHERE generation_id = %s ORDER BY id LIMIT 1
                """,
                (generation_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                return SampleRecord(*row)
            sample_id = self.id_provider.issue_sample_id()
            cursor.execute(
                """
                INSERT INTO farm.samples (
                    sample_id, validation_result_id, task_id, generation_id,
                    run_id, model_id, dataset_id, status, completion, score,
                    failure_code, failure_reason, selector_version, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    sample_id,
                    validation_id,
                    task_id,
                    generation_id,
                    run_id,
                    model_id,
                    dataset_id,
                    status,
                    completion,
                    score,
                    failure_code,
                    failure_reason,
                    selector_version,
                    _json(metadata),
                ),
            )
            return SampleRecord(sample_id, generation_id, status)

    def create_embedding_once(
        self,
        *,
        source_type: str,
        source_id: str,
        model_id: str,
        values: Sequence[float],
        metadata: Mapping[str, Any] | None = None,
    ) -> EmbeddingRecord:
        with self.transaction(), self.connection.cursor() as cursor:
            self._lock(cursor, f"embedding:{source_type}:{source_id}")
            cursor.execute(
                """
                SELECT embedding_id, source_type, source_id
                FROM farm.embeddings
                WHERE source_type = %s AND source_id = %s
                ORDER BY id LIMIT 1
                """,
                (source_type, source_id),
            )
            row = cursor.fetchone()
            if row is not None:
                return EmbeddingRecord(*row)
            embedding_id = self.id_provider.issue_embedding_id()
            cursor.execute(
                """
                INSERT INTO farm.embeddings (
                    embedding_id, source_type, source_id, embedding_model_id,
                    embedding, metadata
                )
                VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb)
                """,
                (
                    embedding_id,
                    source_type,
                    source_id,
                    model_id,
                    _vector_literal(values),
                    _json(metadata),
                ),
            )
            return EmbeddingRecord(embedding_id, source_type, source_id)

    def finalize_task_once(
        self,
        *,
        validation_id: str,
        task_id: str,
        generation_id: str,
        run_id: str,
        model_id: str,
        dataset_id: str,
        status: str,
        completion: str,
        selector_version: str,
        score: float | None = None,
        failure_code: str | None = None,
        failure_reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SampleRecord:
        if status not in {"accepted", "rejected"}:
            raise RepositoryError(f"Unsupported sample status: {status}")
        with self.transaction(), self.connection.cursor() as cursor:
            self._lock(cursor, f"finalize:{task_id}")
            cursor.execute(
                """
                SELECT sample_id, generation_id, status
                FROM farm.samples WHERE generation_id = %s ORDER BY id LIMIT 1
                """,
                (generation_id,),
            )
            existing = cursor.fetchone()
            cursor.execute(
                "SELECT status FROM farm.tasks WHERE task_id = %s FOR UPDATE",
                (task_id,),
            )
            task_row = cursor.fetchone()
            if task_row is None:
                raise RepositoryError(f"Unknown task_id: {task_id}")
            current = TaskStatus(task_row[0])
            if existing is not None:
                existing_status = TaskStatus(existing[2])
                if existing_status is not TaskStatus(status):
                    raise RepositoryError("Persisted sample status conflicts with validation")
                if current in {TaskStatus.ACCEPTED, TaskStatus.REJECTED}:
                    if current is not existing_status:
                        raise RepositoryError("Task status conflicts with persisted sample")
                else:
                    if current is TaskStatus.GENERATING:
                        ensure_task_transition(current, TaskStatus.VALIDATING)
                        current = TaskStatus.VALIDATING
                    ensure_task_transition(current, existing_status)
                    cursor.execute(
                        "UPDATE farm.tasks SET status = %s, updated_at = now() WHERE task_id = %s",
                        (existing_status.value, task_id),
                    )
                self._reconcile_run_counters(cursor, run_id)
                return SampleRecord(*existing)
            ensure_task_transition(current, TaskStatus(status))
            sample_id = self.id_provider.issue_sample_id()
            cursor.execute(
                """
                INSERT INTO farm.samples (
                    sample_id, validation_result_id, task_id, generation_id,
                    run_id, model_id, dataset_id, status, completion, score,
                    failure_code, failure_reason, selector_version, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    sample_id,
                    validation_id,
                    task_id,
                    generation_id,
                    run_id,
                    model_id,
                    dataset_id,
                    status,
                    completion,
                    score,
                    failure_code,
                    failure_reason,
                    selector_version,
                    _json(metadata),
                ),
            )
            cursor.execute(
                "UPDATE farm.tasks SET status = %s, updated_at = now() WHERE task_id = %s",
                (status, task_id),
            )
            self._reconcile_run_counters(cursor, run_id)
        return SampleRecord(sample_id, generation_id, status)

    def fail_task_once(self, *, task_id: str, run_id: str) -> None:
        with self.transaction(), self.connection.cursor() as cursor:
            self._lock(cursor, f"fail:{task_id}")
            cursor.execute(
                "SELECT status FROM farm.tasks WHERE task_id = %s FOR UPDATE",
                (task_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RepositoryError(f"Unknown task_id: {task_id}")
            current = TaskStatus(row[0])
            if current is TaskStatus.FAILED:
                return
            if current in {TaskStatus.ACCEPTED, TaskStatus.REJECTED}:
                raise RepositoryError("Cannot fail a finalized task")
            ensure_task_transition(current, TaskStatus.FAILED)
            cursor.execute(
                "UPDATE farm.tasks SET status = 'failed', updated_at = now() WHERE task_id = %s",
                (task_id,),
            )
            self._reconcile_run_counters(cursor, run_id)

    def list_resume_items(self, run_id: str) -> tuple[ResumeItem, ...]:
        with self.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT task.task_id, task.run_id, task.task_type, task.status,
                       task.input_payload, task.metadata,
                       generation.generation_id, validation.validation_id,
                       sample.sample_id, embedding.embedding_id
                FROM farm.tasks AS task
                LEFT JOIN LATERAL (
                    SELECT generation_id FROM farm.generations
                    WHERE task_id = task.task_id ORDER BY id LIMIT 1
                ) AS generation ON true
                LEFT JOIN LATERAL (
                    SELECT validation_id FROM farm.validation_results
                    WHERE generation_id = generation.generation_id ORDER BY id LIMIT 1
                ) AS validation ON true
                LEFT JOIN LATERAL (
                    SELECT sample_id FROM farm.samples
                    WHERE generation_id = generation.generation_id ORDER BY id LIMIT 1
                ) AS sample ON true
                LEFT JOIN LATERAL (
                    SELECT embedding_id FROM farm.embeddings
                    WHERE source_id = generation.generation_id ORDER BY id LIMIT 1
                ) AS embedding ON true
                WHERE task.run_id = %s
                  AND task.status IN ('pending', 'generating', 'validating')
                ORDER BY task.priority DESC, task.id
                """,
                (run_id,),
            )
            rows = cursor.fetchall()

        return tuple(
            ResumeItem(
                task=TaskRecord(
                    task_id=row[0],
                    run_id=row[1],
                    task_type=row[2],
                    status=TaskStatus(row[3]),
                    input_payload=row[4],
                    metadata=row[5],
                ),
                evidence=EvidenceState(
                    generation_id=row[6],
                    validation_id=row[7],
                    sample_id=row[8],
                    embedding_id=row[9],
                ),
            )
            for row in rows
        )
