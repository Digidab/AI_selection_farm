"""Reference text modality adapter."""

from ..schemas import (
    CapabilityDescriptor,
    ComponentKind,
    LLMTask,
    PreparedLLMInput,
)


class TextModalityAdapter:
    descriptor = CapabilityDescriptor(
        component_id="text",
        kind=ComponentKind.MODALITY,
        capabilities=frozenset({"prompt", "messages"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset(),
        supports_streaming=False,
    )

    def prepare(self, task: LLMTask) -> PreparedLLMInput:
        if task.prompt is not None:
            prompt = task.prompt
        else:
            assert task.messages is not None  # Enforced by the strict LLMTask contract.
            prompt = "\n".join(
                f"<{message.role.value}>\n{message.content}\n</{message.role.value}>"
                for message in task.messages
            )
        return PreparedLLMInput(prompt=prompt, expected_schema=task.expected_schema)
