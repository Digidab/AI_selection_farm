from uuid import uuid4

import pytest


def test_pgvector_cosine_similarity_returns_nearest_candidate(db_connection) -> None:
    suffix = uuid4().hex
    embedding_a_id = f"_tz07_embedding_a_{suffix}"
    embedding_b_id = f"_tz07_embedding_b_{suffix}"

    vector_a_values = [1.0] + [0.0] * 767
    vector_b_values = [0.0, 1.0] + [0.0] * 766
    vector_a = f"[{','.join(str(value) for value in vector_a_values)}]"
    vector_b = f"[{','.join(str(value) for value in vector_b_values)}]"

    assert len(vector_a_values) == 768
    assert len(vector_b_values) == 768

    with db_connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO farm.embeddings (
                embedding_id, source_type, source_id, embedding_model_id,
                embedding
            )
            VALUES (%s, %s, %s, %s, %s::vector)
            """,
            (
                (
                    embedding_a_id,
                    "generation",
                    f"_tz07_source_a_{suffix}",
                    "tz07_integration",
                    vector_a,
                ),
                (
                    embedding_b_id,
                    "generation",
                    f"_tz07_source_b_{suffix}",
                    "tz07_integration",
                    vector_b,
                ),
            ),
        )

        cursor.execute(
            """
            SELECT
                candidate.embedding_id,
                candidate.embedding <=> query.embedding AS cosine_distance
            FROM farm.embeddings AS candidate
            CROSS JOIN (SELECT %s::vector AS embedding) AS query
            WHERE candidate.embedding_id IN (%s, %s)
            ORDER BY candidate.embedding <=> query.embedding
            LIMIT 1
            """,
            (vector_a, embedding_a_id, embedding_b_id),
        )
        nearest_candidate = cursor.fetchone()

    assert nearest_candidate is not None
    assert nearest_candidate[0] == embedding_a_id
    assert nearest_candidate[1] == pytest.approx(0.0, abs=1e-6)
