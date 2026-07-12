import math

import pytest

from services.selector.app.core.schemas import CoreError, ErrorCode
from services.selector.app.llm.config import (
    EmbeddingSettings,
    OutputSettings,
    SemanticDedupSettings,
)
from services.selector.app.llm.evaluators import LLMCandidateEvaluator
from services.selector.app.llm.evaluators.json_schema import JSONSchemaEvaluator
from services.selector.app.llm.evaluators.semantic_dedup import (
    NearestAcceptedEmbedding,
    SemanticDedupEvaluator,
)
from services.selector.app.llm.output_contracts.structured_json import (
    StructuredJSONContract,
    StructuredJSONError,
)
from services.selector.app.llm.schemas import EmbeddingResult

OUTPUT_SETTINGS = OutputSettings(max_characters=128, max_json_depth=3)
EMBEDDING_SETTINGS = EmbeddingSettings(model="nomic-embed-text", dimension=768)
DEDUP_SETTINGS = SemanticDedupSettings(max_cosine_distance=0.05)
EXPECTED_SCHEMA = {
    "type": "object",
    "required": ["decision", "score"],
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["accept", "reject"]},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


class FakeRuntime:
    def __init__(self, vector=None) -> None:
        self.vector = tuple(vector or ([1.0] + [0.0] * 767))
        self.embed_calls = 0

    def embed(self, texts, *, model, expected_dimension):
        self.embed_calls += 1
        assert texts == ('{"decision":"accept","score":0.8}',)
        return EmbeddingResult(model=model, vectors=(self.vector,))


class FakeLookup:
    def __init__(self, nearest=None) -> None:
        self.nearest = nearest
        self.calls = 0

    def find_nearest(self, **kwargs):
        self.calls += 1
        assert kwargs["dataset_id"] == "selector_llm_seed_v001"
        assert kwargs["embedding_model_id"] == "nomic-embed-text"
        return self.nearest


def _evaluator() -> LLMCandidateEvaluator:
    return LLMCandidateEvaluator(
        output_contract=StructuredJSONContract(),
        json_schema=JSONSchemaEvaluator(),
        semantic_dedup=SemanticDedupEvaluator(),
    )


def _evaluate(text, runtime, lookup):
    return _evaluator().evaluate(
        text,
        expected_schema=EXPECTED_SCHEMA,
        dataset_id="selector_llm_seed_v001",
        runtime=runtime,
        lookup=lookup,
        output_settings=OUTPUT_SETTINGS,
        embedding_settings=EMBEDDING_SETTINGS,
        dedup_settings=DEDUP_SETTINGS,
    )


@pytest.mark.parametrize(
    "text, code",
    [
        ("", "empty_output"),
        ("x" * 129, "too_long_output"),
        ("{'decision':'accept'}", "invalid_json"),
        ('{"score":NaN}', "invalid_json"),
        ('{"score":Infinity}', "invalid_json"),
        ("[1,2]", "wrong_type"),
        ('{"a":{"b":{"c":1}}}', "max_depth_exceeded"),
    ],
)
def test_structured_json_rejects_invalid_output(text: str, code: str) -> None:
    with pytest.raises(StructuredJSONError) as exc_info:
        StructuredJSONContract().parse(text, OUTPUT_SETTINGS)
    assert exc_info.value.failure_code == code


def test_structured_json_canonicalizes_keys_and_accepts_depth_boundary() -> None:
    parsed = StructuredJSONContract().parse('{"b":{"x":1},"a":2}', OUTPUT_SETTINGS)
    assert parsed.canonical_text == '{"a":2,"b":{"x":1}}'


def test_schema_failure_stops_before_expensive_embedding() -> None:
    runtime = FakeRuntime()
    lookup = FakeLookup()
    result = _evaluate('{"decision":"unknown","score":0.8}', runtime, lookup)

    assert result.accepted is False
    assert result.failure_code == "schema_error"
    assert [item.check_id for item in result.evidence] == ["structured_json", "json_schema"]
    assert runtime.embed_calls == lookup.calls == 0


def test_accepted_candidate_contains_contract_and_all_mandatory_evidence() -> None:
    runtime = FakeRuntime()
    lookup = FakeLookup()
    result = _evaluate('{"score":0.8,"decision":"accept"}', runtime, lookup)

    assert result.accepted is True
    assert result.output_contract_id == "structured_json"
    assert [item.check_id for item in result.evidence] == [
        "structured_json",
        "json_schema",
        "semantic_dedup",
    ]
    assert all(item.passed for item in result.evidence)
    assert len(result.embedding or ()) == 768


@pytest.mark.parametrize(
    "distance, duplicate",
    [(0.05, True), (math.nextafter(0.05, math.inf), False)],
)
def test_semantic_duplicate_threshold_is_inclusive(distance: float, duplicate: bool) -> None:
    result = _evaluate(
        '{"decision":"accept","score":0.8}',
        FakeRuntime(),
        FakeLookup(NearestAcceptedEmbedding("sample-1", distance)),
    )
    assert result.accepted is not duplicate
    assert (result.failure_code == "duplicate_sample") is duplicate


def test_embedding_failure_fails_closed_with_explicit_evidence() -> None:
    class FailingRuntime(FakeRuntime):
        def embed(self, texts, *, model, expected_dimension):
            raise CoreError(ErrorCode.EXECUTION, "embedding model unavailable")

    result = _evaluate('{"decision":"accept","score":0.8}', FailingRuntime(), FakeLookup())

    assert result.accepted is False
    assert result.failure_code == "semantic_dedup_error"
    assert result.evidence[-1].check_id == "semantic_dedup"
    assert result.evidence[-1].passed is False


def test_invalid_cosine_distance_fails_closed() -> None:
    result = _evaluate(
        '{"decision":"accept","score":0.8}',
        FakeRuntime(),
        FakeLookup(NearestAcceptedEmbedding("sample-1", math.nan)),
    )

    assert result.accepted is False
    assert result.failure_code == "semantic_dedup_error"
