"""Branch-neutral DB-first export coordination and atomic file publication."""

import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import orjson
import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row

from .config import CommonConfig
from .schemas import CoreError, ErrorCode


class ExportError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.EXPORT, message)


@dataclass(frozen=True, slots=True)
class ExportRow:
    sample_id: str
    sample_status: str
    dataset_id: str
    selector_version: str | None
    sample_score: Any
    sample_failure_code: str | None
    sample_failure_reason: str | None
    sample_metadata: dict[str, Any]
    sample_created_at: datetime
    task_id: str
    task_input_payload: dict[str, Any]
    task_expected_schema: dict[str, Any] | None
    generation_id: str
    raw_output: str
    parsed_output: dict[str, Any] | None
    generation_metadata: dict[str, Any]
    validation_id: str
    validator_version: str
    is_valid: bool
    validation_score: Any
    validation_failure_code: str | None
    validation_failure_reason: str | None
    validation_details: dict[str, Any] | None
    run_id: str
    config_id: str | None
    model_id: str
    model_name: str | None
    model_type: str
    base_model: str | None
    completion: str | None


class ExportSource(Protocol):
    def load_rows(self, *, branch_id: str, dataset_id: str) -> tuple[ExportRow, ...]: ...


class BranchSerializer(Protocol):
    @property
    def branch_id(self) -> str: ...

    def serialize(self, row: ExportRow) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class BranchExportRequest:
    dataset_id: str
    serializer: BranchSerializer
    accepted_path: Path
    rejected_path: Path


@dataclass(frozen=True, slots=True)
class BranchExportSummary:
    branch_id: str
    dataset_id: str
    accepted_count: int
    rejected_count: int
    accepted_path: Path
    rejected_path: Path


class PostgresExportSource:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def load_rows(self, *, branch_id: str, dataset_id: str) -> tuple[ExportRow, ...]:
        try:
            with (
                self.connection.transaction(),
                self.connection.cursor(row_factory=dict_row) as cursor,
            ):
                cursor.execute(
                    """
                    SELECT
                        sample.sample_id,
                        sample.status AS sample_status,
                        sample.dataset_id,
                        sample.selector_version,
                        sample.score AS sample_score,
                        sample.failure_code AS sample_failure_code,
                        sample.failure_reason AS sample_failure_reason,
                        sample.metadata AS sample_metadata,
                        sample.created_at AS sample_created_at,
                        sample.completion,
                        task.task_id,
                        task.input_payload AS task_input_payload,
                        task.expected_schema AS task_expected_schema,
                        generation.generation_id,
                        generation.raw_output,
                        generation.parsed_output,
                        generation.metadata AS generation_metadata,
                        validation.validation_id,
                        validation.validator_version,
                        validation.is_valid,
                        validation.score AS validation_score,
                        validation.failure_code AS validation_failure_code,
                        validation.failure_reason AS validation_failure_reason,
                        validation.validation_details,
                        run.run_id,
                        run.config_id,
                        model.model_id,
                        model.model_name,
                        model.model_type,
                        model.base_model
                    FROM farm.samples AS sample
                    JOIN farm.tasks AS task ON task.task_id = sample.task_id
                    JOIN farm.generations AS generation
                      ON generation.generation_id = sample.generation_id
                    JOIN farm.validation_results AS validation
                      ON validation.validation_id = sample.validation_result_id
                    JOIN farm.runs AS run ON run.run_id = sample.run_id
                    JOIN farm.model_registry AS model ON model.model_id = sample.model_id
                    WHERE sample.dataset_id = %s
                      AND sample.status IN ('accepted', 'rejected')
                      AND model.model_type = %s
                    ORDER BY sample.sample_id
                    """,
                    (dataset_id, branch_id),
                )
                rows = cursor.fetchall()
        except psycopg.Error as exc:
            raise ExportError("Cannot read committed export rows") from exc
        return tuple(ExportRow(**row) for row in rows)


class AtomicExportWriter:
    def __init__(self, *, replace: Callable[[str | Path, str | Path], None] = os.replace) -> None:
        self._replace = replace

    @staticmethod
    def _temporary_path(target: Path, suffix: str) -> Path:
        descriptor, name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=suffix,
        )
        os.close(descriptor)
        temporary = Path(name)
        temporary.unlink()
        return temporary

    def write(self, payloads: Mapping[Path, bytes]) -> None:
        if not payloads:
            raise ExportError("Atomic export requires at least one target")
        targets = tuple(sorted((Path(path) for path in payloads), key=str))
        if len(set(targets)) != len(targets):
            raise ExportError("Atomic export targets must be unique")

        staged: dict[Path, Path] = {}
        backups: dict[Path, Path | None] = {}
        try:
            for target in targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                stage = self._temporary_path(target, ".tmp")
                with stage.open("wb") as handle:
                    os.fchmod(handle.fileno(), 0o644)
                    handle.write(payloads[target])
                    handle.flush()
                    os.fsync(handle.fileno())
                staged[target] = stage

            for target in targets:
                backup = None
                if target.exists():
                    backup = self._temporary_path(target, ".bak")
                    self._replace(target, backup)
                backups[target] = backup
                self._replace(staged[target], target)

        except OSError as exc:
            rollback_errors: list[OSError] = []
            for target in reversed(targets):
                backup = backups.get(target)
                try:
                    if backup is not None and backup.exists():
                        if target.exists():
                            target.unlink()
                        self._replace(backup, target)
                    elif target in backups and target.exists():
                        target.unlink()
                except OSError as rollback_exc:
                    rollback_errors.append(rollback_exc)
            if rollback_errors:
                raise ExportError("Atomic export failed and rollback was incomplete") from exc
            raise ExportError("Atomic export failed; previous files were restored") from exc
        else:
            cleanup_errors: list[OSError] = []
            for backup in backups.values():
                if backup is not None and backup.exists():
                    try:
                        backup.unlink()
                    except OSError as cleanup_exc:
                        cleanup_errors.append(cleanup_exc)
            if cleanup_errors:
                raise ExportError("Export published but backup cleanup was incomplete")
        finally:
            for path in (*staged.values(), *(item for item in backups.values() if item)):
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass


class ExportCoordinator:
    def __init__(self, source: ExportSource, writer: AtomicExportWriter) -> None:
        self.source = source
        self.writer = writer

    def export_all(
        self,
        requests: tuple[BranchExportRequest, ...],
    ) -> tuple[BranchExportSummary, ...]:
        if not requests:
            raise ExportError("At least one branch export request is required")
        branch_ids = tuple(request.serializer.branch_id for request in requests)
        if len(set(branch_ids)) != len(branch_ids):
            raise ExportError("Each branch may appear only once per export")

        payloads: dict[Path, bytes] = {}
        summaries: list[BranchExportSummary] = []
        for request in requests:
            accepted_lines: list[bytes] = []
            rejected_lines: list[bytes] = []
            rows = sorted(
                self.source.load_rows(
                    branch_id=request.serializer.branch_id,
                    dataset_id=request.dataset_id,
                ),
                key=lambda row: row.sample_id,
            )
            for row in rows:
                if row.model_type != request.serializer.branch_id:
                    raise ExportError("Export source returned a cross-branch row")
                if row.dataset_id != request.dataset_id:
                    raise ExportError("Export source returned a cross-dataset row")
                if (row.sample_status == "accepted") != row.is_valid:
                    raise ExportError("Sample status conflicts with validation evidence")
                if row.sample_status == "accepted" and (
                    row.sample_failure_code is not None or row.sample_failure_reason is not None
                ):
                    raise ExportError("Accepted sample contains rejection evidence")
                if row.sample_status == "rejected" and row.sample_failure_code is None:
                    raise ExportError("Rejected sample is missing failure evidence")
                line = (
                    orjson.dumps(
                        request.serializer.serialize(row),
                        option=orjson.OPT_SORT_KEYS,
                    )
                    + b"\n"
                )
                if row.sample_status == "accepted":
                    accepted_lines.append(line)
                elif row.sample_status == "rejected":
                    rejected_lines.append(line)
                else:
                    raise ExportError(f"Unsupported sample status: {row.sample_status}")

            accepted_path = Path(request.accepted_path)
            rejected_path = Path(request.rejected_path)
            if (
                accepted_path in payloads
                or rejected_path in payloads
                or accepted_path == rejected_path
            ):
                raise ExportError("Export target paths must be globally unique")
            payloads[accepted_path] = b"".join(accepted_lines)
            payloads[rejected_path] = b"".join(rejected_lines)
            summaries.append(
                BranchExportSummary(
                    branch_id=request.serializer.branch_id,
                    dataset_id=request.dataset_id,
                    accepted_count=len(accepted_lines),
                    rejected_count=len(rejected_lines),
                    accepted_path=accepted_path,
                    rejected_path=rejected_path,
                )
            )

        self.writer.write(payloads)
        return tuple(summaries)


def connect_export_database(config: CommonConfig) -> psycopg.Connection:
    file_values = dotenv_values(config.database.env_file)

    def value(environment_name: str, default: str | None = None) -> str:
        resolved = os.environ.get(environment_name, file_values.get(environment_name, default))
        if not isinstance(resolved, str) or not resolved:
            raise ExportError(f"Missing database environment value: {environment_name}")
        return resolved

    try:
        port = int(value(config.database.port_env, "5432"))
    except ValueError as exc:
        raise ExportError("Database port must be an integer") from exc
    try:
        return psycopg.connect(
            host=value(config.database.host_env, "127.0.0.1"),
            port=port,
            dbname=value(config.database.name_env),
            user=value(config.database.user_env),
            password=value(config.database.password_env),
            connect_timeout=max(1, round(config.timeouts.database_connect_seconds)),
            autocommit=False,
        )
    except psycopg.Error as exc:
        raise ExportError("Cannot connect to export database") from exc
