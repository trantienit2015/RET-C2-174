# RET-C2-174 - Unit tests: per-node success + error/edge paths.

from framework.schemas.agent_status import AgentStatus

from src.nodes.guidance_generate_node import GuidanceGenerateNode
from src.nodes.hitl_requirement_map_node import HITLRequirementMapNode
from src.nodes.meti_provision_retrieve_node import METIProvisionRetrieveNode
from src.nodes.post_process_node import OutputValidateNode
from src.nodes.pre_process_node import QueryNormalizePhysicalAITypeClassifyNode
from src.schemas.state import from_json, to_json
from src.services.degradation import CITATION_WITHHELD, DISCLAIMER_WITHHELD, EMPTY_INPUT, GUIDANCE_MODEL_UNAVAILABLE

KB = [{"section": "4.2", "content": "Checkout robots require mandatory HITL review for payment disputes.", "physical_ai_types": ["checkout_robot"]}]


class TestQueryNormalizePhysicalAITypeClassifyNode:
    def test_success(self):
        state = {"user_input": "What are the HITL requirements for our checkout robot?"}
        r = QueryNormalizePhysicalAITypeClassifyNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["physical_ai_type"] == "checkout_robot"

    def test_empty_query_degrades(self):
        # The reason travels as an allow-listed code on a completed run; asserting the
        # status alone would also pass on a node that silently produced no guidance.
        r = QueryNormalizePhysicalAITypeClassifyNode().execute({"user_input": ""})
        assert r["status"] == AgentStatus.SUCCESS.value
        assert r["error_code"] == EMPTY_INPUT


def _inner_state(query="checkout robot HITL", language="en", physical_ai_type="checkout_robot"):
    return {"user_input": to_json({"query": query, "language": language, "physical_ai_type": physical_ai_type})}


class TestMETIProvisionRetrieveNode:
    def test_success(self):
        r = METIProvisionRetrieveNode(kb=KB).execute(_inner_state())
        assert r["status"] == AgentStatus.SUCCESS
        provisions = from_json(r["retrieved_provisions"], [])
        assert len(provisions) >= 1

    def test_missing_query_degrades(self):
        r = METIProvisionRetrieveNode(kb=KB).execute({"user_input": ""})
        assert r["status"] == AgentStatus.SUCCESS.value
        assert r["error_code"] == EMPTY_INPUT

    def test_invalid_physical_ai_type_stays_an_error(self):
        """The classifier only ever emits allowed values, so reaching this means the run
        is internally inconsistent - not something the caller can correct by resending."""
        state = {"user_input": to_json({"query": "x", "language": "en", "physical_ai_type": "spaceship"})}
        assert METIProvisionRetrieveNode(kb=KB).execute(state)["status"] == AgentStatus.ERROR


class TestHITLRequirementMapNode:
    def test_success(self):
        provisions = [{"section": "4.2", "snippet": "mandatory HITL review"}]
        state = {**_inner_state(), "retrieved_provisions": to_json(provisions)}
        r = HITLRequirementMapNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        requirements = from_json(r["hitl_requirements"], [])
        assert len(requirements) == 1

    def test_missing_provisions_stays_an_error(self):
        """Reached only when the preceding step succeeded without writing its output -
        an internal inconsistency, not a caller-correctable rejection."""
        assert HITLRequirementMapNode().execute({**_inner_state(), "retrieved_provisions": None})["status"] == AgentStatus.ERROR


class TestGuidanceGenerateNode:
    def test_fallback_guidance_with_citations(self):
        requirements = [{"condition": "Mandatory HITL review applies per METI v1.2 4.2", "procedure": "Override procedure per 4.2"}]
        provisions = [{"section": "4.2", "snippet": "mandatory HITL review"}]
        state = {**_inner_state(), "hitl_requirements": to_json(requirements), "retrieved_provisions": to_json(provisions)}
        r = GuidanceGenerateNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        answer = from_json(r["final_answer"], {})
        assert len(answer["citations"]) == 1
        assert answer["disclaimer"]

    def test_no_match_zero_confidence(self):
        state = {**_inner_state(query="obscure topic"), "hitl_requirements": to_json([]), "retrieved_provisions": to_json([])}
        r = GuidanceGenerateNode().execute(state)
        answer = from_json(r["final_answer"], {})
        assert answer["confidence"] == 0.0
        assert answer["disclaimer"]

    def test_llm_dict_response_used(self):
        class DictLLM:
            def complete(self, messages):
                return {"content": "LLM-generated guidance", "model": "fake", "usage": {}}

        requirements = [{"condition": "Mandatory HITL review applies per METI v1.2 4.2", "procedure": "Override procedure per 4.2"}]
        state = {**_inner_state(), "hitl_requirements": to_json(requirements), "retrieved_provisions": to_json([])}
        r = GuidanceGenerateNode(llm=DictLLM()).execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["guidance_draft"] == "LLM-generated guidance"

    def test_llm_string_response_backward_compat(self):
        class StringLLM:
            def complete(self, messages):
                return "plain string guidance"

        state = {**_inner_state(), "hitl_requirements": to_json([]), "retrieved_provisions": to_json([])}
        r = GuidanceGenerateNode(llm=StringLLM()).execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert r["guidance_draft"] == "plain string guidance"

    def test_llm_raises_ends_as_an_error_without_guidance(self):
        # The code travels in error_log, not in error_code: that field marks a run that
        # completed without an answer, and a failure must never be read as one.
        class RaisingLLM:
            def complete(self, messages):
                raise ConnectionError("provider unreachable")

        state = {**_inner_state(), "hitl_requirements": to_json([]), "retrieved_provisions": to_json([])}
        r = GuidanceGenerateNode(llm=RaisingLLM()).execute(state)
        assert r["status"] == AgentStatus.ERROR.value
        assert "error_code" not in r
        assert "guidance_draft" not in r
        assert r["error_log"][0].startswith(f"{GUIDANCE_MODEL_UNAVAILABLE}:")

    def test_llm_empty_content_is_the_same_failure(self):
        class EmptyLLM:
            def complete(self, messages):
                return {"content": ""}

        state = {**_inner_state(), "hitl_requirements": to_json([]), "retrieved_provisions": to_json([])}
        r = GuidanceGenerateNode(llm=EmptyLLM()).execute(state)
        assert r["status"] == AgentStatus.ERROR.value
        assert "error_code" not in r
        assert r["error_log"][0].startswith(f"{GUIDANCE_MODEL_UNAVAILABLE}:")

class TestOutputValidateNode:
    def test_success(self):
        answer = {"language": "en", "physical_ai_type": "checkout_robot", "guidance": "x", "confidence": 0.8, "citations": [{"section": "4.2"}], "disclaimer": "consult SI/legal"}
        r = OutputValidateNode().execute({"final_answer": to_json(answer)})
        assert r["status"] == AgentStatus.SUCCESS

    def test_upstream_error_short_circuits(self):
        assert OutputValidateNode().execute({"status": AgentStatus.ERROR})["status"] == AgentStatus.ERROR

    def test_extra_gate_blocks_non_kb_grounded_citation(self):
        bad = to_json({"citations": [{"section": "4.2", "snippet": "leaked KB text"}], "disclaimer": "consult SI/legal"})
        out = OutputValidateNode()._extra_security_gate_output({"result": bad})
        # The KB snippet that must not leave is gone from every field.
        assert "leaked KB text" not in str(out)
        assert out["error_code"] == CITATION_WITHHELD

    def test_extra_gate_blocks_missing_disclaimer(self):
        bad = to_json({"citations": [{"section": "4.2"}], "disclaimer": None})
        out = OutputValidateNode()._extra_security_gate_output({"result": bad})
        assert "4.2" not in str(out)
        assert out["error_code"] == DISCLAIMER_WITHHELD

    def test_extra_gate_passthrough_valid_answer(self):
        good = to_json({"citations": [{"section": "4.2"}], "disclaimer": "consult SI/legal"})
        state = {"result": good}
        assert OutputValidateNode()._extra_security_gate_output(state) is state
