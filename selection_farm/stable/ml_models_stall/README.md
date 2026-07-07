# ml_models_stall

Stores classical ML / narrow task-specific models (LightGBM, XGBoost, CatBoost, RandomForest, LogisticRegression, IsolationForest, small NNs, ranking/scoring models).

Expected structure per model:

```
<model_name>/
├── model.pkl
├── model.joblib
├── model.onnx
├── features.yaml
├── training_config.yaml
├── eval_report.json
├── model_card.md
└── status.yaml
```
