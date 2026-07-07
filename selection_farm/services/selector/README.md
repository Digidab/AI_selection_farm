# Selector

Strict quality gate: validates model outputs, rejects bad samples, accepts high-quality samples, writes selection results.

## Responsibilities
- generate candidates
- validate JSON / schema / numeric ranges
- reject invalid answers
- deduplicate via embeddings
- write golden samples / rejected samples
- store run metadata
