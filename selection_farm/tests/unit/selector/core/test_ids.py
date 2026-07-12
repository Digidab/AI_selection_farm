from services.selector.app.core.ids import IDProvider, ProductionIDProvider


class FakeIDProvider:
    def issue_model_id(self) -> str:
        return "_tz08_model_fake"

    def issue_run_id(self) -> str:
        return "_tz08_run_fake"

    def issue_task_id(self) -> str:
        return "_tz08_task_fake"

    def issue_generation_id(self) -> str:
        return "_tz08_generation_fake"

    def issue_validation_id(self) -> str:
        return "_tz08_validation_fake"

    def issue_sample_id(self) -> str:
        return "_tz08_sample_fake"

    def issue_embedding_id(self) -> str:
        return "_tz08_embedding_fake"


def test_id_provider_is_injectable() -> None:
    provider = FakeIDProvider()

    assert isinstance(provider, IDProvider)
    assert provider.issue_run_id() == "_tz08_run_fake"


def test_production_provider_exposes_complete_contract_without_issuing_ids() -> None:
    assert isinstance(ProductionIDProvider(), IDProvider)
