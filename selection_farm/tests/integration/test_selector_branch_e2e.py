from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import joblib
import orjson
import pytest
from sklearn.dummy import DummyClassifier

from services.selector.app.core.db import SelectorRepository
from services.selector.app.core.export import (
    AtomicExportWriter,
    BranchExportRequest,
    ExportCoordinator,
    PostgresExportSource,
)
from services.selector.app.core.pipeline import PipelineError, SelectorPipeline
from services.selector.app.llm.config import load_llm_config
from services.selector.app.llm.exporter import LLMExportSerializer
from services.selector.app.llm.main import build_branch as build_llm_branch
from services.selector.app.llm.registry import build_reference_registry as build_llm_registry
from services.selector.app.llm.schemas import (
    CapabilityDescriptor,
    ComponentKind,
    EmbeddingResult,
    GenerationResult,
)
from services.selector.app.ml.config import load_ml_config
from services.selector.app.ml.exporter import MLExportSerializer
from services.selector.app.ml.main import build_branch as build_ml_branch

COUNTERS_FILE = Path(__file__).resolve().parents[2] / "configs/id_mapping/id_counters.json"


class FakeIDProvider:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.counts: defaultdict[str, int] = defaultdict(int)

    def _issue(self, kind: str) -> str:
        self.counts[kind] += 1
        return f"{self.prefix}_{kind}_{self.counts[kind]}"

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


class MockLLMRuntime:
    descriptor = CapabilityDescriptor(
        component_id="ollama",
        kind=ComponentKind.RUNTIME,
        capabilities=frozenset({"generation", "embedding", "structured_json"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    def __init__(self) -> None:
        self.generate_calls = 0
        self.embed_calls = 0

    def generate(self, prepared_input, settings) -> GenerationResult:
        self.generate_calls += 1
        return GenerationResult(
            model=settings.model,
            text='{"reason":"fixture accepted","status":"nominal"}',
            done=True,
        )

    def embed(self, texts, *, model, expected_dimension) -> EmbeddingResult:
        self.embed_calls += 1
        assert expected_dimension == 768
        return EmbeddingResult(
            model=model,
            vectors=tuple((1.0, *([0.0] * 767)) for _ in texts),
        )


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


def _owned_counts(db_connection, prefix: str) -> tuple[int, ...]:
    pattern = f"{prefix}%"
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
            (pattern,) * 8,
        )
        counts = cursor.fetchone()
    db_connection.commit()
    return counts


def _write_jsonl(path: Path, value: dict) -> None:
    path.write_bytes(orjson.dumps(value) + b"\n")


def _insert_models(db_connection, llm_model_id: str, ml_model_id: str) -> None:
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO farm.model_registry (model_id, model_type, resource_class, status)
            VALUES (%s, 'llm', '0.6b_1b', 'raw_candidate'),
                   (%s, 'ml', 'classical_ml', 'raw_candidate')
            """,
            (llm_model_id, ml_model_id),
        )
    db_connection.commit()


def test_assembled_branches_persist_export_isolate_and_cleanup(
    db_connection,
    tmp_path: Path,
) -> None:
    prefix = f"_tz08_task13_{uuid4().hex}"
    llm_model_id = f"{prefix}_llm_model"
    ml_model_id = f"{prefix}_ml_model"
    llm_dataset_id = f"{prefix}_llm_dataset"
    ml_dataset_id = f"{prefix}_ml_dataset"
    counters_before = COUNTERS_FILE.read_bytes()
    provider = FakeIDProvider(prefix)
    repository = SelectorRepository(db_connection, provider)
    _cleanup(db_connection, prefix)

    llm_tasks = tmp_path / f"{prefix}_llm_tasks.jsonl"
    ml_tasks = tmp_path / f"{prefix}_ml_tasks.jsonl"
    artifact = tmp_path / f"{prefix}_model.joblib"
    _write_jsonl(
        llm_tasks,
        {
            "task_id": f"{prefix}_llm_source",
            "prompt": "Return the fixture object",
            "expected_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["status", "reason"],
                "properties": {
                    "status": {"const": "nominal"},
                    "reason": {"type": "string", "minLength": 1},
                },
            },
        },
    )
    _write_jsonl(
        ml_tasks,
        {
            "task_id": f"{prefix}_ml_source",
            "features": {"latency_ms": 12.5, "error_count": 0, "is_cached": True},
        },
    )
    estimator = DummyClassifier(strategy="constant", constant="healthy")
    estimator.fit([[0.0, 0, False], [1.0, 1, True]], ["healthy", "attention"])
    joblib.dump(estimator, artifact)

    llm_settings = load_llm_config().llm.model_copy(
        update={
            "model_id": llm_model_id,
            "dataset_id": llm_dataset_id,
            "config_id": f"{prefix}_llm_config",
            "tasks_path": llm_tasks,
        }
    )
    ml_settings = load_ml_config().ml.model_copy(
        update={
            "model_id": ml_model_id,
            "dataset_id": ml_dataset_id,
            "config_id": f"{prefix}_ml_config",
            "tasks_path": ml_tasks,
            "artifact_path": artifact,
        }
    )
    runtime = MockLLMRuntime()
    llm_branch = build_llm_branch(
        llm_settings,
        db_connection,
        registry=build_llm_registry(runtime),
    )
    ml_branch = build_ml_branch(ml_settings, db_connection)

    try:
        _insert_models(db_connection, llm_model_id, ml_model_id)
        SelectorPipeline(repository).run(llm_branch)
        SelectorPipeline(repository).run(ml_branch)

        assert runtime.generate_calls == runtime.embed_calls == 1
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT model_id, status, total_items, processed_items,
                       accepted_items, rejected_items, failed_items
                FROM farm.runs WHERE run_id LIKE %s ORDER BY model_id
                """,
                (f"{prefix}%",),
            )
            assert cursor.fetchall() == [
                (llm_model_id, "completed", 1, 1, 1, 0, 0),
                (ml_model_id, "completed", 1, 1, 1, 0, 0),
            ]
            cursor.execute(
                """
                SELECT model.model_type, sample.dataset_id, sample.status
                FROM farm.samples AS sample
                JOIN farm.model_registry AS model ON model.model_id = sample.model_id
                WHERE sample.sample_id LIKE %s ORDER BY model.model_type
                """,
                (f"{prefix}%",),
            )
            assert cursor.fetchall() == [
                ("llm", llm_dataset_id, "accepted"),
                ("ml", ml_dataset_id, "accepted"),
            ]
            cursor.execute(
                """
                SELECT model.model_type, count(embedding.embedding_id)
                FROM farm.model_registry AS model
                LEFT JOIN farm.generations AS generation ON generation.model_id = model.model_id
                LEFT JOIN farm.embeddings AS embedding
                  ON embedding.source_id = generation.generation_id
                WHERE model.model_id IN (%s, %s)
                GROUP BY model.model_type ORDER BY model.model_type
                """,
                (llm_model_id, ml_model_id),
            )
            assert cursor.fetchall() == [("llm", 1), ("ml", 0)]
        db_connection.commit()

        targets = {
            "llm_accepted": tmp_path / f"{prefix}_llm_accepted.jsonl",
            "llm_rejected": tmp_path / f"{prefix}_llm_rejected.jsonl",
            "ml_accepted": tmp_path / f"{prefix}_ml_accepted.jsonl",
            "ml_rejected": tmp_path / f"{prefix}_ml_rejected.jsonl",
        }
        coordinator = ExportCoordinator(PostgresExportSource(db_connection), AtomicExportWriter())
        requests = (
            BranchExportRequest(
                dataset_id=llm_dataset_id,
                serializer=LLMExportSerializer(),
                accepted_path=targets["llm_accepted"],
                rejected_path=targets["llm_rejected"],
            ),
            BranchExportRequest(
                dataset_id=ml_dataset_id,
                serializer=MLExportSerializer(),
                accepted_path=targets["ml_accepted"],
                rejected_path=targets["ml_rejected"],
            ),
        )
        summaries = coordinator.export_all(requests)
        first_bytes = {name: path.read_bytes() for name, path in targets.items()}
        assert [
            (item.branch_id, item.accepted_count, item.rejected_count) for item in summaries
        ] == [
            ("llm", 1, 0),
            ("ml", 1, 0),
        ]
        assert orjson.loads(first_bytes["llm_accepted"])["sample_type"] == "llm"
        assert orjson.loads(first_bytes["ml_accepted"])["sample_type"] == "ml"
        assert first_bytes["llm_rejected"] == first_bytes["ml_rejected"] == b""
        coordinator.export_all(requests)
        assert {name: path.read_bytes() for name, path in targets.items()} == first_bytes

        runs_before_mismatch = _owned_counts(db_connection, prefix)[1]
        wrong_branch = build_llm_branch(
            llm_settings.model_copy(update={"model_id": ml_model_id}),
            db_connection,
            registry=build_llm_registry(MockLLMRuntime()),
        )
        with pytest.raises(PipelineError, match="Model type mismatch"):
            SelectorPipeline(repository).run(wrong_branch)
        assert _owned_counts(db_connection, prefix)[1] == runs_before_mismatch
        assert COUNTERS_FILE.read_bytes() == counters_before
    finally:
        _cleanup(db_connection, prefix)

    assert _owned_counts(db_connection, prefix) == (0, 0, 0, 0, 0, 0, 0)
    assert COUNTERS_FILE.read_bytes() == counters_before
