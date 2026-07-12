# LLM Output Contracts

## Mission

Parsing and normalization for one explicitly declared LLM result form.

## Files

- `structured_json.py` — v001 strict structured-JSON boundary.

Output contracts do not silently fall back to another result form and do not import ML.
`StructuredJSONContract` rejects empty, oversized, malformed, non-object, non-finite, and overly
deep output, then emits deterministic canonical JSON for later embedding and persistence.
