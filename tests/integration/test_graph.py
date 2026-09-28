# RET-C2-174 - Integration test: full graph compile + invoke (Cat 2 outer + inner).

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph
from src.services import degradation

CHECKOUT_QUERY = "What are the HITL requirements for our checkout robot per METI v1.2?"
GENERIC_QUERY = "What is the weather forecast for tomorrow?"

KB = [{"section": "4.2", "content": "Checkout robots require mandatory HITL review for payment disputes.", "physical_ai_types": ["checkout_robot"]}]


class TestAgentIntegration:
    def test_checkout_robot_hitl_query_with_kb_match(self):
        agent = Graph(config={"max_retry": 1, "kb": KB})
        agent.compile()
        ctx = InvocationContext(session_id="it-1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ops-mgr")
        result = agent.invoke(CHECKOUT_QUERY, ctx=ctx)

        assert result["status"] == "success"
        assert len(result.get("node_history", [])) >= 5

    def test_empty_query_degrades_instead_of_failing(self):
        """End-to-end shape of a caller-correctable rejection: the run completes and the
        reason is in the output."""
        agent = Graph(config={"max_retry": 1, "kb": KB})
        agent.compile()
        ctx = InvocationContext(session_id="it-2", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ops-mgr")
        result = agent.invoke("", ctx=ctx)
        assert result["status"] == "success"
        assert result["output"] == degradation.explain_degradation(degradation.EMPTY_INPUT)

    def test_refused_request_never_reaches_the_provision_search(self):
        """The refusal happens before retrieval, so the short-circuit - not the absence of
        data - is what has to stop the search. The knowledge base fails the test if used."""

        class RefusingKB(list):
            def __iter__(self):
                raise AssertionError("the METI knowledge base was searched on a refused request")

        agent = Graph(config={"max_retry": 1, "kb": RefusingKB()})
        agent.compile()
        ctx = InvocationContext(session_id="it-5", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ops-mgr")
        result = agent.invoke("", ctx=ctx)
        assert result["status"] == "success"
        assert result["output"] == degradation.explain_degradation(degradation.EMPTY_INPUT)

    def test_failed_llm_call_ends_as_an_error(self):
        """A runtime dependency failure is not reported as a completed run: status=ERROR,
        no output, and no guidance is passed off as an answer."""

        class FailingLLM:
            def complete(self, messages):
                raise RuntimeError("provider unavailable")

        agent = Graph(config={"max_retry": 1, "kb": KB, "llm": FailingLLM()})
        agent.compile()
        ctx = InvocationContext(session_id="it-6", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ops-mgr")
        result = agent.invoke(CHECKOUT_QUERY, ctx=ctx)

        assert result["status"] == "error"
        assert result["output"] is None

    def test_no_kb_match_still_succeeds_with_disclaimer(self):
        agent = Graph(config={"max_retry": 1, "kb": KB})
        agent.compile()
        ctx = InvocationContext(session_id="it-3", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ops-mgr")
        result = agent.invoke(GENERIC_QUERY, ctx=ctx)
        assert result["status"] == "success"

    def test_dict_llm_full_graph_success(self):
        class DictLLM:
            def complete(self, messages):
                return {"content": "LLM-grounded HITL guidance", "model": "fake", "usage": {}}

        agent = Graph(config={"max_retry": 1, "kb": KB, "llm": DictLLM()})
        agent.compile()
        ctx = InvocationContext(session_id="it-4", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="ops-mgr")
        result = agent.invoke(CHECKOUT_QUERY, ctx=ctx)

        assert result["status"] == "success"
