from pathlib import Path

import joblib
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LinearRegression

from services.selector.app.ml.config import (
    ClassificationPredictionSettings,
    ConfidenceSettings,
    RegressionPredictionSettings,
    load_ml_config,
)
from services.selector.app.ml.pipelines.interfaces import (
    MLPipelineAdapter,
    MLPrediction,
    PredictionEvidence,
)
from services.selector.app.ml.pipelines.registry import (
    MLPipelineRegistry,
    MLPipelineRegistryError,
    build_reference_registry,
)
from services.selector.app.ml.pipelines.sklearn_generic import (
    MLPipelineError,
    SklearnGenericAdapter,
)
from services.selector.app.ml.producer import MLProducer
from services.selector.app.ml.schemas import (
    FeatureDefinition,
    FeatureType,
    MLPipelineDescriptor,
    MLTask,
    PredictionMode,
)

pytestmark = pytest.mark.filterwarnings(
    "ignore:Setting the shape on a NumPy array has been deprecated:DeprecationWarning:joblib.numpy_pickle"
)

FEATURES = (
    FeatureDefinition(name="first", data_type=FeatureType.FLOAT),
    FeatureDefinition(name="second", data_type=FeatureType.INTEGER),
    FeatureDefinition(name="flag", data_type=FeatureType.BOOLEAN),
)


class OrderedRegressionEstimator:
    def predict(self, rows):
        return [rows[0][0] * 100 + rows[0][1] * 10 + int(rows[0][2])]


class PredictOnlyClassifier:
    def predict(self, rows):
        return ["healthy"]


class ProbabilityMustNotRun(PredictOnlyClassifier):
    def predict_proba(self, rows):
        raise AssertionError("predict_proba must not be called")


class MultiplePredictionEstimator:
    def predict(self, rows):
        return [1.0, 2.0]


class NonFinitePredictionEstimator:
    def predict(self, rows):
        return [float("nan")]


class MalformedProbabilityEstimator(PredictOnlyClassifier):
    classes_ = ["healthy", "attention"]

    def predict_proba(self, rows):
        return [[1.0]]


def _dump(tmp_path: Path, estimator, name: str = "model.joblib") -> Path:
    path = tmp_path / name
    joblib.dump(estimator, path)
    return path


def _task(**changes: object) -> MLTask:
    features = {"second": 2, "flag": True, "first": 1.5}
    features.update(changes)
    return MLTask(task_id="ml_pipeline_test", features=features)


def _classification(*, confidence_required: bool = True):
    return ClassificationPredictionSettings(
        mode="classification",
        allowed_classes=("healthy", "attention"),
        confidence=ConfidenceSettings(required=confidence_required, minimum=0.5),
    )


def _regression():
    return RegressionPredictionSettings(mode="regression", minimum=-1000.0, maximum=1000.0)


def test_reference_adapter_satisfies_protocol_and_registry_is_explicit() -> None:
    adapter = SklearnGenericAdapter()
    assert isinstance(adapter, MLPipelineAdapter)
    assert build_reference_registry().resolve("sklearn_generic") is not None

    with pytest.raises(MLPipelineRegistryError, match="Unknown ML pipeline"):
        build_reference_registry().resolve("random_forest")


def test_classification_fixture_returns_probability_evidence(tmp_path: Path) -> None:
    estimator = DummyClassifier(strategy="prior")
    estimator.fit(
        [[1.0, 0, False], [2.0, 1, True], [3.0, 0, False]],
        ["healthy", "attention", "healthy"],
    )

    result = SklearnGenericAdapter().predict(
        _task(),
        artifact_path=_dump(tmp_path, estimator),
        feature_contract=FEATURES,
        prediction_settings=_classification(),
    )

    assert result.mode is PredictionMode.CLASSIFICATION
    assert result.prediction == "healthy"
    assert result.probabilities is not None
    assert {item.label for item in result.probabilities} == {"attention", "healthy"}
    assert sum(item.probability for item in result.probabilities) == pytest.approx(1.0)
    assert result.evidence.pipeline_id == "sklearn_generic"
    assert result.evidence.used_probability_api is True


def test_regression_fixture_returns_typed_scalar_without_probabilities(tmp_path: Path) -> None:
    estimator = LinearRegression().fit(
        [[0.0, 0, False], [1.0, 1, True], [2.0, 2, False]],
        [0.0, 2.0, 4.0],
    )

    result = SklearnGenericAdapter().predict(
        _task(first=1.0, second=1, flag=True),
        artifact_path=_dump(tmp_path, estimator),
        feature_contract=FEATURES,
        prediction_settings=_regression(),
    )

    assert isinstance(result.prediction, float)
    assert result.prediction == pytest.approx(2.0)
    assert result.probabilities is None
    assert result.evidence.used_probability_api is False


def test_feature_order_is_config_owned_and_stable(tmp_path: Path) -> None:
    result = SklearnGenericAdapter().predict(
        _task(),
        artifact_path=_dump(tmp_path, OrderedRegressionEstimator()),
        feature_contract=FEATURES,
        prediction_settings=_regression(),
    )

    assert result.prediction == 171.0
    assert result.evidence.feature_order == ("first", "second", "flag")


def test_optional_probability_api_is_not_called(tmp_path: Path) -> None:
    result = SklearnGenericAdapter().predict(
        _task(),
        artifact_path=_dump(tmp_path, ProbabilityMustNotRun()),
        feature_contract=FEATURES,
        prediction_settings=_classification(confidence_required=False),
    )

    assert result.prediction == "healthy"
    assert result.probabilities is None
    assert result.evidence.used_probability_api is False


@pytest.mark.parametrize(
    "estimator, settings, message",
    [
        ({"not": "an estimator"}, _regression(), "callable predict"),
        (MultiplePredictionEstimator(), _regression(), "exactly one result"),
        (NonFinitePredictionEstimator(), _regression(), "prediction must be finite"),
        (PredictOnlyClassifier(), _classification(), "requires callable predict_proba"),
        (
            MalformedProbabilityEstimator(),
            _classification(),
            "Probability count must match",
        ),
    ],
)
def test_artifact_api_and_result_errors_fail_closed(
    tmp_path: Path, estimator, settings, message: str
) -> None:
    with pytest.raises(MLPipelineError, match=message):
        SklearnGenericAdapter().predict(
            _task(),
            artifact_path=_dump(tmp_path, estimator),
            feature_contract=FEATURES,
            prediction_settings=settings,
        )


def test_missing_or_wrong_suffix_artifact_fails_before_load(tmp_path: Path) -> None:
    with pytest.raises(MLPipelineError, match="existing .joblib"):
        SklearnGenericAdapter().predict(
            _task(),
            artifact_path=tmp_path / "missing.joblib",
            feature_contract=FEATURES,
            prediction_settings=_regression(),
        )

    with pytest.raises(MLPipelineError, match="existing .joblib"):
        SklearnGenericAdapter().predict(
            _task(),
            artifact_path=_dump(tmp_path, OrderedRegressionEstimator(), "model.pkl"),
            feature_contract=FEATURES,
            prediction_settings=_regression(),
        )


def test_corrupt_joblib_artifact_fails_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "corrupt.joblib"
    artifact.write_bytes(b"not-a-joblib-artifact")

    with pytest.raises(MLPipelineError, match="Cannot load trusted local ML artifact"):
        SklearnGenericAdapter().predict(
            _task(),
            artifact_path=artifact,
            feature_contract=FEATURES,
            prediction_settings=_regression(),
        )


def test_producer_delegates_to_test_only_adapter_without_dispatch_change(tmp_path: Path) -> None:
    class TestAdapter:
        descriptor = MLPipelineDescriptor(
            pipeline_id="test_pipeline",
            artifact_formats=frozenset({"joblib"}),
            supported_modes=frozenset({PredictionMode.CLASSIFICATION}),
            supported_feature_types=frozenset(FeatureType),
            probability_api_optional=True,
        )

        def predict(self, task, **kwargs):
            return MLPrediction(
                task_id=task.task_id,
                mode=PredictionMode.CLASSIFICATION,
                prediction="test-result",
                probabilities=None,
                evidence=PredictionEvidence(
                    pipeline_id="test_pipeline",
                    feature_order=tuple(feature.name for feature in kwargs["feature_contract"]),
                    used_probability_api=False,
                ),
            )

    registry = MLPipelineRegistry()
    registry.register(TestAdapter())
    settings = load_ml_config().ml.model_copy(
        update={
            "pipeline_id": "test_pipeline",
            "artifact_path": tmp_path / "unused.joblib",
        }
    )

    result = MLProducer(registry).produce(_task(), settings)

    assert result.prediction == "test-result"
    assert result.evidence.pipeline_id == "test_pipeline"


def test_registry_rejects_duplicate_adapter() -> None:
    registry = build_reference_registry()
    with pytest.raises(MLPipelineRegistryError, match="Duplicate ML pipeline"):
        registry.register(SklearnGenericAdapter())


def test_registry_rejects_object_without_adapter_protocol() -> None:
    class MissingPredict:
        descriptor = SklearnGenericAdapter.descriptor.model_copy(
            update={"pipeline_id": "missing_predict"}
        )

    with pytest.raises(MLPipelineRegistryError, match="must declare a pipeline descriptor"):
        MLPipelineRegistry().register(MissingPredict())


def test_registry_and_producer_have_no_dynamic_or_family_dispatch() -> None:
    root = Path("selection_farm/services/selector/app/ml")
    source = (root / "producer.py").read_text(encoding="utf-8") + (
        root / "pipelines/registry.py"
    ).read_text(encoding="utf-8")

    assert "importlib" not in source
    assert "if settings.pipeline_id" not in source
    assert "if pipeline_id" not in source
