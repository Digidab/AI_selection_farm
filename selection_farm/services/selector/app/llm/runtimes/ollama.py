"""Bounded, non-streaming Ollama HTTP runtime adapter."""

import math
import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from ...core.schemas import CoreError, ErrorCode
from ..config import GenerationSettings, RuntimeSettings
from ..schemas import (
    CapabilityDescriptor,
    ComponentKind,
    EmbeddingResult,
    GenerationResult,
    PreparedLLMInput,
)

_TRANSIENT_STATUS_CODES = frozenset({408, 429})
_MAX_ATTEMPTS = 2
_EMBEDDING_DIMENSION = 768
_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class OllamaRuntimeError(CoreError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(ErrorCode.EXECUTION, message, retryable=retryable)


class OllamaRuntimeAdapter:
    descriptor = CapabilityDescriptor(
        component_id="ollama",
        kind=ComponentKind.RUNTIME,
        capabilities=frozenset({"generation", "embedding", "structured_json"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.Client | None = None,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        max_attempts: int = _MAX_ATTEMPTS,
    ) -> None:
        self._endpoint = self._validate_endpoint(endpoint)
        if max_attempts < 1 or max_attempts > _MAX_ATTEMPTS:
            raise ValueError(f"max_attempts must be between 1 and {_MAX_ATTEMPTS}")
        self._client = client or httpx.Client()
        self._timeout = timeout
        self._max_attempts = max_attempts

    @classmethod
    def from_settings(
        cls,
        settings: RuntimeSettings,
        *,
        environ: Mapping[str, str] = os.environ,
        client: httpx.Client | None = None,
    ) -> "OllamaRuntimeAdapter":
        endpoint = environ.get(settings.endpoint_env)
        if endpoint is None or not endpoint.strip():
            raise OllamaRuntimeError(
                f"Required Ollama endpoint environment variable is missing: "
                f"{settings.endpoint_env}"
            )
        return cls(endpoint, client=client)

    def generate(
        self,
        prepared_input: PreparedLLMInput,
        settings: GenerationSettings,
    ) -> GenerationResult:
        payload = {
            "model": settings.model,
            "prompt": prepared_input.prompt,
            "stream": False,
            "format": prepared_input.expected_schema,
            "options": {
                "temperature": settings.temperature,
                "seed": settings.seed,
                "num_predict": settings.max_output_tokens,
            },
        }
        data = self._post("/api/generate", payload, model=settings.model)
        model = data.get("model")
        response = data.get("response")
        done = data.get("done")
        if not isinstance(model, str) or not model.strip():
            raise OllamaRuntimeError("Invalid Ollama generate response: missing model")
        if not isinstance(response, str) or not response.strip():
            raise OllamaRuntimeError("Invalid Ollama generate response: missing response text")
        if done is not True:
            raise OllamaRuntimeError("Invalid Ollama generate response: request is not complete")
        return GenerationResult(model=model, text=response, done=True)

    def embed(
        self,
        texts: tuple[str, ...],
        *,
        model: str,
        expected_dimension: int,
    ) -> EmbeddingResult:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise OllamaRuntimeError("Embedding input must contain non-empty text")
        if expected_dimension != _EMBEDDING_DIMENSION:
            raise OllamaRuntimeError(f"Expected embedding dimension must be {_EMBEDDING_DIMENSION}")

        data = self._post(
            "/api/embed",
            {"model": model, "input": list(texts), "truncate": False},
            model=model,
        )
        response_model = data.get("model")
        embeddings = data.get("embeddings")
        if not isinstance(response_model, str) or not response_model.strip():
            raise OllamaRuntimeError("Invalid Ollama embed response: missing model")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise OllamaRuntimeError("Invalid Ollama embed response: vector count mismatch")

        vectors: list[tuple[float, ...]] = []
        for vector in embeddings:
            if not isinstance(vector, list) or len(vector) != expected_dimension:
                raise OllamaRuntimeError(
                    "Invalid Ollama embed response: embedding dimension mismatch"
                )
            normalized: list[float] = []
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise OllamaRuntimeError(
                        "Invalid Ollama embed response: embedding value is not numeric"
                    )
                numeric_value = float(value)
                if not math.isfinite(numeric_value):
                    raise OllamaRuntimeError(
                        "Invalid Ollama embed response: embedding value is not finite"
                    )
                normalized.append(numeric_value)
            vectors.append(tuple(normalized))
        return EmbeddingResult(model=response_model, vectors=tuple(vectors))

    def _post(self, path: str, payload: dict[str, Any], *, model: str) -> dict[str, Any]:
        url = f"{self._endpoint}{path}"
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.post(url, json=payload, timeout=self._timeout)
            except httpx.TransportError as exc:
                if attempt < self._max_attempts:
                    continue
                raise OllamaRuntimeError(
                    "Ollama request failed after bounded retries", retryable=True
                ) from exc

            if response.status_code == 404:
                raise OllamaRuntimeError(f"Ollama model is unavailable: {model}")
            is_transient = (
                response.status_code in _TRANSIENT_STATUS_CODES or response.status_code >= 500
            )
            if is_transient and attempt < self._max_attempts:
                continue
            if response.status_code != 200:
                raise OllamaRuntimeError(
                    f"Ollama request failed with HTTP {response.status_code}",
                    retryable=is_transient,
                )
            try:
                data = response.json()
            except ValueError as exc:
                raise OllamaRuntimeError("Ollama returned invalid JSON") from exc
            if not isinstance(data, dict):
                raise OllamaRuntimeError("Ollama returned a non-object response")
            return data
        raise AssertionError("bounded retry loop exhausted unexpectedly")

    @staticmethod
    def _validate_endpoint(endpoint: str) -> str:
        candidate = endpoint.strip().rstrip("/")
        parsed = urlsplit(candidate)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise OllamaRuntimeError("Invalid Ollama endpoint")
        return candidate
