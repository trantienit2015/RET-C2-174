"""AgentCore Platform v1.0 - RET-C2-174 outer graph (Cat 2).

Cat 2: outer AgentBaseGraph with the fixed 5-node backbone. Domain complexity
is encapsulated in PhysicalAIHITLComplianceGraphNode (the `main` slot), which
wraps the inner PhysicalAIHITLComplianceWorkflowGraph. Do NOT override
add_edges().

hitl.enabled: false for this template - this is compliance-guidance Q&A about
METI v1.2 HITL requirements, not a HITL-enabled agent itself. The D6 interrupt()/memory_enabled contract does NOT apply.

Backbone: initialize -> pre_process(QueryNormalizePhysicalAITypeClassify) -> main(GraphNode)
          -> post_process(OutputValidate) -> finalize

PhysicalAIHITLComplianceGraphNode lives here (not under src/nodes/) - the PB-6
invoke-order test only discovers BaseNode subclasses under src/nodes/, and a
GraphNode's __call__ intentionally skips the standard S-2/S-4/S-3 lifecycle
(gating is delegated to the inner subgraph).
"""

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import OutputValidateNode
from src.nodes.pre_process_node import QueryNormalizePhysicalAITypeClassifyNode
from src.schemas.state import State


class PhysicalAIHITLComplianceGraphNode(GraphNode):
    """Wraps the inner METI v1.2 HITL compliance workflow (Cat 2 composition)."""

    # S-1: outer main-slot wrapper - first node in the outer backbone receiving
    # caller input; matches agent.yaml required_trust_level and sibling outer
    # nodes (pre_process/post_process). gate-trust-level-check does not scan
    # GraphNode subclasses, so this is not caught by CI - declare explicitly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    # "propagate": re-raise inner errors as SubgraphError (fail fast - default).
    error_strategy: ClassVar[str] = "propagate"
    # No HITL in this template - it answers Q&A ABOUT HITL requirements.
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any | None = None, kb: Any | None = None) -> None:
        super().__init__()
        self._llm = llm
        self._kb = kb or []

    def get_subgraph(self) -> AgentBaseGraph:
        from src.graph.domain_workflow_graph import PhysicalAIHITLComplianceWorkflowGraph

        sg = PhysicalAIHITLComplianceWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # Progress (non-terminal) event for the caller, emitted as the subgraph step
        # begins. Outside the Marketplace runtime this is a no-op emitter.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Working on the request...",
            metadata={"step": "main"},
        )
        emit_trace_event(
            "physical_ai_hitl_workflow_dispatched", {"correlation_id": state.get("correlation_id", "")}, state
        )
        value = state.get("validated_input", state.get("user_input", ""))
        return value if isinstance(value, str) else str(value)

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "physical_ai_hitl_workflow_completed",
            {"correlation_id": state.get("correlation_id", ""), "status": str(sub_result.get("status"))},
            state,
        )
        return {
            # Mapped explicitly like every other field - post_process reads it to report
            # a refusal instead of guidance. The outer marker wins: it names the specific
            # reason, while the inner node can only report the generic one.
            "error_code": state.get("error_code") or sub_result.get("error_code", ""),
            "retrieved_provisions": sub_result.get("retrieved_provisions"),
            "hitl_requirements": sub_result.get("hitl_requirements"),
            "guidance_draft": sub_result.get("guidance_draft"),
            "final_answer": sub_result.get("final_answer"),
            "result": sub_result.get("output"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"llm": self._llm, "kb": self._kb}


class RETC2174PhysicalAIHITLComplianceQA(AgentBaseGraph):
    """RET-C2-174 - Retail Physical AI & Autonomous Store Operations METI v1.2 HITL Compliance Q&A Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "ret-c2-174"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize

        llm = self.config.get("llm")
        kb = self.config.get("kb")

        self._nodes["pre_process"] = QueryNormalizePhysicalAITypeClassifyNode()
        self._nodes["main"] = PhysicalAIHITLComplianceGraphNode(llm=llm, kb=kb)
        self._nodes["post_process"] = OutputValidateNode()

    # add_edges() is NOT overridden - backbone wiring belongs to the framework.


# Stable alias for the standalone entry point import (src/api/server.py).
Graph = RETC2174PhysicalAIHITLComplianceQA
