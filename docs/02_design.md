# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `RETC2174PhysicalAIHITLComplianceQA`
- **L1 Base**: AgentBaseGraph
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

Cat 2: outer `AgentBaseGraph` (fixed 5-node backbone) + `GraphNode` in the `main`
slot wrapping an inner `BaseGraph` (3-step linear domain workflow).

### Node Configuration (outer)

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version/session_id/trust_level | - | - | InitializeNode (default) |
| pre_process | `QueryNormalizePhysicalAITypeClassifyNode` — normalize query, classify physical AI type | `user_input` | `query_language`, `physical_ai_type`, `validated_input` | FunctionNode |
| main | `PhysicalAIHITLComplianceGraphNode` — wraps inner workflow | `validated_input` | `retrieved_provisions`, `hitl_requirements`, `guidance_draft`, `final_answer` | GraphNode |
| post_process | `OutputValidateNode` — assemble output, non-suppressible citation-shape + disclaimer re-check | `final_answer` | `formatted_output`, `result` | FunctionNode |
| finalize | response_metadata, total_time_ms | - | - | FinalizeNode (default) |

### Node Configuration (inner, canonical flow)

| Node | Responsibility |
|------|-----------------|
| `METIProvisionRetrieveNode` | KB-backed retrieval of applicable METI v1.2 provisions scoped by physical_ai_type; re-checks query/physical_ai_type validity (the pre_process→main edge is unconditional) |
| `HITLRequirementMapNode` | Deterministic mapping table (no LLM) from provisions to HITL obligations (mandatory conditions, override procedures, contact-risk assessment) |
| `GuidanceGenerateNode` | LLM-essential — synthesizes compliance guidance with METI citations; deterministic fallback |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                            ↓ (retry)
                                          pre_process

Inner (main slot): START → meti_provision_retrieve → hitl_requirement_map
                         → guidance_generate → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `query_language` | str | "ja"/"en" | NotRequired |
| `physical_ai_type` | str | "checkout_robot"/"shelf_scanner"/"delivery_bot"/"autonomous_store"/"unknown" | NotRequired |
| `retrieved_provisions` | str\|None (JSON) | list[{section, snippet}] | NotRequired |
| `hitl_requirements` | str\|None (JSON) | list[{condition, procedure}] | NotRequired |
| `guidance_draft` | str | draft synthesized guidance text | NotRequired |
| `final_answer` | str\|None (JSON) | final answer + citations + disclaimer | NotRequired |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## HITL Scope Clarification

`hitl.enabled: false` — this template is compliance-guidance Q&A about METI v1.2
HITL requirements for physical AI. It does NOT itself run a HITL workflow. The
D6 `interrupt()` + `memory_enabled` contract does NOT apply; `propagate_hitl` is
`False` on `PhysicalAIHITLComplianceGraphNode`.

## KB Suitability

The KB (METI AI Operator Guideline v1.2 + retail physical-AI deployment docs) is
a legitimate KB use per the locked rationale: regulatory text, version-pinned,
updated infrequently (major revisions only), requires semantic retrieval (not
keyword-navigable). KB refresh trigger: new METI AI Operator Guideline version.

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [x] S-2: `QueryNormalizePhysicalAITypeClassifyNode` normalizes and
      length-validates the incoming question. A request with no question in it is
      refused as a degraded run: the node returns SUCCESS with
      `error_code: EMPTY_INPUT` and no guidance, and the routing short-circuits the
      METI provision search. The run completes and tells the caller what to send
      instead. A configured language model that fails or returns nothing is a runtime
      dependency failure: the run ends as `status=ERROR` with `GUIDANCE_MODEL_UNAVAILABLE`
      recorded in `error_log` and the audit event, and no guidance is passed off as an
      answer. Guidance failing the output checks below is withheld
      as a policy outcome (`CITATION_WITHHELD` / `DISCLAIMER_WITHHELD`); an internally
      inconsistent run ends as `status=ERROR`.

**A composing caller branches on `error_code`, not on `status`.** `status=SUCCESS` with a
non-empty `error_code` means the run completed and no guidance was produced; the code says
why the agent declined (`EMPTY_INPUT`, or a `*_WITHHELD` policy outcome). A run that could
not perform ends as `status=ERROR`. `merge_output` maps the marker to the parent.
- [x] S-3: `OutputValidateNode._extra_security_gate_output()` — non-suppressible
      re-check that every citation entry carries ONLY a `section` field
      (KB-grounded, never fabricated) and the mandatory implementation disclaimer
      is present
- [x] S-4: `emit_trace_event()` — domain events at every node (query received,
      provisions retrieved, requirements mapped, guidance generated/validated)

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### Composition Pattern

- **Pattern**: GraphNode (subgraph)
- **Composition target**: `PhysicalAIHITLComplianceWorkflowGraph` (inner `BaseGraph`)
- **Error propagation strategy**: propagate (fail fast; no HITL in this template)

## Outcome classification

Each way a run can end without guidance falls into one class, and the class decides how it
is reported.

| Class | In this agent | Reported as |
|---|---|---|
| Security failure | Credential-shaped content detected by the baseline S-3 gate | `status=ERROR`, `output=None` |
| Policy withholding | Guidance citing material outside the knowledge base, or lacking the implementation disclaimer | `status=SUCCESS`, `error_code` = `CITATION_WITHHELD` / `DISCLAIMER_WITHHELD`, fixed notice, no guidance body |
| Caller-correctable | A request with no question in it | `status=SUCCESS`, `error_code=EMPTY_INPUT` |
| Dependency failure | A configured language model fails or returns nothing | `status=ERROR`; the code is recorded in `error_log` and the audit event, never as a completed run (`GUIDANCE_MODEL_UNAVAILABLE`) |
| Invariant failure | An invalid `physical_ai_type`, missing provisions, or a missing assembled answer | `status=ERROR`; never represented as successful completion |

Credential-shaped content detected by baseline S-3 causes fail-closed termination:
`status=ERROR`, `output=None`. The template does not transform this terminal status to SUCCESS
and does not emit any source-derived response.

On a policy-withholding or caller-correctable run, `status=SUCCESS` means the agent finished
handling the request safely; it does not mean guidance was returned. The notice is derived from
the `error_code` alone, so nothing from the request is echoed back.

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Fixed multi-step compliance Q&A workflow, no self-directed loop needed |
| Composition pattern | Standalone nodes | GraphNode (subgraph) | GraphNode | Cat 2 domain complexity (3-step inner workflow) encapsulated per scaffold convention |
| HITL enablement | hitl.enabled: true | hitl.enabled: false | false | Template answers Q&A about HITL requirements; it does not itself execute a HITL workflow |

## 1. Deployment entry points

The agent is reachable through two entry points, and both resolve their runtime inputs the same way.

| Entry point | File | Used by |
|---|---|---|
| Standalone HTTP | `src/api/server.py` | staging rehearsal, direct invocation |
| Marketplace one-shot Pod | `cli.py` | the platform runner (container `CMD`) |

Both read runtime parameters from `config/config.yaml` — the manifest carries discovery metadata
only — and both scope secrets to the same location (`namespace=ret`, `agent_name=ret-c2-174`), so a
secret provisioned for one path resolves identically on the other.

**Deployment-provided LLM client.** The three Azure OpenAI connection values
(`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` — the bare resource endpoint — and
`AZURE_OPENAI_DEPLOYMENT`) are resolved through the agent's own secret provider, never from the
process environment. The standalone entry point passes a client as `config["llm"]` only when the
provider client is available and all three values already resolve at startup; otherwise the key
stays unset and the graph runs its deterministic path. The Marketplace entry point cannot resolve
the values while the graph is built, so whenever the provider client is available it passes a
client that resolves them on each call. A value missing at that point makes the call fail, and the
run ends as `status=ERROR` with `GUIDANCE_MODEL_UNAVAILABLE` recorded in `error_log` and the audit
event; neither the value nor the provider's own error text is returned. The manifest declares the
three secrets and the provider extra.

**Progress events.** Each pipeline stage emits a non-terminal progress event at its start, so a
caller sees the run advancing. Outside the Marketplace runtime the emitter resolves to a no-op, so
the same code is safe on every path. Terminal events belong to the platform runner and are never
emitted by this agent.

**Caller authentication at the standalone entry point.** A caller that no upstream middleware
vouched for stays anonymous unless it presents a deployment-level credential: the external bearer
token grants the verified-external level, and a separate staging-only runner credential is the only
way to reach the internal level. Trust established upstream is never changed.
