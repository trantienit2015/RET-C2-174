"""Caller-facing wording for runs that end without guidance.

Each outcome here is reported by completing the run with an allow-listed ``error_code``
and a fixed sentence derived from that code alone. No request value is ever
interpolated, so a notice can never echo caller content back. On such a run
``status=SUCCESS`` means the agent finished handling the request safely; it does not
mean guidance was returned.

Caller-correctable: EMPTY_INPUT, a request with no question in it. The sentence names
what to send instead.

Policy withholding: CITATION_WITHHELD and DISCLAIMER_WITHHELD. Guidance that cites
material outside the knowledge base, or that lacks its mandatory implementation
disclaimer, is withheld under this agent's answer-quality contract; nothing assembled
for it is returned.

Not reported here, and ending as ``status=ERROR`` instead: credential-shaped content,
which fails closed with no output and no status conversion; an internally inconsistent
run (state a preceding step guarantees is absent), which is a defect; and a failed call
to a required external dependency. None of these is ever represented as a successful
completion.
"""

from __future__ import annotations

EMPTY_INPUT = "EMPTY_INPUT"
# Diagnostic code for a run that ends as status=ERROR because the language model failed or
# returned nothing. Recorded in error_log and the audit event only.
GUIDANCE_MODEL_UNAVAILABLE = "GUIDANCE_MODEL_UNAVAILABLE"
CITATION_WITHHELD = "CITATION_WITHHELD"
DISCLAIMER_WITHHELD = "DISCLAIMER_WITHHELD"

_MESSAGES: dict[str, str] = {
    EMPTY_INPUT: (
        "No question was received. Describe the physical-AI compliance question to "
        "answer — the checkout robot, shelf scanner, delivery bot or autonomous store "
        "operation you need the human-oversight requirements for."
    ),
}

_MESSAGES[CITATION_WITHHELD] = (
    "Guidance was assembled but not returned, because it cited material outside the "
    "guideline sections this agent answers from. Ask about one kind of physical-AI "
    "operation at a time and send it again."
)

_MESSAGES[DISCLAIMER_WITHHELD] = (
    "Guidance was assembled but not returned, because it lacked the implementation "
    "disclaimer this agent attaches to every answer. Send the question again."
)

_FALLBACK = "The request could not be accepted and no guidance was produced."


def explain_degradation(code: str) -> str:
    """Return one caller-facing sentence for a degradation code."""
    return _MESSAGES.get(code, f"{_FALLBACK} [{code}]" if code else _FALLBACK)
