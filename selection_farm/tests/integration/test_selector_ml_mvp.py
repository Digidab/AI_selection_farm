from uuid import uuid4

import orjson

from services.selector.app.ml.deduplicator import PostgresAcceptedMLInputLookup


def _canonical(features: dict[str, object]) -> str:
    return orjson.dumps(features, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def _insert_sample(
    db_connection,
    *,
    prefix: str,
    model_type: str,
    dataset_id: str,
    status: str,
    features: dict[str, object],
) -> str:
    model_id = f"{prefix}_model"
    run_id = f"{prefix}_run"
    task_id = f"{prefix}_task"
    generation_id = f"{prefix}_generation"
    validation_id = f"{prefix}_validation"
    sample_id = f"{prefix}_sample"
    payload = _canonical(features)
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO farm.model_registry (model_id, model_type, resource_class, status)
            VALUES (%s, %s, %s, 'raw_candidate')
            """,
            (model_id, model_type, "classical_ml" if model_type == "ml" else "0.6b_1b"),
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
            INSERT INTO farm.tasks (task_id, run_id, task_type, input_payload, status)
            VALUES (%s, %s, 'ml_validation_integration', %s::jsonb, %s)
            """,
            (task_id, run_id, payload, status),
        )
        cursor.execute(
            """
            INSERT INTO farm.generations (
                generation_id, task_id, run_id, model_id, raw_output, parsed_output
            )
            VALUES (%s, %s, %s, %s, '{"prediction":"healthy"}',
                    '{"prediction":"healthy"}'::jsonb)
            """,
            (generation_id, task_id, run_id, model_id),
        )
        cursor.execute(
            """
            INSERT INTO farm.validation_results (
                validation_id, generation_id, validator_version, is_valid,
                failure_code, failure_reason
            )
            VALUES (%s, %s, 'tz08_task10', %s, %s, %s)
            """,
            (
                validation_id,
                generation_id,
                status == "accepted",
                None if status == "accepted" else "logic_error",
                None if status == "accepted" else "fixture rejection",
            ),
        )
        cursor.execute(
            """
            INSERT INTO farm.samples (
                sample_id, validation_result_id, task_id, generation_id,
                run_id, model_id, dataset_id, status, completion,
                failure_code, failure_reason, selector_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    '{"prediction":"healthy"}', %s, %s, 'tz08_task10')
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
                None if status == "accepted" else "logic_error",
                None if status == "accepted" else "fixture rejection",
            ),
        )
    db_connection.commit()
    return sample_id


def _cleanup(db_connection, prefix: str) -> None:
    pattern = f"{prefix}%"
    with db_connection.cursor() as cursor:
        cursor.execute("DELETE FROM farm.samples WHERE sample_id LIKE %s", (pattern,))
        cursor.execute(
            "DELETE FROM farm.validation_results WHERE validation_id LIKE %s", (pattern,)
        )
        cursor.execute("DELETE FROM farm.generations WHERE generation_id LIKE %s", (pattern,))
        cursor.execute("DELETE FROM farm.tasks WHERE task_id LIKE %s", (pattern,))
        cursor.execute("DELETE FROM farm.runs WHERE run_id LIKE %s", (pattern,))
        cursor.execute("DELETE FROM farm.model_registry WHERE model_id LIKE %s", (pattern,))
    db_connection.commit()


def test_exact_lookup_is_limited_to_accepted_same_dataset_ml_inputs(db_connection) -> None:
    prefix = f"_tz08_task10_{uuid4().hex}"
    dataset_id = f"{prefix}_dataset"
    accepted_features = {"latency_ms": 12.5, "error_count": 0, "is_cached": True}
    excluded_features = {"latency_ms": 99.0, "error_count": 1, "is_cached": False}
    _cleanup(db_connection, prefix)

    try:
        expected_sample = _insert_sample(
            db_connection,
            prefix=f"{prefix}_eligible",
            model_type="ml",
            dataset_id=dataset_id,
            status="accepted",
            features=accepted_features,
        )
        _insert_sample(
            db_connection,
            prefix=f"{prefix}_rejected",
            model_type="ml",
            dataset_id=dataset_id,
            status="rejected",
            features=excluded_features,
        )
        _insert_sample(
            db_connection,
            prefix=f"{prefix}_other_dataset",
            model_type="ml",
            dataset_id=f"{prefix}_elsewhere",
            status="accepted",
            features=excluded_features,
        )
        _insert_sample(
            db_connection,
            prefix=f"{prefix}_other_branch",
            model_type="llm",
            dataset_id=dataset_id,
            status="accepted",
            features=excluded_features,
        )
        lookup = PostgresAcceptedMLInputLookup(db_connection)

        duplicate = lookup.find_duplicate(
            dataset_id=dataset_id,
            canonical_input=_canonical({"is_cached": True, "error_count": 0, "latency_ms": 12.5}),
        )
        excluded = lookup.find_duplicate(
            dataset_id=dataset_id,
            canonical_input=_canonical(excluded_features),
        )

        assert duplicate is not None
        assert duplicate.sample_id == expected_sample
        assert excluded is None

        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM farm.embeddings
                WHERE embedding_id LIKE %s OR source_id LIKE %s
                """,
                (f"{prefix}%", f"{prefix}%"),
            )
            assert cursor.fetchone()[0] == 0
        db_connection.commit()
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
                (SELECT count(*) FROM farm.embeddings
                 WHERE embedding_id LIKE %s OR source_id LIKE %s)
            """,
            (f"{prefix}%",) * 8,
        )
        assert cursor.fetchone() == (0, 0, 0, 0, 0, 0, 0)
    db_connection.commit()
