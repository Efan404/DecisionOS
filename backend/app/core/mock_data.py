from __future__ import annotations

import hashlib

from app.schemas.common import (
    Direction,
    DirectionId,
    PriorityLevel,
    ReasoningBreakdown,
    ScoreBreakdown,
)
from app.schemas.feasibility import FeasibilityInput, FeasibilityOutput, Plan
from app.schemas.idea import OPPORTUNITY_MAX_COUNT, OPPORTUNITY_MIN_COUNT, OpportunityOutput
from app.schemas.prd import PRDInput, PRDOutput, PRDSections
from app.schemas.scope import InScopeItem, OutScopeItem, ScopeInput, ScopeOutput

_DIRECTION_TEMPLATES: list[tuple[str, str, list[str]]] = [
    (
        "Rapid Validation Assistant",
        "Help solo founders validate a product idea in 48 hours.",
        ["unclear demand", "time pressure", "scope drift"],
    ),
    (
        "Decision Compression Workspace",
        "Turn noisy product discussions into one-page decisions.",
        ["too many options", "meeting fatigue", "slow alignment"],
    ),
    (
        "MVP Launch Copilot",
        "Sequence tasks from concept to first public launch.",
        ["execution chaos", "hidden dependencies", "missed deadlines"],
    ),
    (
        "Feature Prioritization Radar",
        "Rank potential features by impact and build effort.",
        ["backlog overload", "low signal", "resource mismatch"],
    ),
    (
        "Experiment Tracker for Teams",
        "Track hypotheses, tests, and outcomes in one flow.",
        ["weak learning loops", "result ambiguity", "context loss"],
    ),
    (
        "Niche Market Discovery Lens",
        "Map underserved user segments and actionable wedges.",
        ["crowded market", "weak positioning", "uncertain niche"],
    ),
]

_PLAN_TEMPLATES: list[tuple[str, str, str]] = [
    (
        "Single-Flow MVP",
        "Build one polished core workflow and defer advanced automation.",
        "Position as the fastest path from idea to first user signal.",
    ),
    (
        "Template-Driven Toolkit",
        "Ship reusable templates first to reduce onboarding friction.",
        "Position as a plug-and-play decision kit for hackathon teams.",
    ),
    (
        "Analytics-First Rollout",
        "Instrument every action early and optimize with usage data.",
        "Position as a measurable decision engine for iterative builders.",
    ),
    (
        "Service + Product Hybrid",
        "Pair lightweight tooling with guided strategy recommendations.",
        "Position as a hands-on copilot for solo founders.",
    ),
    (
        "Integration-Lite Strategy",
        "Export outcomes to existing tools before deep native integrations.",
        "Position as the missing strategic layer above existing stacks.",
    ),
    (
        "Community-Led Launch",
        "Use public build logs and feedback loops to shape priorities.",
        "Position as a transparent builder OS refined with real users.",
    ),
]

_IN_SCOPE_BANK: list[tuple[str, str]] = [
    ("Idea intake with deterministic mock generation", "Capture idea seed and generate repeatable outputs."),
    ("Configurable opportunity canvas", "Generate between one and six direction options on demand."),
    ("Feasibility plan cards with score breakdown", "Compare top plans with clear dimension scores."),
    ("Scope freeze IN/OUT board", "Lock MVP boundaries after plan confirmation."),
    ("POST-based SSE streaming", "Incrementally render partial outputs with progress events."),
    ("Guard rails for missing context", "Prevent jumping to downstream steps without prerequisites."),
]

_OUT_SCOPE_BANK: list[tuple[str, str]] = [
    ("Team workspace and RBAC", "MVP focuses on single-session solo usage."),
    ("Persistent server-side history", "Hackathon demo can rely on client persistence only."),
    ("Third-party integrations", "Avoid Notion/Jira complexity in first release."),
    ("Automated billing and plans", "No monetization workflow required for MVP."),
    ("Multi-language localization", "Initial demo targets one language market."),
    ("Native mobile clients", "Web-first experience is sufficient for demo stage."),
]

_REASONS_TECH = [
    "Architecture remains simple with low operational complexity.",
    "Main risk is integration churn, but fallback mocks reduce exposure.",
    "Implementation is straightforward with existing FastAPI primitives.",
]

_REASONS_MARKET = [
    "Pain point is visible for indie builders under delivery pressure.",
    "Comparable products exist, but speed-to-decision is still under-served.",
    "Positioning is differentiated by deterministic demo reliability.",
]

_REASONS_RISK = [
    "Execution risk is contained by narrow MVP scope and fixed outputs.",
    "Risk remains moderate because frontend streaming logic is concurrency-sensitive.",
    "Most unknowns are UX polish, not core technical feasibility.",
]

_DIRECTION_IDS: tuple[DirectionId, ...] = ("A", "B", "C", "D", "E", "F")
_PRIORITIES: tuple[PriorityLevel, ...] = ("P0", "P1", "P2")


def generate_opportunity_output(idea_seed: str, *, count: int) -> OpportunityOutput:
    if count < OPPORTUNITY_MIN_COUNT or count > OPPORTUNITY_MAX_COUNT:
        raise ValueError(f"count must be between {OPPORTUNITY_MIN_COUNT} and {OPPORTUNITY_MAX_COUNT}")

    base = _seed_int(f"opportunity:{idea_seed}")
    directions: list[Direction] = []

    for index, direction_id in enumerate(_DIRECTION_IDS[:count]):
        template = _DIRECTION_TEMPLATES[(base + index) % len(_DIRECTION_TEMPLATES)]
        title, one_liner, pain_tags = template
        directions.append(
            Direction(
                id=direction_id,
                title=title,
                one_liner=one_liner,
                pain_tags=pain_tags,
            )
        )

    return OpportunityOutput(directions=directions)


def generate_feasibility_output(payload: FeasibilityInput) -> FeasibilityOutput:
    seed = f"feasibility:{payload.idea_seed}:{payload.direction_id}:{payload.path_id}:{payload.direction_text}"
    base = _seed_int(seed)

    plans: list[Plan] = []
    for index in range(3):
        template = _PLAN_TEMPLATES[(base + index) % len(_PLAN_TEMPLATES)]
        name, summary, positioning = template

        technical = _score(seed, index * 3)
        market = _score(seed, index * 3 + 1)
        execution = _score(seed, index * 3 + 2)

        plans.append(
            Plan(
                id=f"plan{index + 1}",
                name=name,
                summary=summary,
                score_overall=round((technical + market + execution) / 3, 1),
                scores=ScoreBreakdown(
                    technical_feasibility=technical,
                    market_viability=market,
                    execution_risk=execution,
                ),
                reasoning=ReasoningBreakdown(
                    technical_feasibility=_REASONS_TECH[(base + index) % len(_REASONS_TECH)],
                    market_viability=_REASONS_MARKET[(base + index) % len(_REASONS_MARKET)],
                    execution_risk=_REASONS_RISK[(base + index) % len(_REASONS_RISK)],
                ),
                recommended_positioning=f"{positioning} (Path: {payload.path_id}).",
            )
        )

    return FeasibilityOutput(plans=plans)


def generate_scope_output(payload: ScopeInput) -> ScopeOutput:
    seed = f"scope:{payload.idea_seed}:{payload.selected_plan_id}:{payload.path_id}"
    base = _seed_int(seed)

    in_scope: list[InScopeItem] = []
    out_scope: list[OutScopeItem] = []

    for index in range(3):
        title, desc = _IN_SCOPE_BANK[(base + index) % len(_IN_SCOPE_BANK)]
        priority = _PRIORITIES[index]
        in_scope.append(
            InScopeItem(
                id=f"f{index + 1}",
                title=title,
                desc=desc,
                priority=priority,
            )
        )

    for index in range(3):
        title, reason = _OUT_SCOPE_BANK[(base + index) % len(_OUT_SCOPE_BANK)]
        out_scope.append(
            OutScopeItem(
                id=f"f{index + 9}",
                title=title,
                desc="Deferred after MVP validation milestone.",
                reason=reason,
            )
        )

    return ScopeOutput(in_scope=in_scope, out_scope=out_scope)


def generate_prd_output(payload: PRDInput) -> PRDOutput:
    sections = PRDSections(
        problem_statement=f"Builders need a reliable flow to evaluate '{payload.idea_seed}' quickly.",
        target_user="Independent developers and small hackathon teams.",
        core_workflow="Idea input -> opportunity selection -> feasibility confirmation -> scope freeze.",
        mvp_scope="\n".join(f"- {item.title}" for item in payload.scope.in_scope),
        success_metrics="First completed decision workflow in < 15 minutes; clear IN/OUT scope lock.",
        risk_analysis="Biggest risks are stream UX edge cases and weak positioning clarity.",
    )

    markdown = "\n".join(
        [
            "# DecisionOS MVP PRD",
            "",
            f"## Problem Statement\n{sections.problem_statement}",
            f"## Target User\n{sections.target_user}",
            f"## Core Workflow\n{sections.core_workflow}",
            f"## MVP Scope\n{sections.mvp_scope}",
            f"## Success Metrics\n{sections.success_metrics}",
            f"## Risk Analysis\n{sections.risk_analysis}",
        ]
    )

    return PRDOutput(markdown=markdown, sections=sections)


MOCK_EXPAND_NODES: list[dict[str, str]] = [
    {"content": "Mock child idea A — narrow focus on power users", "edge_label": "缩小用户群体"},
    {"content": "Mock child idea B — extend to enterprise workflow", "edge_label": "缩小用户群体"},
]

MOCK_PATH_SUMMARY = (
    "This idea evolved from a broad concept to a focused solution "
    "for a specific user segment, validating core assumptions along the way."
)


def _seed_int(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _score(seed: str, offset: int) -> float:
    raw = _seed_int(f"{seed}:{offset}") % 331
    return round(6.7 + raw / 100, 1)
