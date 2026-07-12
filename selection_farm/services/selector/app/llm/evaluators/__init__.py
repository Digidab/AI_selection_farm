"""Ordered v001 LLM candidate evaluation."""

from dataclasses import dataclass
from typing import Any

from ...core.schemas import CoreError, EvidenceRecord
from ..config import EmbeddingSettings, OutputSettings, SemanticDedupSettings
from ..interfaces import LLMRuntimeAdapter
from ..output_contracts.structured_json import (
    ParsedStructuredJSON,
    StructuredJSONContract,
    StructuredJSONError,
)
from .json_schema import JSONSchemaEvaluator
from .semantic_dedup import AcceptedEmbeddingLookup, SemanticDedupEvaluator


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    accepted: bool
    output_contract_id: str
    parsed_output: dict[str, Any] | None
    canonical_text: str | None
    embedding: tuple[float, ...] | None
    evidence: tuple[EvidenceRecord, ...]
    failure_code: str | None = None
    failure_reason: str | None = None


class LLMCandidateEvaluator:
    """Run cheap structural checks before embedding and semantic lookup."""

    def __init__(
        self,
        *,
        output_contract: StructuredJSONContract,
        json_schema: JSONSchemaEvaluator,
        semantic_dedup: SemanticDedupEvaluator,
    ) -> None:
        self.output_contract = output_contract
        self.json_schema = json_schema
        self.semantic_dedup = semantic_dedup

    def evaluate(
        self,
        text: str,
        *,
        expected_schema: dict[str, Any],
        dataset_id: str,
        runtime: LLMRuntimeAdapter,
        lookup: AcceptedEmbeddingLookup,
        output_settings: OutputSettings,
        embedding_settings: EmbeddingSettings,
        dedup_settings: SemanticDedupSettings,
    ) -> CandidateEvaluation:
        evidence: list[EvidenceRecord] = []
        try:
            parsed = self.output_contract.parse(text, output_settings)
        except StructuredJSONError as exc:
            failed = EvidenceRecord(
                check_id=self.output_contract.descriptor.component_id,
                passed=False,
                code=exc.failure_code,
                details={"message": str(exc)},
            )
            return self._rejected(None, (failed,), exc.failure_code, str(exc))

        evidence.append(
            EvidenceRecord(
                check_id=parsed.contract_id,
                passed=True,
                details={"canonical_characters": len(parsed.canonical_text)},
            )
        )
        schema_evidence = self.json_schema.evaluate(parsed, expected_schema)
        evidence.append(schema_evidence)
        if not schema_evidence.passed:
            return self._rejected(
                parsed,
                tuple(evidence),
                schema_evidence.code or "schema_error",
                str(schema_evidence.details.get("message", "JSON Schema validation failed")),
            )

        try:
            semantic = self.semantic_dedup.evaluate(
                parsed,
                dataset_id=dataset_id,
                runtime=runtime,
                lookup=lookup,
                embedding_settings=embedding_settings,
                dedup_settings=dedup_settings,
            )
        except CoreError as exc:
            failed = EvidenceRecord(
                check_id=self.semantic_dedup.descriptor.component_id,
                passed=False,
                code="semantic_dedup_error",
                details={"message": str(exc)},
            )
            evidence.append(failed)
            return self._rejected(
                parsed,
                tuple(evidence),
                "semantic_dedup_error",
                str(exc),
            )

        evidence.append(semantic.evidence)
        if not semantic.evidence.passed:
            return self._rejected(
                parsed,
                tuple(evidence),
                semantic.evidence.code or "duplicate_sample",
                "Candidate is a semantic duplicate of an accepted sample",
                embedding=semantic.embedding,
            )

        return CandidateEvaluation(
            accepted=True,
            output_contract_id=parsed.contract_id,
            parsed_output=parsed.value,
            canonical_text=parsed.canonical_text,
            embedding=semantic.embedding,
            evidence=tuple(evidence),
        )

    def _rejected(
        self,
        parsed: ParsedStructuredJSON | None,
        evidence: tuple[EvidenceRecord, ...],
        failure_code: str,
        failure_reason: str,
        *,
        embedding: tuple[float, ...] | None = None,
    ) -> CandidateEvaluation:
        return CandidateEvaluation(
            accepted=False,
            output_contract_id=self.output_contract.descriptor.component_id,
            parsed_output=None if parsed is None else parsed.value,
            canonical_text=None if parsed is None else parsed.canonical_text,
            embedding=embedding,
            evidence=evidence,
            failure_code=failure_code,
            failure_reason=failure_reason,
        )


__all__ = ("CandidateEvaluation", "LLMCandidateEvaluator")
