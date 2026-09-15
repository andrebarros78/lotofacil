# SARE Lotofácil — Agent Authority

## Purpose

This repository may use specialized AI agents to assist engineering, research, audit, security, release work and operational verification. Agents are an **engineering/orchestration layer**. They are not a predictive ensemble and they do not acquire authority over the scientific or operational state of the SARE Lotofácil.

## Canonical authority

The authority order is immutable unless changed by an approved pull request:

1. `main` — approved code, protocols, tests and workflows.
2. `operations/state` — canonical operational state produced only by approved GitHub Actions.
3. GitHub Actions — canonical executor for operational evidence and state transitions.
4. GitHub Artifacts and Git history — evidence and provenance.
5. Agent outputs — proposals, findings and structured handoffs only.

No agent output can override a failing test, a scientific guardrail, a ruleset, a workflow gate or a persisted canonical state.

## Non-negotiable restrictions

- No agent writes directly to `main`.
- No agent writes directly to `operations/state`.
- No agent bypasses GitHub rulesets or required checks.
- No agent may tune a model or parameter using the frozen lockbox after that lockbox is opened.
- No agent may promote predictive evidence while the canonical conclusion is `NOT_ESTABLISHED`.
- No agent may convert retrospective signal into a claim of future advantage without the predeclared scientific promotion gate.
- No agent may suppress failed windows, failed checks, negative results or contradictory evidence.
- No agent may import an external framework, model, dataset, prompt pack, skill or tool into the runtime without dependency, license, security and scientific-impact review.
- Community repositories are untrusted inputs until reviewed and pinned.

## Required handoff contract

Every agent handoff must be representable as structured data with at least:

- `agent_id`
- `task_id`
- `evidence_refs`
- `findings`
- `proposed_actions`
- `risk_level`
- `requires_approval`
- `scientific_claim_level`

A handoff is evidence about work performed; it is never authority to mutate canonical state.

## Agent ecosystem

The canonical registries are:

- `governance/agents/agents.json`
- `governance/agents/skills.json`
- `governance/agents/acquisitions.json`

The governance validator is:

- `scripts/validate_agent_ecosystem.py`

CI must fail if agent identities, skills, boundaries or acquisition records are inconsistent.

## Runtime policy

The 1.x production runtime remains free of agent-framework dependencies unless a separate, measured experiment demonstrates a concrete need and passes the normal pull-request, CI, release and scientific-governance process.

Approved external ecosystems can be used as **reference sources** before becoming dependencies. Reference acquisition does not authorize vendoring arbitrary third-party code.
