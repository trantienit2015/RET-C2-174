"""AgentCore Platform v1.0 - RET-C2-174 GuidanceGenerateNode (inner subgraph, step 3).

LLM-essential answer synthesis from mapped HITL requirements + mandatory
citation attach (METI section) on every substantive answer. Deterministic
fallback when no LLM is configured.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.degradation import GUIDANCE_MODEL_UNAVAILABLE
from src.services.service import assemble_final_answer, build_citations, build_guidance_fallback


class GuidanceGenerateNode(FunctionNode):
    """Generate the HITL compliance guidance + attach mandatory citations."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any | None = None) -> None:
        super().__init__()
        self._llm = llm

    @staticmethod
    def _extract_text(raw: Any) -> str:
        """Normalize BaseLLM.complete() response (canonical dict {"content": str, ...},
        with backward-compat for fake/string-returning test doubles) to plain text."""
        if isinstance(raw, dict):
            content = raw.get("content", "")
            return content if isinstance(content, str) else ""
        if isinstance(raw, str):
            return raw
        return ""

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        parsed = from_json(state.get("user_input"), {})
        query = parsed.get("query", "") if isinstance(parsed, dict) else ""
        language = parsed.get("language", "en") if isinstance(parsed, dict) else "en"
        physical_ai_type = parsed.get("physical_ai_type", "unknown") if isinstance(parsed, dict) else "unknown"
        hitl_requirements = from_json(state.get("hitl_requirements"), [])
        provisions = from_json(state.get("retrieved_provisions"), [])

        if self._llm is None:
            # Deterministic-core mode: no LLM configured, fallback is the intended path.
            guidance_text, confidence = build_guidance_fallback(hitl_requirements, physical_ai_type)
        else:
            # An LLM IS configured: a call failure / empty / malformed response must not
            # fall back to the deterministic guidance (the caller could not otherwise
            # tell "LLM answered" from "LLM failed"). It is reported as its own outcome.
            prompt = f"Answer this METI v1.2 HITL compliance question in {language} using these requirements: {hitl_requirements}. Question: {query}"
            try:
                raw = self._llm.complete([{"role": "user", "content": prompt}])
            except (
                Exception
            ) as exc:  # provider-specific exception types are unknown at this layer; never passed off as an answer
                emit_trace_event(
                    "physical_ai_hitl_llm_call_failed",
                    {
                        "error_code": GUIDANCE_MODEL_UNAVAILABLE,
                        "error": str(exc),
                        "correlation_id": state.get("correlation_id", ""),
                    },
                    state,
                )
                # A runtime dependency failure ends the run as status=ERROR. The code
                # travels in error_log and the audit event, not in error_code, which marks
                # a run that completed without an answer. No guidance is produced.
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [
                        f"{GUIDANCE_MODEL_UNAVAILABLE}: GuidanceGenerateNode: LLM call failed ({type(exc).__name__})"
                    ],
                }

            guidance_text = self._extract_text(raw)
            if not guidance_text:
                emit_trace_event(
                    "physical_ai_hitl_llm_empty_response",
                    {"error_code": GUIDANCE_MODEL_UNAVAILABLE, "correlation_id": state.get("correlation_id", "")},
                    state,
                )
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [f"{GUIDANCE_MODEL_UNAVAILABLE}: GuidanceGenerateNode: LLM returned empty content"],
                }
            confidence = min(1.0, 0.6 + 0.1 * len(hitl_requirements))

        citations = build_citations(provisions)
        final_answer = assemble_final_answer(language, physical_ai_type, guidance_text, confidence, citations)

        emit_trace_event(
            "physical_ai_hitl_guidance_generated",
            {
                "physical_ai_type": physical_ai_type,
                "confidence": confidence,
                "llm_used": self._llm is not None,
                "correlation_id": state.get("correlation_id", ""),
            },
            state,
        )

        return {
            "guidance_draft": guidance_text,
            "final_answer": to_json(final_answer),
            "status": AgentStatus.SUCCESS.value,
        }
