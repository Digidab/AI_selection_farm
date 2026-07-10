import json
from uuid import uuid4


def test_runtime_core_round_trip(db_connection) -> None:
    suffix = uuid4().hex
    model_id = f"_tz07_model_{suffix}"
    run_id = f"_tz07_run_{suffix}"
    task_id = f"_tz07_task_{suffix}"
    generation_id = f"_tz07_generation_{suffix}"
    validation_id = f"_tz07_validation_{suffix}"
    sample_id = f"_tz07_sample_{suffix}"
    dataset_id = f"_tz07_dataset_{suffix}"
    config_id = f"_tz07_config_{suffix}"

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO farm.model_registry (
                model_id, model_type, resource_class, status
            )
            VALUES (%s, %s, %s, %s)
            """,
            (model_id, "llm", "0.6b_1b", "raw_candidate"),
        )

        cursor.execute(
            """
            INSERT INTO farm.runs (
                run_id, run_type, status, model_id, dataset_id, config_id,
                total_items, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                run_id,
                "smoke_test",
                "running",
                model_id,
                dataset_id,
                config_id,
                1,
                json.dumps({"tz": "07", "kind": "runtime_round_trip"}),
            ),
        )

        cursor.execute(
            """
            INSERT INTO farm.tasks (
                task_id, run_id, task_type, prompt, input_payload,
                expected_schema, status, priority
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """,
            (
                task_id,
                run_id,
                "integration_test",
                "Return JSON",
                json.dumps({"input": "ping"}),
                json.dumps({"type": "object"}),
                "pending",
                0,
            ),
        )

        cursor.execute(
            """
            INSERT INTO farm.generations (
                generation_id, task_id, run_id, model_id, temperature,
                raw_output, parsed_output, latency_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                generation_id,
                task_id,
                run_id,
                model_id,
                0.1,
                json.dumps({"answer": "pong"}),
                json.dumps({"answer": "pong"}),
                1,
            ),
        )

        cursor.execute(
            """
            INSERT INTO farm.validation_results (
                validation_id, generation_id, validator_version, is_valid,
                score, validation_details
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                validation_id,
                generation_id,
                "tz07_integration",
                True,
                1.0,
                json.dumps({"ok": True}),
            ),
        )

        cursor.execute(
            """
            INSERT INTO farm.samples (
                sample_id, validation_result_id, task_id, generation_id,
                run_id, model_id, dataset_id, status, prompt, completion,
                score, selector_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                sample_id,
                validation_id,
                task_id,
                generation_id,
                run_id,
                model_id,
                dataset_id,
                "accepted",
                "Return JSON",
                json.dumps({"answer": "pong"}),
                1.0,
                "tz07_integration",
            ),
        )

        cursor.execute(
            """
            SELECT
                run.run_id,
                run.config_id,
                run.status,
                run.total_items,
                task.task_id,
                task.status,
                generation.generation_id,
                validation.validation_id,
                validation.is_valid,
                sample.sample_id,
                sample.status
            FROM farm.model_registry AS model
            JOIN farm.runs AS run
              ON run.model_id = model.model_id
            JOIN farm.tasks AS task
              ON task.run_id = run.run_id
            JOIN farm.generations AS generation
              ON generation.task_id = task.task_id
             AND generation.run_id = run.run_id
             AND generation.model_id = model.model_id
            JOIN farm.validation_results AS validation
              ON validation.generation_id = generation.generation_id
            JOIN farm.samples AS sample
              ON sample.validation_result_id = validation.validation_id
             AND sample.task_id = task.task_id
             AND sample.generation_id = generation.generation_id
             AND sample.run_id = run.run_id
             AND sample.model_id = model.model_id
            WHERE model.model_id = %s
            """,
            (model_id,),
        )
        round_trip = cursor.fetchone()

    assert round_trip == (
        run_id,
        config_id,
        "running",
        1,
        task_id,
        "pending",
        generation_id,
        validation_id,
        True,
        sample_id,
        "accepted",
    )
