from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_NAMES = (
    "001_init.sql",
    "002_add_pgvector.sql",
    "003_model_registry.sql",
    "004_runtime_core.sql",
    "005_embeddings.sql",
    "006_indexes.sql",
)

EXPECTED_TABLE_NAMES = frozenset(
    {
        "embeddings",
        "generations",
        "model_registry",
        "runs",
        "samples",
        "tasks",
        "validation_results",
    }
)

EXPECTED_INDEX_NAMES = frozenset(
    {
        "embeddings_embedding_id_key",
        "embeddings_pkey",
        "generations_generation_id_key",
        "generations_pkey",
        "idx_embeddings_embedding_hnsw",
        "idx_generations_model_id",
        "idx_generations_run_id",
        "idx_generations_task_id",
        "idx_model_registry_status",
        "idx_runs_run_type",
        "idx_runs_started_at",
        "idx_runs_status",
        "idx_samples_dataset_id",
        "idx_samples_model_id",
        "idx_samples_run_id",
        "idx_samples_status",
        "idx_tasks_run_id",
        "idx_tasks_status",
        "idx_validation_results_failure_code",
        "idx_validation_results_generation_id",
        "idx_validation_results_is_valid",
        "model_registry_model_id_key",
        "model_registry_pkey",
        "runs_pkey",
        "runs_run_id_key",
        "samples_pkey",
        "samples_sample_id_key",
        "tasks_pkey",
        "tasks_task_id_key",
        "validation_results_pkey",
        "validation_results_validation_id_key",
    }
)


def test_schema_snapshot_matches_migrations() -> None:
    schema_lines = (PROJECT_ROOT / "db" / "schema.sql").read_text().splitlines(keepends=True)
    schema_body = "".join(schema_lines[2:])
    migrations_body = "".join(
        (PROJECT_ROOT / "db" / "migrations" / name).read_text() for name in MIGRATION_NAMES
    )

    assert schema_body == migrations_body


def test_postgres_connection_and_pgvector(db_connection) -> None:
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        current_database = cursor.fetchone()

        cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        vector_extension = cursor.fetchone()

        cursor.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_opclass AS operator_class
                JOIN pg_am AS access_method
                  ON access_method.oid = operator_class.opcmethod
                WHERE access_method.amname = 'hnsw'
                  AND operator_class.opcname = 'vector_cosine_ops'
            )
            """)
        cosine_hnsw_capability = cursor.fetchone()

    assert current_database is not None
    assert current_database[0] == db_connection.info.dbname
    assert vector_extension is not None
    assert vector_extension[0]
    assert cosine_hnsw_capability == (True,)


def test_v001_catalog_contract(db_connection) -> None:
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'farm'")
        actual_table_names = frozenset(row[0] for row in cursor.fetchall())

        cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'farm'")
        actual_index_names = frozenset(row[0] for row in cursor.fetchall())

        cursor.execute("""
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'farm'
              AND indexname = 'idx_embeddings_embedding_hnsw'
            """)
        hnsw_index = cursor.fetchone()

    assert actual_table_names == EXPECTED_TABLE_NAMES
    assert actual_index_names == EXPECTED_INDEX_NAMES
    assert hnsw_index is not None
    assert "USING hnsw" in hnsw_index[0]
    assert "vector_cosine_ops" in hnsw_index[0]
