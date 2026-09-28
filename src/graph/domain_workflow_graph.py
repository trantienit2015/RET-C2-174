"""AgentCore Platform v1.0 - RET-C2-174 inner domain workflow graph.

Cat 2 inner graph: METI provision retrieval + HITL requirement mapping +
guidance generation with citation attach. Instantiated by
PhysicalAIHITLComplianceGraphNode.get_subgraph() in graph.py.

Pipeline (linear, fail-fast on ERROR):
    START -> meti_provision_retrieve -> hitl_requirement_map
          -> guidance_generate -> END
"""

from typing import Any

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from langgraph.graph import END, START

from src.nodes.guidance_generate_node import GuidanceGenerateNode
from src.nodes.hitl_requirement_map_node import HITLRequirementMapNode
from src.nodes.meti_provision_retrieve_node import METIProvisionRetrieveNode
from src.schemas.state import State


class PhysicalAIHITLComplianceWorkflowGraph(BaseGraph):
    """Inner graph for the RET-C2-174 METI v1.2 HITL compliance Q&A workflow."""

    @property
    def name(self) -> str:
        return "physical-ai-hitl-compliance-workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config: llm and kb are optional (deterministic fallback exists).
        pass

    def register_nodes(self) -> None:
        # No super() - BaseGraph.register_nodes() is abstract.
        llm = self.config.get("llm")
        kb = self.config.get("kb")

        self._nodes["meti_provision_retrieve"] = METIProvisionRetrieveNode(kb=kb)
        self._nodes["hitl_requirement_map"] = HITLRequirementMapNode()
        self._nodes["guidance_generate"] = GuidanceGenerateNode(llm=llm)

    def add_edges(self) -> None:
        self._sg.add_edge(START, "meti_provision_retrieve")
        self._sg.add_conditional_edges(
            "meti_provision_retrieve",
            lambda s: END if self._is_error(s) else "hitl_requirement_map",
            {"hitl_requirement_map": "hitl_requirement_map", END: END},
        )
        self._sg.add_conditional_edges(
            "hitl_requirement_map",
            lambda s: END if self._is_error(s) else "guidance_generate",
            {"guidance_generate": "guidance_generate", END: END},
        )
        self._sg.add_edge("guidance_generate", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        # A degraded rejection ends the run as SUCCESS, so keying only on the status
        # would let the remaining nodes run on a request that was already refused.
        return bool(state.get("error_code")) or state.get("status") == AgentStatus.ERROR.value

    def route(self, state: AgentState) -> str:
        return END if self._is_error(state) else "guidance_generate"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "error_code": state.get("error_code"),
            "retrieved_provisions": state.get("retrieved_provisions"),
            "hitl_requirements": state.get("hitl_requirements"),
            "guidance_draft": state.get("guidance_draft"),
            "final_answer": state.get("final_answer"),
            "output": state.get("final_answer"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
