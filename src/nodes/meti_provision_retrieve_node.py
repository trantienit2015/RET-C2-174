"""AgentCore Platform v1.0 - RET-C2-174 METIProvisionRetrieveNode (inner subgraph, step 1).

Note: since AgentBaseGraph's pre_process -> main edge is unconditional, an
upstream pre_process ERROR still dispatches into this inner subgraph. The
query/physical_ai_type shape is therefore re-validated here, never trusting
that the upstream rejection alone
stopped the pipeline. KB-backed retrieval only - never fabricates a METI v1.2
section that is not present in the configured KB.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.degradation import EMPTY_INPUT
from src.services.service import VALID_PHYSICAL_AI_TYPES, retrieve_meti_provisions


class METIProvisionRetrieveNode(FunctionNode):
    """Retrieve applicable METI AI Operator Guideline v1.2 provisions."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, kb: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._kb = kb or []

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        parsed = from_json(state.get("user_input"), {})
        query = parsed.get("query", "") if isinstance(parsed, dict) else ""
        physical_ai_type = parsed.get("physical_ai_type", "unknown") if isinstance(parsed, dict) else "unknown"

        if not query:
            # The subgraph is seeded with the request text alone, so this node cannot
            # tell "the outer step already refused" from "upstream dropped the field".
            # Both readings point at the same thing the caller can do.
            return {"error_code": EMPTY_INPUT, "status": AgentStatus.SUCCESS.value}
        if physical_ai_type not in VALID_PHYSICAL_AI_TYPES:
            # Stays an error: the classifier only ever emits allowed values, so this is
            # an internally inconsistent run, not something the caller can correct.
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"METIProvisionRetrieveNode: invalid physical_ai_type '{physical_ai_type}'"],
            }

        provisions = retrieve_meti_provisions(physical_ai_type, self._kb)

        emit_trace_event(
            "meti_provisions_retrieved",
            {
                "provision_count": len(provisions),
                "physical_ai_type": physical_ai_type,
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )

        return {
            "retrieved_provisions": to_json(provisions),
            "status": AgentStatus.SUCCESS.value,
        }
