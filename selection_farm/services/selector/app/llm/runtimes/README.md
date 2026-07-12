# LLM Runtimes

## Mission

Provider transport, capability, timeout, retry, and response-normalization components.

## Files

- `ollama.py` — v001 Ollama runtime boundary.

The `ollama` reference runtime calls `/api/generate` and `/api/embed` directly with httpx. Calls use
explicit non-streaming payloads, timeouts, and at most two attempts for transient failures. A 404,
invalid response, missing vector, non-finite value, or dimension other than the configured 768 fails
closed. The runtime owns no prompts, evaluation policy, database transaction, secrets, SDK, model
pull, fallback, or ML behavior.
