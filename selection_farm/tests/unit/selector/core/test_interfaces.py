from services.selector.app.core.interfaces import SelectorBranch
from services.selector.app.core.schemas import (
    DecisionStatus,
    SelectionDecision,
    TaskRecord,
    TaskStatus,
)


class FakeBranch:
    branch_id = "fake"

    def evaluate(self, task: TaskRecord) -> SelectionDecision:
        return SelectionDecision(
            task_id=task.task_id,
            status=DecisionStatus.ACCEPTED,
            output_payload={"value": "accepted"},
        )


def test_protocol_fake_is_runtime_compatible() -> None:
    branch = FakeBranch()
    task = TaskRecord(
        task_id="TA_TEST",
        run_id="RU_TEST",
        task_type="fixture",
        status=TaskStatus.PENDING,
        input_payload={"value": 1},
    )

    assert isinstance(branch, SelectorBranch)
    assert branch.evaluate(task).status is DecisionStatus.ACCEPTED
