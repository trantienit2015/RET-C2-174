# RET-C2-174 — Test Specification

## Test Strategy

Deterministic-core: `llm` is optional (guidance synthesis enrichment only), so
the full suite runs offline.

## Unit Tests (`tests/unit/test_nodes.py`)

| Node | Cases |
|---|---|
| QueryNormalizePhysicalAITypeClassifyNode | success (ja/en detected, physical_ai_type classified); empty query→degraded SUCCESS carrying `error_code: EMPTY_INPUT` |
| METIProvisionRetrieveNode | provisions retrieved from KB; missing query→degraded SUCCESS carrying `error_code: EMPTY_INPUT`; invalid physical_ai_type→ERROR (internally inconsistent run — the classifier only ever emits allowed values) |
| HITLRequirementMapNode | requirements mapped from provisions; missing provisions→ERROR (internally inconsistent run) |
| GuidanceGenerateNode | deterministic fallback guidance + citations assembled |
| OutputValidateNode | success; upstream error short-circuit; non-suppressible hook withholds guidance with a non-KB-grounded citation→SUCCESS + `CITATION_WITHHELD`, or a missing disclaimer→SUCCESS + `DISCLAIMER_WITHHELD` |

## Integration Tests (`tests/integration/test_graph.py`)

| ID | Test | Expected |
|---|---|---|
| I-1 | checkout robot HITL question with KB match | SUCCESS; ≥5 nodes; citation present; disclaimer present |
| I-2 | empty query | SUCCESS; `output` is the caller-facing reason for the refusal, no guidance |
| I-2b | empty query, knowledge base raises if searched | SUCCESS with the same reason; the provision search is never reached |
| I-3 | query with no KB match | SUCCESS; low confidence; disclaimer still present |
| I-4 | invalid physical AI type re-checked in inner node | error (defense in depth) |
| I-5 | configured LLM raises on the call | `status=error`, `output=None`; `GUIDANCE_MODEL_UNAVAILABLE` in `error_log` (unit) |

### How each outcome is reported

A request with no question in it is refused as `EMPTY_INPUT`. Guidance reaching the output
with a citation that is not knowledge-base grounded, or without its mandatory implementation
disclaimer, is withheld as a policy outcome (`CITATION_WITHHELD` / `DISCLAIMER_WITHHELD`);
`status=SUCCESS` there means the request was handled safely, not that guidance was returned.

A security failure (credential-shaped content), an invariant failure, and a configured LLM
that fails or returns nothing (I-5, `GUIDANCE_MODEL_UNAVAILABLE` in `error_log`) end as
`status=ERROR` and are never represented as a successful completion.

## Proof-of-Boundary Tests (`tests/proof_of_boundary/`)

| PB-ID | Boundary | Test | Expected Result |
|-------|----------|------|----------------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass |
| PB-6 | Invoke execution order | S-1 → node_start → S-2 → execute → S-3 → node_complete | Order verified |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result |
|-------|------|-------|----------------|
| BL-01 | checkout robot classification | "自動精算機のHITL要件は具体的に何か" | physical_ai_type=checkout_robot |
| BL-02 | shelf scanner classification | "棚スキャンロボットの異常検知時のオーバーライド手順" | physical_ai_type=shelf_scanner |
| BL-03 | no KB match | generic unrelated question | confidence=0.0, disclaimer still present |
| BL-04 | citation always KB-grounded | any substantive answer | citations only carry `section` key |

## Non-suppressible citation-grounding + disclaimer tests (critical)

- The post_process S-3 hook checks the answer's own `citations` field only
  (the hook only receives the node's own result dict) — never cross-references separate state fields; blocks any
  citation entry carrying fields beyond `section` (never a fabricated free-text
  citation).
- The post_process S-3 hook also blocks any answer missing the mandatory
  implementation disclaimer.
- Audit events never contain the raw query text — language + physical_ai_type +
  query_length only.

## Test Execution Summary
- Execution date: 2026-07-07
- Total tests: see CI run
- Coverage: node-level unit + full-graph integration + PB-2/PB-4/PB-6

## 1. Deployment path tests

### TC-DEP-01 Marketplace entry point identity — `tests/unit/test_cli_entry_point.py`

| Case | Expected |
|---|---|
| Identity is concrete | `agent_name` / `namespace` are non-empty and not the runner default |
| Identity matches the HTTP entry point | the values equal what `src/api/server.py` passes to `secrets_factory`; where that entry point provisions no secrets, they equal the manifest `namespace` and the lower-cased template id |
| The runner call uses the constants | `run_agent_marketplace` is called with the module constants, not inline literals |

### TC-DEP-02 Standalone entry point boundary — `tests/proof_of_boundary/test_server_llm_injection.py`

| Case | Expected |
|---|---|
| Boots with no credential provisioned | the module imports and the app/agent objects are constructed |
| External bearer never reaches the internal level | resolves to the verified-external level |
| Staging runner credential reaches the internal level | resolves to the internal level |
| Wrong or missing bearer while auth is enabled | rejected with 401 |
