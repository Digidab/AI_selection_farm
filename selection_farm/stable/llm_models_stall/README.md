# llm_models_stall

Stores per-model directories for LLM assets (Qwen, Llama, Gemma, Phi, DeepSeek Distill, small judge/reasoning models, embedding models managed as LLM assets).

Expected structure per model:

```
<model_name>/
├── model_card.md
├── base_info.yaml
├── adapters/
├── eval_reports/
├── prompts/
└── status.yaml
```

Does not duplicate large weights already stored by Ollama or external model caches.
