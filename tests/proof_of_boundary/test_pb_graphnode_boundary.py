# GraphNode boundary test (Cat 2) - PB-6 only discovers BaseNode subclasses
# under src/nodes/; PhysicalAIHITLComplianceGraphNode lives under src/graph/
# (matches scaffold canonical placement, see src/graph/graph.py docstring),
# so it is outside PB-6's discovery walk. This is a real security boundary
# (first node receiving caller input) and must be probed independently:
# S-1 trust-gate rejection, and the extract_input/merge_output field-mapping
# boundary (criterion #9 - no raw pass-through).

from framework.schemas.trust_level import TrustLevel

from src.graph.graph import PhysicalAIHITLComplianceGraphNode


def _base_state(**overrides) -> dict:
    state = {
        "correlation_id": "corr-pb6-graphnode",
        "user_input": '{"query": "what are HITL override procedures?"}',
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
    }
    state.update(overrides)
    return state


class TestGraphNodeS1TrustGate:
    """S-1: caller below required_trust_level must be rejected before execute()."""

    def test_anonymous_caller_denied(self):
        node = PhysicalAIHITLComplianceGraphNode(llm=None, kb=[])
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)

        result = node(state)

        assert result["status"] == "error"
        assert any("S-1 trust gate denied" in msg for msg in result["error_log"])
        # execute() (which would dispatch to the inner subgraph) must not run.
        assert "physical_ai_hitl_workflow_dispatched" not in str(result)

    def test_verified_external_caller_allowed_to_reach_execute(self, monkeypatch):
        node = PhysicalAIHITLComplianceGraphNode(llm=None, kb=[])
        called = {}

        def fake_execute(self, state):
            called["ran"] = True
            return {"status": "success"}

        monkeypatch.setattr(PhysicalAIHITLComplianceGraphNode, "execute", fake_execute)
        state = _base_state(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL.value)

        result = node(state)

        assert called.get("ran") is True
        assert result["status"] == "success"


class TestGraphNodeBoundaryMapping:
    """extract_input/merge_output must map fields explicitly (criterion #9)."""

    def test_extract_input_only_reads_contract_fields(self):
        node = PhysicalAIHITLComplianceGraphNode(llm=None, kb=[])
        state = _base_state(
            validated_input='{"query": "checkout robot escalation"}',
            unrelated_secret="should-not-leak",
        )

        extracted = node.extract_input(state)

        assert extracted == state["validated_input"]
        assert "unrelated_secret" not in extracted

    def test_extract_input_falls_back_to_user_input(self):
        node = PhysicalAIHITLComplianceGraphNode(llm=None, kb=[])
        state = _base_state()
        state.pop("validated_input", None)

        extracted = node.extract_input(state)

        assert extracted == state["user_input"]

    def test_merge_output_maps_fields_explicitly_no_raw_passthrough(self):
        node = PhysicalAIHITLComplianceGraphNode(llm=None, kb=[])
        state = _base_state()
        sub_result = {
            "retrieved_provisions": ["prov-1"],
            "hitl_requirements": ["req-1"],
            "guidance_draft": "draft text",
            "final_answer": {"answer": "final"},
            "output": {"answer": "final"},
            "status": "success",
            "internal_subgraph_only_field": "must-not-leak-to-parent",
        }

        merged = node.merge_output(state, sub_result)

        # mapped explicitly like every other field - post_process reads it to report a
        # refusal instead of guidance
        assert "error_code" in merged
        assert merged["retrieved_provisions"] == ["prov-1"]
        assert merged["hitl_requirements"] == ["req-1"]
        assert merged["guidance_draft"] == "draft text"
        assert merged["final_answer"] == {"answer": "final"}
        assert merged["result"] == {"answer": "final"}
        assert merged["status"] == "success"
        # Explicit field mapping only - no pass-through of the raw sub_result dict.
        assert "internal_subgraph_only_field" not in merged

    def test_merge_output_keeps_the_outer_refusal_over_the_inner_one(self):
        """The outer step names the specific reason; the inner node, seeded with the
        request text alone, can only report the generic one. Composing inner-first would
        overwrite the specific reason with the generic one."""
        node = PhysicalAIHITLComplianceGraphNode(llm=None, kb=[])
        state = _base_state(error_code="OUTER_REASON")

        merged = node.merge_output(state, {"error_code": "INNER_REASON", "status": "success"})

        assert merged["error_code"] == "OUTER_REASON"


class TestGraphNodeInnerDelegatesGating:
    """Delegation is deliberate: GraphNode.execute() dispatches to the inner
    subgraph, a compiled BaseGraph whose own nodes run the standard
    S-2/S-4/S-3 pipeline via BaseNode.__call__(). See
    framework/nodes/graph_node.py (GraphNode.execute -> subgraph.invoke) and
    src/graph/domain_workflow_graph.py for the inner backbone that performs
    the actual gating - this is a design choice, not a gap.
    """

    def test_inner_subgraph_is_a_compiled_base_graph(self):
        node = PhysicalAIHITLComplianceGraphNode(llm=None, kb=[])
        subgraph = node.get_subgraph()

        from framework.graph.base_graph import BaseGraph

        assert isinstance(subgraph, BaseGraph)
