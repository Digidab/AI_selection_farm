import os

import orjson

from services.selector.app.llm.config import GenerationSettings
from services.selector.app.llm.runtimes.ollama import OllamaRuntimeAdapter
from services.selector.app.llm.schemas import PreparedLLMInput


def test_live_ollama_structured_generation() -> None:
    runtime = OllamaRuntimeAdapter(
        os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        max_attempts=1,
    )
    result = runtime.generate(
        PreparedLLMInput(
            prompt="Return JSON with status nominal.",
            expected_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["status"],
                "properties": {"status": {"const": "nominal"}},
            },
        ),
        GenerationSettings(
            model="qwen3:0.6b",
            temperature=0.0,
            seed=42,
            max_output_tokens=64,
        ),
    )

    assert result.model == "qwen3:0.6b"
    assert result.done is True
    assert orjson.loads(result.text) == {"status": "nominal"}
