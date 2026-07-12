# ML Pipelines

## Mission

Explicit model-family adapters for artifact checks, feature preparation, inference, and normalized
ML decisions.

## Files

- `interfaces.py` — ML pipeline adapter protocol boundary.
- `registry.py` — allowlisted pipeline resolution boundary.
- `sklearn_generic.py` — only v001 model-family adapter boundary.

No future family placeholders belong here. New families require separate approved TZs. The v001
reference registry contains only `sklearn_generic`. It accepts existing `.joblib` artifacts from
trusted local paths, requires callable `predict`, preserves config-owned feature order, and calls
`predict_proba` only when classification confidence is explicitly required. Results contain typed
prediction/probability records and the resolved pipeline identity; arbitrary imports and
model-family dispatch chains are forbidden.
