from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[4] / "services" / "selector" / "app" / "core"
FORBIDDEN_TERMS = (
    "ollama",
    "prompt",
    "estimator",
    "feature_vector",
    "class_label",
    "semantic_threshold",
    "embedding",
    "vector",
    "nomic-embed",
)


def test_core_source_has_no_branch_specific_vocabulary() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in sorted(CORE_ROOT.glob("*.py"))
    )

    assert [term for term in FORBIDDEN_TERMS if term in sources] == []
