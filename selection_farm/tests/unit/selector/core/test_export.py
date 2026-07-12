import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from services.selector.app.core.export import (
    AtomicExportWriter,
    BranchExportRequest,
    ExportCoordinator,
    ExportError,
    ExportRow,
    connect_export_database,
)
from services.selector.app.core.config import load_common_config


def _row(branch: str, status: str, sample_id: str) -> ExportRow:
    return ExportRow(
        sample_id=sample_id,
        sample_status=status,
        dataset_id=f"{branch}_dataset",
        selector_version="selector_v001",
        sample_score=1.0 if status == "accepted" else None,
        sample_failure_code=None if status == "accepted" else "logic_error",
        sample_failure_reason=None if status == "accepted" else "rejected fixture",
        sample_metadata={},
        sample_created_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        task_id=f"{sample_id}_task",
        task_input_payload={"value": 1},
        task_expected_schema=None,
        generation_id=f"{sample_id}_generation",
        raw_output='{"value":1}',
        parsed_output={"value": 1},
        generation_metadata={},
        validation_id=f"{sample_id}_validation",
        validator_version="v001",
        is_valid=status == "accepted",
        validation_score=1.0 if status == "accepted" else None,
        validation_failure_code=None if status == "accepted" else "logic_error",
        validation_failure_reason=None if status == "accepted" else "rejected fixture",
        validation_details={"checks": ["fixture"]},
        run_id=f"{sample_id}_run",
        config_id=f"{branch}_v001",
        model_id=f"{branch}_model",
        model_name=f"{branch} fixture",
        model_type=branch,
        base_model="fixture",
        completion='{"value":1}',
    )


class FakeSource:
    def __init__(self, rows_by_branch):
        self.rows_by_branch = rows_by_branch

    def load_rows(self, *, branch_id, dataset_id):
        assert dataset_id == f"{branch_id}_dataset"
        return tuple(self.rows_by_branch[branch_id])


class DummySerializer:
    def __init__(self, branch_id: str) -> None:
        self.branch_id = branch_id

    def serialize(self, row):
        return {
            "branch": self.branch_id,
            "sample_id": row.sample_id,
            "status": row.sample_status,
        }


def _requests(tmp_path: Path):
    return tuple(
        BranchExportRequest(
            dataset_id=f"{branch}_dataset",
            serializer=DummySerializer(branch),
            accepted_path=tmp_path / f"golden_{branch}.jsonl",
            rejected_path=tmp_path / f"rejected_{branch}.jsonl",
        )
        for branch in ("llm", "ml")
    )


def test_coordinator_publishes_four_byte_stable_files_in_sample_order(tmp_path: Path) -> None:
    source = FakeSource(
        {
            "llm": (_row("llm", "rejected", "llm_b"), _row("llm", "accepted", "llm_a")),
            "ml": (_row("ml", "accepted", "ml_b"), _row("ml", "rejected", "ml_a")),
        }
    )
    coordinator = ExportCoordinator(source, AtomicExportWriter())
    requests = _requests(tmp_path)

    summaries = coordinator.export_all(requests)
    first_bytes = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}
    repeated = coordinator.export_all(requests)
    second_bytes = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}

    assert first_bytes == second_bytes
    assert [summary.branch_id for summary in summaries] == ["llm", "ml"]
    assert summaries == repeated
    assert first_bytes["golden_llm.jsonl"].count(b"\n") == 1
    assert first_bytes["rejected_llm.jsonl"].count(b"\n") == 1
    assert first_bytes["golden_ml.jsonl"].count(b"\n") == 1
    assert first_bytes["rejected_ml.jsonl"].count(b"\n") == 1
    assert not list(tmp_path.glob(".*.tmp"))
    assert not list(tmp_path.glob(".*.bak"))


def test_atomic_replace_failure_restores_all_previous_files(tmp_path: Path) -> None:
    targets = tuple(tmp_path / f"target_{index}.jsonl" for index in range(4))
    for index, target in enumerate(targets):
        target.write_bytes(f"old-{index}\n".encode())

    calls = 0

    def fail_once(source, target):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected replacement failure")
        os.replace(source, target)

    writer = AtomicExportWriter(replace=fail_once)
    with pytest.raises(ExportError, match="previous files were restored"):
        writer.write({target: f"new-{index}\n".encode() for index, target in enumerate(targets)})

    assert [target.read_text() for target in targets] == [f"old-{index}\n" for index in range(4)]
    assert sorted(path.name for path in tmp_path.iterdir()) == [path.name for path in targets]


def test_serialization_failure_leaves_existing_targets_untouched(tmp_path: Path) -> None:
    class FailingSerializer(DummySerializer):
        def serialize(self, row):
            raise RuntimeError("injected serialization failure")

    accepted = tmp_path / "accepted.jsonl"
    rejected = tmp_path / "rejected.jsonl"
    accepted.write_bytes(b"old-accepted\n")
    rejected.write_bytes(b"old-rejected\n")
    request = BranchExportRequest(
        dataset_id="llm_dataset",
        serializer=FailingSerializer("llm"),
        accepted_path=accepted,
        rejected_path=rejected,
    )

    with pytest.raises(RuntimeError, match="injected serialization failure"):
        ExportCoordinator(
            FakeSource({"llm": (_row("llm", "accepted", "sample"),)}),
            AtomicExportWriter(),
        ).export_all((request,))

    assert accepted.read_bytes() == b"old-accepted\n"
    assert rejected.read_bytes() == b"old-rejected\n"


def test_export_connection_uses_project_host_default_without_exposing_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    sentinel = object()

    for name in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(
        "services.selector.app.core.export.dotenv_values",
        lambda path: {
            "POSTGRES_PORT": "5433",
            "POSTGRES_DB": "farm_test",
            "POSTGRES_USER": "farm_user",
            "POSTGRES_PASSWORD": "secret-value",
        },
    )

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("services.selector.app.core.export.psycopg.connect", fake_connect)

    connection = connect_export_database(load_common_config())

    assert connection is sentinel
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 5433
    assert captured["dbname"] == "farm_test"
    assert captured["user"] == "farm_user"
    assert captured["password"] == "secret-value"
