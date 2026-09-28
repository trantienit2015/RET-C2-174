"""AgentCore Platform v1.0 - RET-C2-174 QueryNormalizePhysicalAITypeClassifyNode (outer pre_process slot).

Normalize the physical-AI HITL compliance question; detect language;
deterministically classify the physical AI type per METI v1.2 taxonomy.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.degradation import EMPTY_INPUT
from src.services.service import classify_physical_ai_type, detect_language, extract_audit_safe_topic, normalize_query


class QueryNormalizePhysicalAITypeClassifyNode(FunctionNode):
    """Normalize the query, detect language, and classify the physical AI type."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the request...",
            metadata={"step": "pre_process"},
        )
        user_input = state.get("user_input", "")

        normalized, error = normalize_query(user_input)
        if error:
            # The caller can act on this, so the run completes and carries the reason.
            emit_trace_event("physical_ai_hitl_query_refused", {"error_code": EMPTY_INPUT}, state)
            return {
                "error_code": EMPTY_INPUT,
                "status": AgentStatus.SUCCESS.value,
            }

        language = detect_language(normalized)
        physical_ai_type = classify_physical_ai_type(normalized)

        emit_trace_event(
            "physical_ai_hitl_query_received", extract_audit_safe_topic(normalized, language, physical_ai_type), state
        )

        return {
            "query_language": language,
            "physical_ai_type": physical_ai_type,
            "validated_input": to_json(
                {"query": normalized, "language": language, "physical_ai_type": physical_ai_type}
            ),
            "status": AgentStatus.SUCCESS.value,
        }
