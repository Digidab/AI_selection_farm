# LLM Pipelines

## Mission

Interaction orchestration for explicitly registered LLM workflows.

## Files

- `single_turn.py` — v001 single-turn pipeline boundary.

Pipelines may compose declared runtime, modality, output-contract, and evaluator components. The
`single_turn` reference component prepares exactly one task through its registered modality and
delegates one generation call to its registered runtime. It owns no provider transport and does not
import the ML branch.
