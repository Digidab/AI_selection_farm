from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[4] / "services" / "selector" / "app" / "ml"
FORBIDDEN_TERMS = (
    "ollama",
    "prompt",
    "embedding",
    "semantic_threshold",
    "pgvector",
    "vector_cosine_ops",
    "<=>",
)


def test_ml_source_has_no_llm_vocabulary() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in sorted(ML_ROOT.rglob("*.py"))
    )

    assert [term for term in FORBIDDEN_TERMS if term in sources] == []
