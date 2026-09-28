"""AgentCore Platform v1.0 - RET-C2-174 state schema."""

# ADR-005: State must be a flat TypedDict - never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects (and nested
# dict/list containers) are not msgpack-safe. Extend AgentState with agent-specific
# fields only. Nested list/dict fields are stored as JSON strings and
# (de)serialized at the node boundary via to_json/from_json below. Do NOT add
# credentials, secrets, or Pydantic models.
#
# hitl.enabled: false for this template - this is compliance-guidance Q&A about
# METI v1.2 HITL requirements, not a HITL-enabled agent itself. The D6 interrupt()/memory_enabled contract does NOT apply.

from __future__ import annotations

import json
from typing import Any, NotRequired, Optional

from framework.schemas.agent_state import AgentState


def to_json(value: Any) -> Optional[str]:
    """Serialize a list/dict State value to a compact JSON string (ADR-005, msgpack-safe)."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def from_json(value: Any, default: Any) -> Any:
    """Deserialize a JSON-string State value back to its list/dict form (tolerant)."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class State(AgentState):
    """Retail physical AI & autonomous store operations METI v1.2 HITL compliance Q&A state.

    Shared fields (user_input, validated_input, status, session_id, node_history,
    error_log, result, formatted_output, hitl_*, etc.) are inherited from AgentState.
    Only agent-specific, flat, JSON-serializable fields are declared below; all are
    NotRequired (written mid-pipeline).
    """

    # Outcome marker. A run that completes without guidance - a caller-correctable refusal or
    # a policy withholding - carries this code, and its output says why in wording
    # derived from the code alone (src/services/degradation.py). A security failure or
    # an internally inconsistent run ends as status=ERROR instead.
    error_code: NotRequired[str]

    query_language: NotRequired[str]  # "ja" | "en"
    physical_ai_type: NotRequired[
        str
    ]  # "checkout_robot" | "shelf_scanner" | "delivery_bot" | "autonomous_store" | "unknown"
    # JSON list[{section, snippet}] - retrieved METI v1.2 provisions (KB-backed only).
    retrieved_provisions: NotRequired[str | None]
    # JSON list[{condition, procedure}] - mapped HITL obligations.
    hitl_requirements: NotRequired[str | None]
    guidance_draft: NotRequired[str]
    final_answer: NotRequired[str | None]  # JSON final answer + citations + disclaimer
