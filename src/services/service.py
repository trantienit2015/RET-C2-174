"""AgentCore Platform v1.0 - RET-C2-174 domain services.

Deterministic helpers only: query normalize, language detect, physical-AI-type
classification, METI v1.2 provision retrieval mock (KB-backed, real interface),
deterministic HITL-requirement mapping table, answer fallback + confidence
scoring, citation formatting, and audit-safe topic extraction. No agenticstar
imports.
"""

from __future__ import annotations

import re
from typing import Any

MAX_QUERY_LENGTH = 2000

JAPANESE_CHAR_PATTERN = re.compile(r"[぀-ヿ一-鿿]")

VALID_PHYSICAL_AI_TYPES = ("checkout_robot", "shelf_scanner", "delivery_bot", "autonomous_store", "unknown")

CONFIDENCE_THRESHOLD = 0.65
IMPLEMENTATION_DISCLAIMER = "Consult a qualified system integrator or legal counsel for site-specific implementation / 現場実装の詳細は専門のシステムインテグレーターまたは法律顧問にご相談ください。"


def normalize_query(raw_query: str) -> tuple[str, str | None]:
    """S-1: normalize + length-validate the incoming physical-AI compliance question."""
    if not isinstance(raw_query, str) or not raw_query.strip():
        return "", "query is empty or missing"
    return raw_query.strip()[:MAX_QUERY_LENGTH], None


def detect_language(query: str) -> str:
    """Deterministic language detection heuristic (ja by script; else en default)."""
    if JAPANESE_CHAR_PATTERN.search(query):
        return "ja"
    return "en"


def classify_physical_ai_type(query: str) -> str:
    """Deterministic keyword-based physical-AI-type classification per METI v1.2 taxonomy."""
    q = query.lower()
    if any(tok in q for tok in ("checkout", "精算機", "self-checkout", "cashier")):
        return "checkout_robot"
    if any(tok in q for tok in ("shelf", "棚スキャン", "shelf scanner", "shelf-scanning")):
        return "shelf_scanner"
    if any(tok in q for tok in ("delivery", "配送ロボット", "delivery bot", "delivery robot")):
        return "delivery_bot"
    if any(tok in q for tok in ("autonomous store", "無人店舗", "store operations")):
        return "autonomous_store"
    return "unknown"


def retrieve_meti_provisions(physical_ai_type: str, kb: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Deterministic mock vector search over the METI AI Operator Guideline v1.2
    KB, scoped by physical_ai_type. KB-backed only - never fabricates a section
    that is not present in the configured KB."""
    kb = kb or []
    matches = []
    for doc in kb:
        tags = doc.get("physical_ai_types", [])
        if physical_ai_type in tags or "all" in tags:
            matches.append({"section": doc.get("section", ""), "snippet": doc.get("content", "")[:200]})
    return matches[:5]


def map_hitl_requirements(provisions: list[dict[str, Any]], physical_ai_type: str) -> list[dict[str, Any]]:
    """Deterministic mapping table from retrieved provisions to HITL obligations
    (mandatory HITL conditions, override procedures, contact-risk assessment)."""
    requirements = []
    for p in provisions:
        section = p.get("section", "")
        requirements.append(
            {
                "condition": f"Mandatory HITL review applies per METI v1.2 {section}",
                "procedure": f"Override procedure and contact-risk assessment as specified in {section}",
            }
        )
    return requirements


def build_guidance_fallback(hitl_requirements: list[dict[str, Any]], physical_ai_type: str) -> tuple[str, float]:
    """Deterministic guidance + confidence score when no LLM is configured."""
    if not hitl_requirements:
        return "No matching METI v1.2 HITL guidance found in the knowledge base for this physical AI type.", 0.0
    lines = [f"- {r['condition']}: {r['procedure']}" for r in hitl_requirements]
    confidence = min(1.0, 0.5 + 0.1 * len(hitl_requirements))
    return f"HITL compliance guidance for {physical_ai_type}:\n" + "\n".join(lines), confidence


def build_citations(provisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mandatory citation attach: METI section per substantive answer."""
    return [{"section": p["section"]} for p in provisions if p.get("section")]


def assemble_final_answer(
    language: str, physical_ai_type: str, guidance_text: str, confidence: float, citations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Assemble the final answer + mandatory implementation disclaimer + citations."""
    return {
        "language": language,
        "physical_ai_type": physical_ai_type,
        "guidance": guidance_text,
        "confidence": confidence,
        "citations": citations,
        "disclaimer": IMPLEMENTATION_DISCLAIMER,
    }


def extract_audit_safe_topic(query: str, language: str, physical_ai_type: str) -> dict[str, Any]:
    """S-4: audit-safe metadata - topic/language/type ONLY, never the raw query text."""
    return {"language": language, "physical_ai_type": physical_ai_type, "query_length": len(query)}
