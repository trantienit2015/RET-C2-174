# RET-C2-174 — Retail Physical AI & Autonomous Store Operations METI v1.2 HITL Compliance Q&A Agent

> **Category**: Cat 2 (multi-step workflow for a specific job-to-be-done)
> **Industry**: RET

## Overview

This agent answers questions about the human-oversight requirements that apply to physical AI systems in a store — checkout robots, shelf scanners, delivery units, autonomous store formats. It retrieves from the operator-guideline knowledge base configured for the deployment and answers on override procedures, contact-risk assessment criteria, and the conditions under which human oversight is mandatory, citing the clauses it drew on.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Credentials — you supply them

This agent calls an Azure OpenAI deployment, so it needs that deployment's credentials.
They are **not** in this repository and are not shipped with it: they are yours and they
bill to your account.

`config/agent.yaml` declares what is needed:

| Name | Used for |
|---|---|
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` | Interpreting the question and drafting the guidance |

Set them as environment variables on the process that runs the agent. Never commit them,
and never put them in `config/config.yaml` — that file ships in the image.

**A model that cannot be reached ends the run as a failure.** The run ends with
`status=ERROR` and the cause recorded in `error_log`. It never presents an unanswered call
as an answer and never falls back to a guess.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
