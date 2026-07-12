from uuid import uuid4

import pytest

from services.selector.app.llm.evaluators.semantic_dedup import (
    PostgresAcceptedEmbeddingLookup,
)
from services.selector.app.llm.persistence import (
    LLMEmbeddingPersistenceError,
    LLMEmbeddingRepository,
)


class FakeEmbeddingIDProvider:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.calls = 0

    def issue_embedding_id(self) -> str:
        self.calls += 1
        return f"{self.prefix}_embedding_{self.calls}"


def _vector(axis: int) -> list[float]:
    values = [0.0] * 768
    values[axis] = 1.0
    return values


def _literal(values: list[float]) -> str:
    return f"[{','.join(str(value) for value in values)}]"


def _insert_accepted_sample(
    db_connection,
    *,
    prefix: str,
    model_type: str,
    dataset_id: str,
    embedding_model_id: str,
    values: list[float],
) -> str:
    model_id = f"{prefix}_model"
    run_id = f"{prefix}_run"
    task_id = f"{prefix}_task"
    generation_id = f"{prefix}_generation"
    validation_id = f"{prefix}_validation"
    sample_id = f"{prefix}_sample"
    embedding_id = f"{prefix}_embedding"
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO farm.model_registry (model_id, model_type, resource_class, status)
            VALUES (%s, %s, %s, 'raw_candidate')
            """,
            (model_id, model_type, "0.6b_1b" if model_type == "llm" else "classical_ml"),
        )
        cursor.execute(
            """
            INSERT INTO farm.runs (run_id, run_type, status, model_id, dataset_id)
            VALUES (%s, 'selector', 'completed', %s, %s)
            """,
            (run_id, model_id, dataset_id),
        )
        cursor.execute(
            """
            INSERT INTO farm.tasks (task_id, run_id, task_type, status)
            VALUES (%s, %s, 'llm_evaluator_integration', 'accepted')
            """,
            (task_id, run_id),
        )
        cursor.execute(
            """
            INSERT INTO farm.generations (
                generation_id, task_id, run_id, model_id, raw_output, parsed_output
            )
            VALUES (%s, %s, %s, %s, '{"ok":true}', '{"ok":true}'::jsonb)
            """,
            (generation_id, task_id, run_id, model_id),
        )
        cursor.execute(
            """
            INSERT INTO farm.validation_results (
                validation_id, generation_id, validator_version, is_valid
            )
            VALUES (%s, %s, 'tz08_task8', true)
            """,
            (validation_id, generation_id),
        )
        cursor.execute(
            """
            INSERT INTO farm.samples (
                sample_id, validation_result_id, task_id, generation_id,
                run_id, model_id, dataset_id, status, completion, selector_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'accepted', '{"ok":true}', 'tz08_task8')
            """,
            (sample_id, validation_id, task_id, generation_id, run_id, model_id, dataset_id),
        )
        cursor.execute(
            """
            INSERT INTO farm.embeddings (
                embedding_id, source_type, source_id, embedding_model_id, embedding
            )
            VALUES (%s, 'generation', %s, %s, %s::vector)
            """,
            (embedding_id, generation_id, embedding_model_id, _literal(values)),
        )
    db_connection.commit()
    return sample_id


def _cleanup(db_connection, prefix: str) -> None:
    pattern = f"{prefix}%"
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


def test_pgvector_lookup_is_limited_to_accepted_same_dataset_llm_samples(
    db_connection,
) -> None:
    prefix = f"_tz08_task8_{uuid4().hex}"
    dataset_id = f"{prefix}_dataset"
    embedding_model_id = "nomic-embed-text"
    _cleanup(db_connection, prefix)

    try:
        expected_sample = _insert_accepted_sample(
            db_connection,
            prefix=f"{prefix}_eligible",
            model_type="llm",
            dataset_id=dataset_id,
            embedding_model_id=embedding_model_id,
            values=_vector(0),
        )
        _insert_accepted_sample(
            db_connection,
            prefix=f"{prefix}_ml_excluded",
            model_type="ml",
            dataset_id=dataset_id,
            embedding_model_id=embedding_model_id,
            values=_vector(1),
        )
        _insert_accepted_sample(
            db_connection,
            prefix=f"{prefix}_dataset_excluded",
            model_type="llm",
            dataset_id=f"{prefix}_other_dataset",
            embedding_model_id=embedding_model_id,
            values=_vector(1),
        )
        lookup = PostgresAcceptedEmbeddingLookup(db_connection)

        same_vector = lookup.find_nearest(
            dataset_id=dataset_id,
            embedding_model_id=embedding_model_id,
            candidate=_vector(0),
        )
        excluded_vector = lookup.find_nearest(
            dataset_id=dataset_id,
            embedding_model_id=embedding_model_id,
            candidate=_vector(1),
        )
        wrong_model_space = lookup.find_nearest(
            dataset_id=dataset_id,
            embedding_model_id="other-embedding-model",
            candidate=_vector(0),
        )

        assert same_vector is not None
        assert same_vector.sample_id == expected_sample
        assert same_vector.cosine_distance == pytest.approx(0.0, abs=1e-6)
        assert excluded_vector is not None
        assert excluded_vector.sample_id == expected_sample
        assert excluded_vector.cosine_distance == pytest.approx(1.0, abs=1e-6)
        assert wrong_model_space is None
    finally:
        _cleanup(db_connection, prefix)

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM farm.model_registry WHERE model_id LIKE %s),
                (SELECT count(*) FROM farm.runs WHERE run_id LIKE %s),
                (SELECT count(*) FROM farm.tasks WHERE task_id LIKE %s),
                (SELECT count(*) FROM farm.generations WHERE generation_id LIKE %s),
                (SELECT count(*) FROM farm.validation_results WHERE validation_id LIKE %s),
                (SELECT count(*) FROM farm.samples WHERE sample_id LIKE %s),
                (SELECT count(*) FROM farm.embeddings WHERE embedding_id LIKE %s)
            """,
            (f"{prefix}%",) * 7,
        )
        assert cursor.fetchone() == (0, 0, 0, 0, 0, 0, 0)
    db_connection.commit()


def test_llm_owned_embedding_repository_is_idempotent_and_dimension_strict(
    db_connection,
) -> None:
    prefix = f"_tz08_llm_persistence_{uuid4().hex}"
    generation_id = f"{prefix}_generation"
    provider = FakeEmbeddingIDProvider(prefix)
    repository = LLMEmbeddingRepository(db_connection, provider)
    _cleanup(db_connection, prefix)

    try:
        created = repository.create_once(
            generation_id=generation_id,
            model_id="nomic-embed-text",
            values=_vector(0),
            metadata={"branch_id": "llm"},
        )
        repeated = repository.create_once(
            generation_id=generation_id,
            model_id="nomic-embed-text",
            values=_vector(1),
        )

        assert repeated.embedding_id == created.embedding_id
        assert provider.calls == 1
        with pytest.raises(LLMEmbeddingPersistenceError, match="model identity conflicts"):
            repository.create_once(
                generation_id=generation_id,
                model_id="other-embedding-model",
                values=_vector(1),
            )
        assert provider.calls == 1
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT source_type, source_id, embedding_model_id, metadata
                FROM farm.embeddings WHERE embedding_id = %s
                """,
                (created.embedding_id,),
            )
            assert cursor.fetchone() == (
                "generation",
                generation_id,
                "nomic-embed-text",
                {"branch_id": "llm"},
            )
        db_connection.commit()

        with pytest.raises(LLMEmbeddingPersistenceError, match="exactly 768"):
            repository.create_once(
                generation_id=f"{prefix}_invalid_generation",
                model_id="nomic-embed-text",
                values=[0.0] * 767,
            )
        assert provider.calls == 1
    finally:
        _cleanup(db_connection, prefix)
