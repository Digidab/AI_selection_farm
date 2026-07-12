import json
import math

import httpx
import pytest

from services.selector.app.llm.config import GenerationSettings, RuntimeSettings
from services.selector.app.llm.runtimes.ollama import (
    OllamaRuntimeAdapter,
    OllamaRuntimeError,
)
from services.selector.app.llm.schemas import PreparedLLMInput


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_from_settings_requires_declared_endpoint_environment_variable() -> None:
    settings = RuntimeSettings(endpoint_env="OLLAMA_HOST")
    with pytest.raises(OllamaRuntimeError, match="OLLAMA_HOST"):
        OllamaRuntimeAdapter.from_settings(settings, environ={})


def test_generate_posts_non_streaming_structured_request() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"model": "qwen3:0.6b", "response": '{"ok":true}', "done": True},
        )

    runtime = OllamaRuntimeAdapter("http://localhost:11434", client=_client(handler))
    result = runtime.generate(
        PreparedLLMInput(prompt="Return JSON", expected_schema={"type": "object"}),
        GenerationSettings(model="qwen3:0.6b", temperature=0.0, seed=42, max_output_tokens=64),
    )

    assert captured == {
        "path": "/api/generate",
        "payload": {
            "model": "qwen3:0.6b",
            "prompt": "Return JSON",
            "stream": False,
            "format": {"type": "object"},
            "options": {"temperature": 0.0, "seed": 42, "num_predict": 64},
        },
    }
    assert result.text == '{"ok":true}'


def test_embed_posts_batch_and_accepts_exactly_768_finite_values() -> None:
    vector = [0.0] * 768

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        assert json.loads(request.content) == {
            "model": "nomic-embed-text",
            "input": ["one", "two"],
            "truncate": False,
        }
        return httpx.Response(
            200,
            json={"model": "nomic-embed-text", "embeddings": [vector, vector]},
        )

    result = OllamaRuntimeAdapter("http://localhost:11434", client=_client(handler)).embed(
        ("one", "two"), model="nomic-embed-text", expected_dimension=768
    )

    assert len(result.vectors) == 2
    assert all(len(item) == 768 for item in result.vectors)


def test_embed_rejects_non_v001_expected_dimension_before_transport() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    runtime = OllamaRuntimeAdapter("http://localhost:11434", client=_client(handler))
    with pytest.raises(OllamaRuntimeError, match="must be 768"):
        runtime.embed(("one",), model="fixture", expected_dimension=384)

    assert calls == 0


def test_embed_fails_closed_on_model_identity_mismatch() -> None:
    runtime = OllamaRuntimeAdapter(
        "http://localhost:11434",
        client=_client(
            lambda request: httpx.Response(
                200,
                json={"model": "wrong-embed-model", "embeddings": [[0.0] * 768]},
            )
        ),
    )

    with pytest.raises(OllamaRuntimeError, match="model identity mismatch"):
        runtime.embed(("one",), model="nomic-embed-text", expected_dimension=768)


def test_embed_accepts_explicit_latest_alias_for_same_model() -> None:
    runtime = OllamaRuntimeAdapter(
        "http://localhost:11434",
        client=_client(
            lambda request: httpx.Response(
                200,
                json={"model": "nomic-embed-text:latest", "embeddings": [[0.0] * 768]},
            )
        ),
    )

    result = runtime.embed(("one",), model="nomic-embed-text", expected_dimension=768)

    assert result.model == "nomic-embed-text:latest"


@pytest.mark.parametrize(
    "vector, message",
    [
        ([0.0] * 767, "dimension mismatch"),
        ([0.0] * 767 + [math.inf], "not finite"),
        ([0.0] * 767 + [True], "not numeric"),
    ],
)
def test_embed_fails_closed_on_invalid_vector(vector, message: str) -> None:
    runtime = OllamaRuntimeAdapter(
        "http://localhost:11434",
        client=_client(
            lambda request: httpx.Response(
                200,
                content=json.dumps({"model": "nomic-embed-text", "embeddings": [vector]}).encode(),
                headers={"content-type": "application/json"},
            )
        ),
    )

    with pytest.raises(OllamaRuntimeError, match=message):
        runtime.embed(("one",), model="nomic-embed-text", expected_dimension=768)


def test_transient_failure_retries_once_then_succeeds() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"model": "fixture", "response": "{}", "done": True})

    runtime = OllamaRuntimeAdapter("http://localhost:11434", client=_client(handler))
    runtime.generate(
        PreparedLLMInput(prompt="Return JSON", expected_schema={"type": "object"}),
        GenerationSettings(model="fixture", temperature=0.0, seed=42, max_output_tokens=8),
    )
    assert attempts == 2


def test_missing_model_fails_without_retry_or_provider_error_leak() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, json={"error": "sensitive provider detail"})

    runtime = OllamaRuntimeAdapter("http://localhost:11434", client=_client(handler))
    with pytest.raises(OllamaRuntimeError, match="model is unavailable: absent") as exc_info:
        runtime.embed(("one",), model="absent", expected_dimension=768)

    assert attempts == 1
    assert "sensitive" not in str(exc_info.value)


def test_network_failure_stops_after_bounded_attempts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("offline", request=request)

    runtime = OllamaRuntimeAdapter("http://localhost:11434", client=_client(handler))
    with pytest.raises(OllamaRuntimeError) as exc_info:
        runtime.embed(("one",), model="fixture", expected_dimension=768)

    assert attempts == 2
    assert exc_info.value.retryable is True


def test_runtime_source_has_no_database_or_provider_sdk_dependency() -> None:
    source = open(
        "selection_farm/services/selector/app/llm/runtimes/ollama.py",
        encoding="utf-8",
    ).read()
    assert "psycopg" not in source
    assert "import ollama" not in source
