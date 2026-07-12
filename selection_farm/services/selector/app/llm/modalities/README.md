# LLM Modalities

## Mission

Validation and preparation for explicitly declared LLM input modalities.

## Files

- `text.py` — v001 text modality boundary.

The `text` reference component preserves prompt input and renders ordered messages into a stable,
role-delimited prompt for the single-turn runtime call. This directory owns modality preparation
only and does not teach Core or runtimes project-specific payload rules.
