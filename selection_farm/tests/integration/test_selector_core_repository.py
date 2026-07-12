from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import pytest

from services.selector.app.core.db import RepositoryError, SelectorRepository
from services.selector.app.core.pipeline import LifecycleError, ResumeStage, resume_stage
from services.selector.app.core.schemas import RunStatus, TaskStatus

COUNTERS_FILE = Path(__file__).resolve().parents[2] / "configs" / "id_mapping" / "id_counters.json"


class FakeIDProvider:
    def __init__(self, suffix: str) -> None:
        self.suffix = suffix
        self.counts: defaultdict[str, int] = defaultdict(int)

    def _issue(self, kind: str) -> str:
        self.counts[kind] += 1
        return f"_tz08_{kind}_{self.suffix}_{self.counts[kind]}"

    def issue_model_id(self) -> str:
        return self._issue("model")

    def issue_run_id(self) -> str:
        return self._issue("run")

    def issue_task_id(self) -> str:
        return self._issue("task")

    def issue_generation_id(self) -> str:
        return self._issue("generation")

    def issue_validation_id(self) -> str:
        return self._issue("validation")

    def issue_sample_id(self) -> str:
        return self._issue("sample")

    def issue_embedding_id(self) -> str:
        return self._issue("embedding")


def _cleanup(db_connection, suffix: str) -> None:
    pattern = f"%{suffix}%"
    with db_connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM farm.embeddings WHERE embedding_id LIKE %s OR source_id LIKE %s",
            (pattern, pattern),
        )
        cursor.execute("DELETE FROM farm.samples WHERE sample_id LIKE %s", (pattern,))
        cursor.execute(
            "DELETE FROM farm.validation_results WHERE validation_id LIKE %s", (pattern,)
        )
        cursor.execute("DELETE FROM farm.generations WHERE generation_id LIKE %s", (pattern,))
        cursor.execute("DELETE FROM farm.tasks WHERE task_id LIKE %s", (pattern,))
        cursor.execute("DELETE FROM farm.runs WHERE run_id LIKE %s", (pattern,))
        cursor.execute("DELETE FROM farm.model_registry WHERE model_id LIKE %s", (pattern,))
    db_connection.commit()


def _owned_row_count(db_connection, suffix: str) -> int:
    pattern = f"%{suffix}%"
    queries = (
        "SELECT count(*) FROM farm.model_registry WHERE model_id LIKE %s",
        "SELECT count(*) FROM farm.runs WHERE run_id LIKE %s",
        "SELECT count(*) FROM farm.tasks WHERE task_id LIKE %s",
        "SELECT count(*) FROM farm.generations WHERE generation_id LIKE %s",
        "SELECT count(*) FROM farm.validation_results WHERE validation_id LIKE %s",
        "SELECT count(*) FROM farm.samples WHERE sample_id LIKE %s",
        "SELECT count(*) FROM farm.embeddings WHERE embedding_id LIKE %s",
    )
    total = 0
    with db_connection.cursor() as cursor:
        for query in queries:
            cursor.execute(query, (pattern,))
            total += cursor.fetchone()[0]
    db_connection.commit()
    return total


def test_repository_lifecycle_resume_and_idempotence(db_connection) -> None:
    suffix = uuid4().hex
    model_id = f"_tz08_model_{suffix}"
    counters_before = COUNTERS_FILE.read_bytes()
    provider = FakeIDProvider(suffix)
    repository = SelectorRepository(db_connection, provider)
    _cleanup(db_connection, suffix)

    try:
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO farm.model_registry (model_id, model_type, resource_class, status)
                VALUES (%s, 'ml', 'classical_ml', 'raw_candidate')
                """,
                (model_id,),
            )
        db_connection.commit()

        run = repository.create_run(
            model_id=model_id,
            dataset_id=f"_tz08_dataset_{suffix}",
            config_id="ml_v001",
            total_items=1,
        )
        task = repository.create_task(
            run_id=run.run_id,
            task_type="integration",
            input_payload={"value": 1},
        )

        with pytest.raises(LifecycleError):
            repository.transition_task(task.task_id, TaskStatus.ACCEPTED)

        repository.transition_run(run.run_id, RunStatus.RUNNING)
        repository.transition_task(task.task_id, TaskStatus.GENERATING)

        generation = repository.create_generation_once(
            task_id=task.task_id,
            run_id=run.run_id,
            model_id=model_id,
            raw_output='{"decision":"healthy"}',
            parsed_output={"decision": "healthy"},
        )
        assert (
            repository.create_generation_once(
                task_id=task.task_id,
                run_id=run.run_id,
                model_id=model_id,
                raw_output="ignored",
            ).generation_id
            == generation.generation_id
        )
        assert (
            resume_stage(repository.list_resume_items(run.run_id)[0].evidence)
            is ResumeStage.VALIDATE
        )

        repository.transition_task(task.task_id, TaskStatus.VALIDATING)
        validation = repository.create_validation_once(
            generation_id=generation.generation_id,
            validator_version="tz08_task6",
            is_valid=True,
            score=1.0,
        )
        assert (
            repository.create_validation_once(
                generation_id=generation.generation_id,
                validator_version="ignored",
                is_valid=False,
            ).validation_id
            == validation.validation_id
        )

        sample = repository.create_sample_once(
            validation_id=validation.validation_id,
            task_id=task.task_id,
            generation_id=generation.generation_id,
            run_id=run.run_id,
            model_id=model_id,
            dataset_id=f"_tz08_dataset_{suffix}",
            status="accepted",
            completion='{"decision":"healthy"}',
            selector_version="tz08_task6",
        )
        assert (
            repository.create_sample_once(
                validation_id=validation.validation_id,
                task_id=task.task_id,
                generation_id=generation.generation_id,
                run_id=run.run_id,
                model_id=model_id,
                dataset_id=f"_tz08_dataset_{suffix}",
                status="rejected",
                completion="ignored",
                selector_version="ignored",
            ).sample_id
            == sample.sample_id
        )

        embedding = repository.create_embedding_once(
            source_type="generation",
            source_id=generation.generation_id,
            model_id="tz08_task6_vector",
            values=[1.0] + [0.0] * 767,
        )
        assert (
            repository.create_embedding_once(
                source_type="generation",
                source_id=generation.generation_id,
                model_id="ignored",
                values=[0.0] * 768,
            ).embedding_id
            == embedding.embedding_id
        )

        resume_item = repository.list_resume_items(run.run_id)[0]
        assert resume_stage(resume_item.evidence) is ResumeStage.COMPLETE

        with pytest.raises(RepositoryError):
            repository.update_run_counters(run.run_id, accepted=1)
        counters = repository.update_run_counters(run.run_id, processed=1, accepted=1)
        assert counters.processed == counters.accepted == 1

        repository.transition_task(task.task_id, TaskStatus.ACCEPTED)
        repository.transition_run(run.run_id, RunStatus.COMPLETED)

        db_connection.rollback()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT count(*) FROM farm.generations WHERE task_id = %s),
                    (SELECT count(*) FROM farm.validation_results WHERE generation_id = %s),
                    (SELECT count(*) FROM farm.samples WHERE generation_id = %s),
                    (SELECT count(*) FROM farm.embeddings WHERE source_id = %s),
                    (SELECT status FROM farm.runs WHERE run_id = %s),
                    (SELECT status FROM farm.tasks WHERE task_id = %s)
                """,
                (
                    task.task_id,
                    generation.generation_id,
                    generation.generation_id,
                    generation.generation_id,
                    run.run_id,
                    task.task_id,
                ),
            )
            assert cursor.fetchone() == (1, 1, 1, 1, "completed", "accepted")
        db_connection.commit()
        assert provider.counts["generation"] == 1
        assert provider.counts["validation"] == 1
        assert provider.counts["sample"] == 1
        assert provider.counts["embedding"] == 1
        assert COUNTERS_FILE.read_bytes() == counters_before
    finally:
        _cleanup(db_connection, suffix)

    assert _owned_row_count(db_connection, suffix) == 0


def test_no_tz08_rows_remain(db_connection) -> None:
    queries = {
        "model_registry": "SELECT count(*) FROM farm.model_registry WHERE model_id LIKE '_tz08_%'",
        "runs": "SELECT count(*) FROM farm.runs WHERE run_id LIKE '_tz08_%'",
        "tasks": "SELECT count(*) FROM farm.tasks WHERE task_id LIKE '_tz08_%'",
        "generations": "SELECT count(*) FROM farm.generations WHERE generation_id LIKE '_tz08_%'",
        "validation_results": (
            "SELECT count(*) FROM farm.validation_results WHERE validation_id LIKE '_tz08_%'"
        ),
        "samples": "SELECT count(*) FROM farm.samples WHERE sample_id LIKE '_tz08_%'",
        "embeddings": "SELECT count(*) FROM farm.embeddings WHERE embedding_id LIKE '_tz08_%'",
    }
    counts = {}
    with db_connection.cursor() as cursor:
        for table, query in queries.items():
            cursor.execute(query)
            counts[table] = cursor.fetchone()[0]
    db_connection.commit()

    assert counts == {table: 0 for table in queries}
