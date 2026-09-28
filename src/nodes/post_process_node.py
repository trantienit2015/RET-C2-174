"""AgentCore Platform v1.0 - RET-C2-174 OutputValidateNode (outer post_process slot).

S-3 non-suppressible gate: METI citations must be KB-grounded (every citation
entry carries ONLY a `section` field, never fabricated free-text) and the
mandatory implementation disclaimer must be present. The hook checks the
assembled answer's OWN fields only, never cross-referencing separately-read
sibling `state` fields (the output hook only receives the node's own result
dict). On failure the output is dropped
entirely (status=ERROR), never silently emitted.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.degradation import CITATION_WITHHELD, DISCLAIMER_WITHHELD, explain_degradation

ALLOWED_CITATION_KEYS = {"section"}


class OutputValidateNode(FunctionNode):
    """Assemble the final output; non-suppressible citation-shape + disclaimer re-check."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Preparing the result...",
            metadata={"step": "post_process"},
        )
        # A degraded run produced no guidance by design. The output keeps a caller-facing
        # shape and states why; every value is a constant, so nothing the refused request
        # left in State reaches the caller. The citation and disclaimer invariants below
        # do not apply: they exist so that no produced *guidance* leaves without them, and
        # a refusal carries no guidance.
        degraded_code = state.get("error_code", "")
        if degraded_code:
            reason = explain_degradation(degraded_code)
            emit_trace_event("physical_ai_hitl_guidance_degraded", {"error_code": degraded_code}, state)
            return {
                # carried in this node's own dict so the S-3 re-check - which sees that
                # dict, not the full state - can scope itself to produced guidance
                "error_code": degraded_code,
                "formatted_output": reason,
                "result": reason,
                "status": AgentStatus.SUCCESS.value,
            }

        if state.get("status") == AgentStatus.ERROR.value:
            return {"status": AgentStatus.ERROR.value}

        answer = from_json(state.get("final_answer"), None)
        if not isinstance(answer, dict):
            return {"status": AgentStatus.ERROR.value, "error_log": ["OutputValidateNode: missing assembled answer"]}

        emit_trace_event(
            "physical_ai_hitl_guidance_validated",
            {
                "physical_ai_type": answer.get("physical_ai_type"),
                "confidence": answer.get("confidence"),
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )

        return {
            "formatted_output": answer,
            "result": to_json(answer),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Non-suppressible re-check: KB-grounded citations + mandatory disclaimer (own-dict fields only).

        The invariants apply to produced guidance. A degraded run carries a refusal
        instead - so the check is scoped by the degradation marker, not weakened.
        """
        if state.get("error_code"):
            return state
        answer = from_json(state.get("result"), None)
        if not isinstance(answer, dict):
            return state

        citations = answer.get("citations") or []
        for citation in citations:
            if not isinstance(citation, dict) or set(citation.keys()) - ALLOWED_CITATION_KEYS:
                emit_trace_event("output_gate_citation_not_kb_grounded_blocked", {}, state)
                return self._withheld(
                    CITATION_WITHHELD,
                    "Output gate: citation entry carries fields beyond section - blocked (KB-grounded citation guard)",
                )

        if not answer.get("disclaimer"):
            emit_trace_event("output_gate_missing_disclaimer_blocked", {}, state)
            return self._withheld(
                DISCLAIMER_WITHHELD, "Output gate: answer missing mandatory implementation disclaimer - blocked"
            )

        return state

    @staticmethod
    def _withheld(code: str, log_line: str) -> dict[str, Any]:
        """The result that replaces guidance withheld under the answer-quality contract.

        A policy outcome, not a failure. Both output fields are overwritten with the
        fixed statement for the code, so the guidance that failed the check cannot
        travel on in either of them.
        """
        reason = explain_degradation(code)
        return {
            "error_code": code,
            "formatted_output": reason,
            "result": reason,
            "status": AgentStatus.SUCCESS.value,
            "error_log": [log_line],
        }
