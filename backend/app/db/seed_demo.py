"""Seed pre-populated demo data for the ``mock`` / ``mock`` user.

Called from bootstrap.py after seed users are created.
Idempotent: skips if demo ideas already exist.
"""
from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from app.core.time import utc_now_iso

# ---------------------------------------------------------------------------
# Stable IDs (deterministic for idempotency)
# ---------------------------------------------------------------------------
DEMO_IDEA_1 = "demo-idea-recipe"       # fully completed (PRD stage)
DEMO_IDEA_2 = "demo-idea-events"       # mid-workflow (scope_freeze stage)
DEMO_IDEA_3 = "demo-idea-devtools"     # early stage (idea_canvas)

_BASELINE_1 = "demo-baseline-recipe"
_BASELINE_2 = "demo-baseline-events"

_PATH_1 = "demo-path-recipe"
_PATH_2 = "demo-path-events"

# Stable node IDs
_N1_ROOT = "demo-n1-root"
_N1_A = "demo-n1-a"
_N1_B = "demo-n1-b"
_N1_C = "demo-n1-c"
_N1_A1 = "demo-n1-a1"
_N1_A2 = "demo-n1-a2"

_N2_ROOT = "demo-n2-root"
_N2_A = "demo-n2-a"
_N2_B = "demo-n2-b"
_N2_C = "demo-n2-c"
_N2_A1 = "demo-n2-a1"

_N3_ROOT = "demo-n3-root"
_N3_A = "demo-n3-a"
_N3_B = "demo-n3-b"
_N3_C = "demo-n3-c"


def seed_demo_data(conn: sqlite3.Connection) -> None:
    """Insert demo data if not already present. Must be called inside a transaction."""
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM idea WHERE id LIKE 'demo-idea-%'"
    ).fetchone()
    if row and int(row["cnt"]) > 0:
        return  # already seeded

    now = utc_now_iso()
    frozen_at = now  # reuse for simplicity

    # ------------------------------------------------------------------
    # 1. IDEAS
    # ------------------------------------------------------------------
    _insert_idea_1(conn, now)
    _insert_idea_2(conn, now)
    _insert_idea_3(conn, now)

    # ------------------------------------------------------------------
    # 2. DAG NODES
    # ------------------------------------------------------------------
    _insert_dag_nodes(conn, now)

    # ------------------------------------------------------------------
    # 3. DAG PATHS
    # ------------------------------------------------------------------
    _insert_dag_paths(conn, now)

    # ------------------------------------------------------------------
    # 4. SCOPE BASELINES + ITEMS
    # ------------------------------------------------------------------
    _insert_scope_baselines(conn, now, frozen_at)

    # ------------------------------------------------------------------
    # 5. NOTIFICATIONS (pre-populated for demo bell)
    # ------------------------------------------------------------------
    _insert_notifications(conn, now)

    # ------------------------------------------------------------------
    # 6. DECISION EVENTS (feed for pattern learner)
    # ------------------------------------------------------------------
    _insert_decision_events(conn, now)

    # ------------------------------------------------------------------
    # 7. USER PREFERENCES (learned patterns)
    # ------------------------------------------------------------------
    _insert_user_preferences(conn, now)


# ===================================================================
# IDEA 1: AI Recipe Recommender — fully completed (PRD stage)
# ===================================================================
def _insert_idea_1(conn: sqlite3.Connection, now: str) -> None:
    context = {
        "session_id": str(uuid4()),
        "created_at": now,
        "context_schema_version": 1,
        "idea_seed": "AI-powered recipe recommender that learns dietary preferences and suggests personalized meal plans",
        "opportunity": {
            "directions": [
                {"id": "A", "title": "Health-focused meal planner", "one_liner": "Personalized nutrition plans for health-conscious users", "pain_tags": ["diet tracking", "meal prep", "nutrition"]},
                {"id": "B", "title": "Budget-friendly recipe curator", "one_liner": "Smart recipes that minimize grocery spending", "pain_tags": ["budgeting", "grocery", "waste reduction"]},
                {"id": "C", "title": "Cultural cuisine explorer", "one_liner": "Discover recipes from global cuisines matched to local ingredients", "pain_tags": ["variety", "ingredients", "cultural"]},
            ]
        },
        "confirmed_dag_path_id": _PATH_1,
        "confirmed_dag_node_id": _N1_A1,
        "confirmed_dag_node_content": "AI nutritionist that creates weekly meal plans based on health goals, allergies, and taste preferences with automatic grocery list generation",
        "confirmed_dag_path_summary": "Starting from an AI recipe recommender, we narrowed to health-focused meal planning, then specialized into a personal AI nutritionist that generates weekly plans with grocery automation.",
        "feasibility": {
            "plans": [
                {
                    "id": "plan1", "name": "Bootstrapped MVP",
                    "summary": "Launch with a mobile-first web app, free tier with 3 meal plans/week, premium at $9.99/month for unlimited plans and grocery delivery integration.",
                    "score_overall": 8.2,
                    "scores": {"technical_feasibility": 8.5, "market_viability": 8.0, "execution_risk": 8.0},
                    "reasoning": {"technical_feasibility": "Standard web stack + OpenAI API for recipe generation. Grocery API integrations (Instacart, Kroger) are well-documented.", "market_viability": "Growing health-tech market. Competitors like Mealime validate demand but lack AI personalization.", "execution_risk": "Solo developer can ship MVP in 8 weeks. Recipe database seeding is the main risk."},
                    "recommended_positioning": "AI-first personal nutritionist for busy health-conscious professionals"
                },
                {
                    "id": "plan2", "name": "VC-Funded Growth",
                    "summary": "Raise seed round to build native iOS/Android apps with computer vision (scan fridge contents), partnerships with nutritionists, and B2B wellness programs.",
                    "score_overall": 7.0,
                    "scores": {"technical_feasibility": 6.5, "market_viability": 8.0, "execution_risk": 6.5},
                    "reasoning": {"technical_feasibility": "Computer vision for fridge scanning adds significant complexity. Native apps require larger team.", "market_viability": "B2B wellness is a validated market with enterprise budgets. High potential but longer sales cycles.", "execution_risk": "Requires 3-4 person team minimum. Fundraising takes 3-6 months before building."},
                    "recommended_positioning": "Enterprise wellness platform with AI-powered meal planning"
                },
                {
                    "id": "plan3", "name": "Platform / Ecosystem",
                    "summary": "Build an API-first recipe intelligence platform. License the recommendation engine to fitness apps, meal kit companies, and health insurance providers.",
                    "score_overall": 6.5,
                    "scores": {"technical_feasibility": 7.0, "market_viability": 6.5, "execution_risk": 6.0},
                    "reasoning": {"technical_feasibility": "API-first is architecturally clean but requires robust documentation and rate limiting from day one.", "market_viability": "B2B API market is smaller and requires enterprise sales capability.", "execution_risk": "Long sales cycles, heavy documentation burden, and chicken-and-egg problem for the marketplace."},
                    "recommended_positioning": "Recipe intelligence API for health & wellness platforms"
                }
            ]
        },
        "selected_plan_id": "plan1",
        "scope": {
            "in_scope": [
                {"id": "in-1", "title": "AI-powered weekly meal plan generation", "desc": "Generate personalized 7-day meal plans based on dietary preferences, allergies, and health goals", "priority": "P0"},
                {"id": "in-2", "title": "Smart grocery list", "desc": "Auto-generate consolidated grocery lists from meal plans with quantity optimization", "priority": "P0"},
                {"id": "in-3", "title": "Dietary preference profiles", "desc": "User profiles storing allergies, cuisine preferences, cooking skill level, and nutrition targets", "priority": "P0"},
                {"id": "in-4", "title": "Recipe detail view with nutrition info", "desc": "Step-by-step recipes with calorie counts, macros, and cooking time estimates", "priority": "P1"},
                {"id": "in-5", "title": "Meal plan history and favorites", "desc": "Save, rate, and revisit past meal plans and individual recipes", "priority": "P1"},
            ],
            "out_scope": [
                {"id": "out-1", "title": "Grocery delivery integration", "desc": "Direct ordering from Instacart/Kroger APIs", "reason": "Deferred to v2 after validating core meal planning value"},
                {"id": "out-2", "title": "Social features", "desc": "Sharing meal plans, community recipes, leaderboards", "reason": "Not aligned with MVP focus on personal health"},
                {"id": "out-3", "title": "Computer vision fridge scanning", "desc": "Camera-based ingredient detection", "reason": "High technical complexity, requires dedicated ML team"},
            ]
        },
        "scope_frozen": True,
        "current_scope_baseline_id": _BASELINE_1,
        "current_scope_baseline_version": 1,
        "prd": {
            "markdown": "# Product Requirements Document: AI Recipe Recommender\n\n## Executive Summary\n\nThe AI Recipe Recommender is a mobile-first web application that generates personalized weekly meal plans using AI. It targets health-conscious professionals who want to eat better but lack the time to plan meals manually. The MVP focuses on three core capabilities: AI-powered meal plan generation, smart grocery lists, and dietary preference profiles.\n\n## Problem Statement\n\nHealth-conscious individuals spend an average of 3-5 hours per week planning meals, searching recipes, and creating grocery lists. Existing solutions like Mealime offer static recipe databases without true AI personalization. Users need a tool that learns their preferences over time and adapts to changing health goals, seasonal ingredients, and budget constraints.\n\n## User Personas\n\n### Primary: Busy Health Professional\nAge 28-45, works full-time, exercises 3-4x/week, wants to maintain a healthy diet but has limited cooking time. Values convenience and nutrition accuracy over gourmet quality.\n\n### Secondary: Diet-Specific User\nHas specific dietary requirements (keto, vegan, gluten-free, etc.) and struggles to find varied recipes within their constraints. Frustrated by generic recipe apps that require extensive filtering.\n\n## Key Capabilities\n\nThe system generates personalized 7-day meal plans using a fine-tuned LLM that considers user dietary profiles, nutritional targets, and past preferences. Each plan includes breakfast, lunch, dinner, and snacks with automatic macro calculations.\n\nSmart grocery lists consolidate ingredients across all meals, optimize quantities to reduce waste, and group items by store section. Users can check off items as they shop.\n\n## Technical Approach\n\nBuilt with Next.js frontend and FastAPI backend. Recipe generation uses OpenAI GPT-4 with structured outputs. Nutritional data sourced from USDA FoodData Central API. User preferences stored in PostgreSQL with vector embeddings for taste similarity matching.\n\n## Success Metrics\n\n- 1,000 weekly active users within 3 months of launch\n- 60% of users generate at least 2 meal plans per week\n- Net Promoter Score > 40\n- Premium conversion rate > 5%\n\n## Out of Scope\n\nGrocery delivery integration, social features, and computer vision fridge scanning are explicitly deferred to future versions. The MVP validates core meal planning value before expanding to marketplace features.",
            "sections": [
                {"id": "sec-1", "title": "Executive Summary", "content": "The AI Recipe Recommender is a mobile-first web application that generates personalized weekly meal plans using AI. It targets health-conscious professionals who want to eat better but lack the time to plan meals. The MVP focuses on AI-powered meal plan generation, smart grocery lists, and dietary preference profiles."},
                {"id": "sec-2", "title": "Problem Statement", "content": "Health-conscious individuals spend 3-5 hours per week on meal planning. Existing solutions offer static databases without AI personalization. Users need a tool that learns preferences and adapts to health goals, seasonal ingredients, and budget constraints."},
                {"id": "sec-3", "title": "User Personas", "content": "Primary persona: Busy Health Professional (28-45, full-time, exercises regularly, values convenience). Secondary: Diet-Specific User (has dietary constraints like keto/vegan, needs variety within restrictions)."},
                {"id": "sec-4", "title": "Key Capabilities", "content": "AI-powered 7-day meal plan generation with macro calculations. Smart grocery lists with quantity optimization and store section grouping. Dietary preference profiles with allergy tracking and nutrition targets."},
                {"id": "sec-5", "title": "Technical Approach", "content": "Next.js frontend, FastAPI backend. GPT-4 for recipe generation with structured outputs. USDA FoodData Central for nutrition. PostgreSQL with vector embeddings for taste matching."},
                {"id": "sec-6", "title": "Success Metrics", "content": "1,000 WAU in 3 months. 60% generate 2+ plans/week. NPS > 40. Premium conversion > 5%. These metrics validate product-market fit before scaling."},
            ],
            "requirements": [
                {"id": "req-001", "title": "Weekly meal plan generation", "description": "The system generates a complete 7-day meal plan including breakfast, lunch, dinner, and snacks based on user dietary profile and health goals.", "rationale": "Core value proposition that differentiates from static recipe databases", "acceptance_criteria": ["User can generate a new meal plan with one click", "Plan respects all dietary restrictions and allergies", "Each meal includes estimated prep time and calorie count"], "source_refs": ["step2", "step3"]},
                {"id": "req-002", "title": "Dietary preference profile", "description": "Users create and maintain a profile specifying allergies, cuisine preferences, cooking skill level, calorie targets, and macro ratios.", "rationale": "Personalization requires structured preference data to drive AI recommendations", "acceptance_criteria": ["User can set allergies from a predefined list plus custom entries", "User can specify daily calorie and macro targets", "Profile changes immediately affect next meal plan generation"], "source_refs": ["step2", "step4"]},
                {"id": "req-003", "title": "Smart grocery list generation", "description": "The system auto-generates a consolidated grocery list from the active meal plan, combining duplicate ingredients and optimizing quantities.", "rationale": "Grocery list automation removes the biggest friction point after meal planning itself", "acceptance_criteria": ["Grocery list groups items by store section", "Duplicate ingredients across meals are consolidated", "User can check off items and the list persists across sessions"], "source_refs": ["step3", "step4"]},
                {"id": "req-004", "title": "Recipe detail view", "description": "Each recipe displays step-by-step instructions, ingredient list with quantities, nutrition breakdown, and estimated cooking time.", "rationale": "Users need actionable cooking guidance, not just meal names", "acceptance_criteria": ["Recipe shows macros (protein, carbs, fat) per serving", "Step-by-step instructions are numbered and clear", "Ingredient quantities adjust based on serving count"], "source_refs": ["step2"]},
                {"id": "req-005", "title": "Meal plan history", "description": "Users can view past meal plans, mark favorites, and regenerate variations of previously enjoyed plans.", "rationale": "Retention requires users to build a personal recipe library over time", "acceptance_criteria": ["User can view all past meal plans chronologically", "User can favorite individual recipes for quick access", "User can request a variation of a past plan"], "source_refs": ["step4"]},
                {"id": "req-006", "title": "User authentication and onboarding", "description": "Secure sign-up/login flow with a guided onboarding that collects dietary preferences before the first meal plan.", "rationale": "Personalization requires authenticated users with complete profiles from day one", "acceptance_criteria": ["New users complete dietary profile during onboarding", "Login supports email/password and Google OAuth", "Session persists across browser refreshes"], "source_refs": ["step3"]},
            ],
            "backlog": {
                "items": [
                    {"id": "bl-001", "title": "Implement meal plan generation API", "requirement_id": "req-001", "priority": "P0", "type": "epic", "summary": "Build the backend endpoint that calls GPT-4 to generate weekly meal plans from user profiles", "acceptance_criteria": ["API returns valid 7-day plan JSON", "Response time < 15 seconds"], "source_refs": ["step2", "step3"], "depends_on": []},
                    {"id": "bl-002", "title": "Build dietary profile CRUD", "requirement_id": "req-002", "priority": "P0", "type": "story", "summary": "Create frontend form and backend storage for user dietary preferences", "acceptance_criteria": ["Profile form validates all required fields", "Changes persist to database"], "source_refs": ["step2", "step4"], "depends_on": []},
                    {"id": "bl-003", "title": "Grocery list aggregation engine", "requirement_id": "req-003", "priority": "P0", "type": "story", "summary": "Consolidate ingredients across 21 meals into a deduplicated, section-grouped list", "acceptance_criteria": ["Quantities are correctly summed across meals", "Items grouped by store aisle"], "source_refs": ["step3", "step4"], "depends_on": ["bl-001"]},
                    {"id": "bl-004", "title": "Recipe detail page UI", "requirement_id": "req-004", "priority": "P1", "type": "story", "summary": "Frontend recipe view with step-by-step instructions and nutrition sidebar", "acceptance_criteria": ["Nutrition breakdown shows per-serving macros", "Serving size adjuster recalculates quantities"], "source_refs": ["step2"], "depends_on": ["bl-001"]},
                    {"id": "bl-005", "title": "Meal plan history timeline", "requirement_id": "req-005", "priority": "P1", "type": "story", "summary": "Chronological list of past meal plans with favorite marking", "acceptance_criteria": ["Plans show generation date and summary", "Favorite toggle persists immediately"], "source_refs": ["step4"], "depends_on": ["bl-001"]},
                    {"id": "bl-006", "title": "Auth flow with Google OAuth", "requirement_id": "req-006", "priority": "P0", "type": "story", "summary": "Sign-up/login with email+password and Google OAuth, including onboarding wizard", "acceptance_criteria": ["Google OAuth redirects correctly", "Onboarding collects dietary profile before first plan"], "source_refs": ["step3"], "depends_on": []},
                    {"id": "bl-007", "title": "Allergy and restriction tags", "requirement_id": "req-002", "priority": "P0", "type": "task", "summary": "Predefined allergy tag list (nuts, dairy, gluten, etc.) plus custom entry field", "acceptance_criteria": ["Tags are searchable and selectable", "Custom entries are saved to user profile"], "source_refs": ["step2", "step4"], "depends_on": ["bl-002"]},
                    {"id": "bl-008", "title": "Grocery list checkbox persistence", "requirement_id": "req-003", "priority": "P1", "type": "task", "summary": "Allow users to check off grocery items with state persisted across sessions", "acceptance_criteria": ["Checked state syncs to backend", "List resets when new plan is generated"], "source_refs": ["step3"], "depends_on": ["bl-003"]},
                ]
            },
            "generation_meta": {
                "provider_id": "demo",
                "model": "demo-model",
                "confirmed_path_id": _PATH_1,
                "selected_plan_id": "plan1",
                "baseline_id": _BASELINE_1,
            }
        },
    }

    conn.execute(
        """INSERT INTO idea (id, workspace_id, title, idea_seed, stage, status, context_json, version, created_at, updated_at, archived_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            DEMO_IDEA_1, "default",
            "AI Recipe Recommender",
            context["idea_seed"],
            "prd", "active",
            json.dumps(context, ensure_ascii=False),
            8,  # high version to look realistic
            now, now, None,
        ),
    )


# ===================================================================
# IDEA 2: Local Event Discovery — mid-workflow (scope_freeze stage)
# ===================================================================
def _insert_idea_2(conn: sqlite3.Connection, now: str) -> None:
    context = {
        "session_id": str(uuid4()),
        "created_at": now,
        "context_schema_version": 1,
        "idea_seed": "A local event discovery app that surfaces hidden community events using AI-curated recommendations",
        "opportunity": {
            "directions": [
                {"id": "A", "title": "Hyper-local event aggregator", "one_liner": "Aggregate events from scattered community boards into one feed", "pain_tags": ["fragmented sources", "local events", "community"]},
                {"id": "B", "title": "AI event matchmaker", "one_liner": "Match users to events based on interests and past attendance", "pain_tags": ["discovery", "personalization", "relevance"]},
                {"id": "C", "title": "Event organizer platform", "one_liner": "Tools for small organizers to promote and manage community events", "pain_tags": ["promotion", "ticketing", "small events"]},
            ]
        },
        "confirmed_dag_path_id": _PATH_2,
        "confirmed_dag_node_id": _N2_A1,
        "confirmed_dag_node_content": "AI-powered event discovery feed that learns user preferences from attendance history and social connections",
        "confirmed_dag_path_summary": "From a local event discovery app, narrowed to hyper-local aggregation, then specialized into an AI discovery feed that learns from attendance patterns.",
        "feasibility": {
            "plans": [
                {
                    "id": "plan1", "name": "Bootstrapped Community App",
                    "summary": "Web app scraping local event sources (Meetup, Eventbrite, Facebook Events) with AI ranking. Free for users, premium for organizers.",
                    "score_overall": 7.5,
                    "scores": {"technical_feasibility": 8.0, "market_viability": 7.0, "execution_risk": 7.5},
                    "reasoning": {"technical_feasibility": "Web scraping is straightforward but fragile. Event APIs exist for major platforms.", "market_viability": "Local event discovery is validated but highly competitive. Differentiation through AI ranking.", "execution_risk": "Data sourcing is the main challenge — scraping may break and API limits apply."},
                    "recommended_positioning": "AI-curated local event discovery for community enthusiasts"
                },
                {
                    "id": "plan2", "name": "VC-Funded Social Platform",
                    "summary": "Build a social-first event platform with friend activity feeds, group plans, and venue partnerships for monetization.",
                    "score_overall": 6.5,
                    "scores": {"technical_feasibility": 6.0, "market_viability": 7.5, "execution_risk": 6.0},
                    "reasoning": {"technical_feasibility": "Social features add complexity. Real-time feeds require infrastructure investment.", "market_viability": "Social events is a validated concept but requires network effects to work.", "execution_risk": "High burn rate, cold start problem, and competition from existing social platforms."},
                    "recommended_positioning": "Social event planning platform for friend groups"
                },
                {
                    "id": "plan3", "name": "B2B Event Analytics",
                    "summary": "Sell event trend analytics to venues, cities, and tourism boards. API-first with dashboard product.",
                    "score_overall": 6.0,
                    "scores": {"technical_feasibility": 7.0, "market_viability": 5.5, "execution_risk": 5.5},
                    "reasoning": {"technical_feasibility": "Analytics pipeline is well-understood. Dashboard building is standard.", "market_viability": "Niche B2B market with long sales cycles. Tourism boards have budget but slow procurement.", "execution_risk": "Enterprise sales cycle is 6-12 months. Requires sales team, not just product."},
                    "recommended_positioning": "Event intelligence platform for cities and venues"
                }
            ]
        },
        "selected_plan_id": "plan1",
        "scope": {
            "in_scope": [
                {"id": "in-1", "title": "Event aggregation from multiple sources", "desc": "Scrape and normalize events from Meetup, Eventbrite, and local calendar feeds", "priority": "P0"},
                {"id": "in-2", "title": "AI-ranked event feed", "desc": "Personalized event recommendations based on user interests and location", "priority": "P0"},
                {"id": "in-3", "title": "Event detail pages", "desc": "Rich event pages with map, time, description, and RSVP link", "priority": "P1"},
            ],
            "out_scope": [
                {"id": "out-1", "title": "In-app ticketing", "desc": "Native ticket purchase flow", "reason": "Redirect to source platform for MVP"},
                {"id": "out-2", "title": "Social features", "desc": "Friend activity, group planning", "reason": "Deferred to validate core discovery value first"},
            ]
        },
        "scope_frozen": False,
        "current_scope_baseline_id": _BASELINE_2,
        "current_scope_baseline_version": 1,
    }

    conn.execute(
        """INSERT INTO idea (id, workspace_id, title, idea_seed, stage, status, context_json, version, created_at, updated_at, archived_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            DEMO_IDEA_2, "default",
            "Local Event Discovery App",
            context["idea_seed"],
            "scope_freeze", "draft",
            json.dumps(context, ensure_ascii=False),
            5,
            now, now, None,
        ),
    )


# ===================================================================
# IDEA 3: Developer Productivity Tracker — early stage (idea_canvas)
# ===================================================================
def _insert_idea_3(conn: sqlite3.Connection, now: str) -> None:
    context = {
        "session_id": str(uuid4()),
        "created_at": now,
        "context_schema_version": 1,
        "idea_seed": "A developer productivity tracker that integrates with GitHub, Jira, and CI/CD to surface actionable insights",
        "opportunity": {
            "directions": [
                {"id": "A", "title": "Individual dev dashboard", "one_liner": "Personal productivity insights from commit patterns and PR reviews", "pain_tags": ["self-improvement", "metrics", "focus time"]},
                {"id": "B", "title": "Team velocity analyzer", "one_liner": "Engineering manager tool for sprint health and bottleneck detection", "pain_tags": ["team management", "sprint planning", "velocity"]},
                {"id": "C", "title": "CI/CD cost optimizer", "one_liner": "Analyze build pipelines to reduce CI costs and wait times", "pain_tags": ["CI costs", "build time", "DevOps"]},
            ]
        },
    }

    conn.execute(
        """INSERT INTO idea (id, workspace_id, title, idea_seed, stage, status, context_json, version, created_at, updated_at, archived_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            DEMO_IDEA_3, "default",
            "Developer Productivity Tracker",
            context["idea_seed"],
            "idea_canvas", "draft",
            json.dumps(context, ensure_ascii=False),
            2,
            now, now, None,
        ),
    )


# ===================================================================
# DAG NODES
# ===================================================================
def _insert_dag_nodes(conn: sqlite3.Connection, now: str) -> None:
    nodes = [
        # Idea 1: Recipe Recommender (full tree)
        (_N1_ROOT, DEMO_IDEA_1, None, "AI-powered recipe recommender that learns dietary preferences", None, None, 0),
        (_N1_A, DEMO_IDEA_1, _N1_ROOT, "Health-focused meal planner for nutrition-conscious users", "narrow_audience", "Narrow audience", 1),
        (_N1_B, DEMO_IDEA_1, _N1_ROOT, "Budget-friendly recipe curator that minimizes grocery costs", "expand_feature", "Expand feature", 1),
        (_N1_C, DEMO_IDEA_1, _N1_ROOT, "Cultural cuisine explorer matched to local ingredient availability", "scenario_shift", "Scenario shift", 1),
        (_N1_A1, DEMO_IDEA_1, _N1_A, "AI nutritionist that creates weekly meal plans based on health goals, allergies, and taste preferences with automatic grocery list generation", "narrow_audience", "Specialize further", 2),
        (_N1_A2, DEMO_IDEA_1, _N1_A, "Fitness meal prep assistant for athletes with macro tracking and post-workout nutrition", "expand_feature", "Add capability", 2),

        # Idea 2: Event Discovery (partial tree)
        (_N2_ROOT, DEMO_IDEA_2, None, "Local event discovery app using AI-curated recommendations", None, None, 0),
        (_N2_A, DEMO_IDEA_2, _N2_ROOT, "Hyper-local event aggregator pulling from community boards", "narrow_audience", "Narrow audience", 1),
        (_N2_B, DEMO_IDEA_2, _N2_ROOT, "AI event matchmaker based on interests and attendance history", "expand_feature", "Expand feature", 1),
        (_N2_C, DEMO_IDEA_2, _N2_ROOT, "Event organizer tools for small community event promotion", "scenario_shift", "Scenario shift", 1),
        (_N2_A1, DEMO_IDEA_2, _N2_A, "AI-powered event discovery feed that learns user preferences from attendance history and social connections", "narrow_audience", "Specialize further", 2),

        # Idea 3: Dev Productivity (root only + 3 children)
        (_N3_ROOT, DEMO_IDEA_3, None, "Developer productivity tracker integrating GitHub, Jira, and CI/CD", None, None, 0),
        (_N3_A, DEMO_IDEA_3, _N3_ROOT, "Personal dev dashboard with commit patterns and PR review insights", "narrow_audience", "Narrow audience", 1),
        (_N3_B, DEMO_IDEA_3, _N3_ROOT, "Team velocity analyzer for engineering managers", "expand_feature", "Expand feature", 1),
        (_N3_C, DEMO_IDEA_3, _N3_ROOT, "CI/CD pipeline cost optimizer reducing build times and cloud spend", "scenario_shift", "Scenario shift", 1),
    ]

    for node_id, idea_id, parent_id, content, pattern, edge_label, depth in nodes:
        conn.execute(
            """INSERT INTO idea_nodes (id, idea_id, parent_id, content, expansion_pattern, edge_label, depth, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_id, idea_id, parent_id, content, pattern, edge_label, depth, "active", now),
        )


# ===================================================================
# DAG PATHS
# ===================================================================
def _insert_dag_paths(conn: sqlite3.Connection, now: str) -> None:
    # Path 1: Recipe Recommender confirmed path
    chain_1 = [_N1_ROOT, _N1_A, _N1_A1]
    path_json_1 = json.dumps({
        "nodes": [
            {"id": _N1_ROOT, "content": "AI-powered recipe recommender", "depth": 0},
            {"id": _N1_A, "content": "Health-focused meal planner", "depth": 1},
            {"id": _N1_A1, "content": "AI nutritionist with weekly plans and grocery automation", "depth": 2},
        ]
    })
    conn.execute(
        "INSERT INTO idea_paths (id, idea_id, node_chain, path_md, path_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (_PATH_1, DEMO_IDEA_1, json.dumps(chain_1),
         "AI recipe recommender > Health-focused meal planner > AI nutritionist with weekly plans and grocery automation",
         path_json_1, now),
    )

    # Path 2: Event Discovery confirmed path
    chain_2 = [_N2_ROOT, _N2_A, _N2_A1]
    path_json_2 = json.dumps({
        "nodes": [
            {"id": _N2_ROOT, "content": "Local event discovery app", "depth": 0},
            {"id": _N2_A, "content": "Hyper-local event aggregator", "depth": 1},
            {"id": _N2_A1, "content": "AI discovery feed learning from attendance", "depth": 2},
        ]
    })
    conn.execute(
        "INSERT INTO idea_paths (id, idea_id, node_chain, path_md, path_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (_PATH_2, DEMO_IDEA_2, json.dumps(chain_2),
         "Local event discovery > Hyper-local aggregator > AI discovery feed learning from attendance",
         path_json_2, now),
    )


# ===================================================================
# SCOPE BASELINES + ITEMS
# ===================================================================
def _insert_scope_baselines(conn: sqlite3.Connection, now: str, frozen_at: str) -> None:
    # Baseline 1: Recipe Recommender — frozen
    conn.execute(
        "INSERT INTO scope_baselines (id, idea_id, version, status, source_baseline_id, created_at, frozen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_BASELINE_1, DEMO_IDEA_1, 1, "frozen", None, now, frozen_at),
    )
    scope_items_1 = [
        ("in", "AI-powered weekly meal plan generation", 0),
        ("in", "Smart grocery list with quantity optimization", 1),
        ("in", "Dietary preference profiles (allergies, macros, cuisine)", 2),
        ("in", "Recipe detail view with nutrition breakdown", 3),
        ("in", "Meal plan history and favorites", 4),
        ("out", "Grocery delivery integration (Instacart/Kroger)", 0),
        ("out", "Social features (sharing, community recipes)", 1),
        ("out", "Computer vision fridge scanning", 2),
    ]
    for lane, content, order in scope_items_1:
        conn.execute(
            "INSERT INTO scope_baseline_items (id, baseline_id, lane, content, display_order, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), _BASELINE_1, lane, content, order, now),
        )

    # Baseline 2: Event Discovery — draft (not frozen)
    conn.execute(
        "INSERT INTO scope_baselines (id, idea_id, version, status, source_baseline_id, created_at, frozen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_BASELINE_2, DEMO_IDEA_2, 1, "draft", None, now, None),
    )
    scope_items_2 = [
        ("in", "Event aggregation from multiple sources", 0),
        ("in", "AI-ranked personalized event feed", 1),
        ("in", "Event detail pages with map and RSVP", 2),
        ("out", "In-app ticketing", 0),
        ("out", "Social features (friend activity, group planning)", 1),
    ]
    for lane, content, order in scope_items_2:
        conn.execute(
            "INSERT INTO scope_baseline_items (id, baseline_id, lane, content, display_order, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), _BASELINE_2, lane, content, order, now),
        )


# ===================================================================
# NOTIFICATIONS
# ===================================================================
def _insert_notifications(conn: sqlite3.Connection, now: str) -> None:
    notifications = [
        (
            "demo-notif-1", "default", "news_match",
            "News: FDA guidance opens door for AI nutrition apps",
            "Recent FDA regulatory changes may create opportunities for your AI Recipe Recommender — new guidance specifically addresses AI-generated dietary recommendations, potentially reducing compliance barriers. Similarity score: 0.28",
            {"news_id": "demo-news-fda", "idea_id": DEMO_IDEA_1, "news_title": "FDA guidance opens door for AI nutrition apps", "distance": 0.28},
        ),
        (
            "demo-notif-2", "default", "news_match",
            "News: AI personalization drives 40% higher engagement in food-tech",
            "A new industry report shows AI-personalized meal recommendations increase user engagement by 40% compared to static recipe databases — directly relevant to your Recipe Recommender's core value proposition. Similarity score: 0.22",
            {"news_id": "demo-news-foodtech", "idea_id": DEMO_IDEA_1, "news_title": "AI personalization drives 40% higher engagement in food-tech", "distance": 0.22},
        ),
        (
            "demo-notif-3", "default", "cross_idea_insight",
            "Related ideas detected",
            "Your AI Recipe Recommender and Local Event Discovery App both leverage location-based personalization and user preference learning. Consider shared infrastructure for recommendation engines and preference profiles.",
            {"idea_a_id": DEMO_IDEA_1, "idea_b_id": DEMO_IDEA_2, "analysis": "Both ideas leverage location-based personalization and user preference learning. Shared recommendation engine infrastructure could accelerate both products."},
        ),
        (
            "demo-notif-4", "default", "pattern_learned",
            "Updated your preference profile",
            "Based on your recent decisions: business_model_preference: Freemium with premium AI features, risk_tolerance: Moderate, focus_area: Consumer AI applications",
            {"preferences": {"business_model_preference": "Freemium with premium AI features", "risk_tolerance": "Moderate — prefers validated markets", "focus_area": "Consumer AI applications", "decision_style": "Data-driven, favors scored comparisons"}},
        ),
    ]
    for nid, user_id, ntype, title, body, metadata in notifications:
        conn.execute(
            "INSERT INTO notification (id, user_id, type, title, body, metadata_json, read_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nid, user_id, ntype, title, body, json.dumps(metadata, ensure_ascii=False), None, now),
        )


# ===================================================================
# DECISION EVENTS
# ===================================================================
def _insert_decision_events(conn: sqlite3.Connection, now: str) -> None:
    events = [
        ("demo-evt-1", "default", DEMO_IDEA_1, "dag_path_confirmed", {"path_id": _PATH_1, "leaf_node_id": _N1_A1}),
        ("demo-evt-2", "default", DEMO_IDEA_1, "feasibility_plan_selected", {"selected_plan_id": "plan1", "plan_name": "Bootstrapped MVP", "score_overall": 8.2}),
        ("demo-evt-3", "default", DEMO_IDEA_1, "scope_frozen", {"baseline_id": _BASELINE_1, "version": 1}),
        ("demo-evt-4", "default", DEMO_IDEA_1, "prd_generated", {"baseline_id": _BASELINE_1, "fingerprint": "demo-fingerprint-001"}),
        ("demo-evt-5", "default", DEMO_IDEA_2, "dag_path_confirmed", {"path_id": _PATH_2, "leaf_node_id": _N2_A1}),
        ("demo-evt-6", "default", DEMO_IDEA_2, "feasibility_plan_selected", {"selected_plan_id": "plan1", "plan_name": "Bootstrapped Community App", "score_overall": 7.5}),
    ]
    for eid, user_id, idea_id, event_type, payload in events:
        conn.execute(
            "INSERT INTO decision_events (id, user_id, idea_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (eid, user_id, idea_id, event_type, json.dumps(payload, ensure_ascii=False), now),
        )


# ===================================================================
# USER PREFERENCES (learned patterns for profile page)
# ===================================================================
def _insert_user_preferences(conn: sqlite3.Connection, now: str) -> None:
    patterns = {
        "business_model_preference": "Freemium with premium AI features",
        "risk_tolerance": "Moderate — prefers validated markets",
        "focus_area": "Consumer AI applications",
        "decision_style": "Data-driven, favors scored comparisons",
    }
    conn.execute(
        """INSERT INTO user_preferences (user_id, learned_patterns_json, last_learned_event_count, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             learned_patterns_json = excluded.learned_patterns_json,
             last_learned_event_count = excluded.last_learned_event_count,
             updated_at = excluded.updated_at""",
        ("default", json.dumps(patterns, ensure_ascii=False), 6, now),
    )
