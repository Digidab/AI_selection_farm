"""Production and injectable ID provider boundary."""

from typing import Protocol, runtime_checkable

from scripts.id_generator.embedding_id import issue_embedding_id
from scripts.id_generator.generation_id import issue_generation_id
from scripts.id_generator.model_id import issue_model_id
from scripts.id_generator.run_id import issue_run_id
from scripts.id_generator.sample_id import issue_sample_id
from scripts.id_generator.task_id import issue_task_id
from scripts.id_generator.validation_id import issue_validation_id


@runtime_checkable
class IDProvider(Protocol):
    def issue_model_id(self) -> str: ...

    def issue_run_id(self) -> str: ...

    def issue_task_id(self) -> str: ...

    def issue_generation_id(self) -> str: ...

    def issue_validation_id(self) -> str: ...

    def issue_sample_id(self) -> str: ...

    def issue_embedding_id(self) -> str: ...


class ProductionIDProvider:
    def issue_model_id(self) -> str:
        return issue_model_id()

    def issue_run_id(self) -> str:
        return issue_run_id()

    def issue_task_id(self) -> str:
        return issue_task_id()

    def issue_generation_id(self) -> str:
        return issue_generation_id()

    def issue_validation_id(self) -> str:
        return issue_validation_id()

    def issue_sample_id(self) -> str:
        return issue_sample_id()

    def issue_embedding_id(self) -> str:
        return issue_embedding_id()
