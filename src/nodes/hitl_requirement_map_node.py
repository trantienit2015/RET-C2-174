"""AgentCore Platform v1.0 - RET-C2-174 HITLRequirementMapNode (inner subgraph, step 2).

Deterministic mapping table (no LLM) from retrieved METI v1.2 provisions to
specific HITL obligations (mandatory HITL conditions, override procedures,
contact-risk assessment criteria).
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import map_hitl_requirements


class HITLRequirementMapNode(FunctionNode):
    """Map retrieved METI v1.2 provisions to specific HITL obligations."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        provisions = from_json(state.get("retrieved_provisions"), None)
        parsed = from_json(state.get("user_input"), {})
        physical_ai_type = parsed.get("physical_ai_type", "unknown") if isinstance(parsed, dict) else "unknown"

        if not isinstance(provisions, list):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["HITLRequirementMapNode: missing retrieved provisions"],
            }

        hitl_requirements = map_hitl_requirements(provisions, physical_ai_type)

        emit_trace_event(
            "hitl_requirements_mapped",
            {"requirement_count": len(hitl_requirements), "correlation_id": state.get("correlation_id", "")},
            state,
        )

        return {
            "hitl_requirements": to_json(hitl_requirements),
            "status": AgentStatus.SUCCESS.value,
        }
