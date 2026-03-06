from __future__ import annotations

from app.agents.memory.vector_store import VectorStore

DEMO_IDEAS: list[dict] = [
    {
        "id": "demo-idea-1",
        "summary": (
            "AI-powered code review assistant that integrates with GitHub PRs "
            "to provide real-time feedback on code quality, security vulnerabilities, "
            "and performance bottlenecks for engineering teams."
        ),
    },
    {
        "id": "demo-idea-2",
        "summary": (
            "SaaS platform for freelance designers to manage client projects, "
            "contracts, invoicing, and portfolio showcase in one unified workspace "
            "with built-in collaboration tools."
        ),
    },
    {
        "id": "demo-idea-3",
        "summary": (
            "Developer productivity dashboard that aggregates metrics from Jira, "
            "GitHub, and CI/CD pipelines to give engineering managers real-time "
            "visibility into team velocity and bottlenecks."
        ),
    },
    {
        "id": "demo-idea-4",
        "summary": (
            "Personalized meal-planning app using AI to generate weekly menus "
            "based on dietary preferences, grocery budgets, and local store "
            "inventory with one-tap ingredient ordering."
        ),
    },
    {
        "id": "demo-idea-5",
        "summary": (
            "No-code internal tools builder for operations teams that connects "
            "to existing databases and APIs, letting non-technical staff create "
            "CRUD apps, dashboards, and approval workflows in minutes."
        ),
    },
]

DEMO_NEWS: list[dict] = [
    {
        "id": "demo-news-1",
        "title": "GitHub Copilot expands AI code review to all Enterprise users",
        "content": (
            "GitHub announced that its AI-powered code review feature is now "
            "generally available for all Enterprise plan customers. The tool "
            "automatically reviews pull requests for bugs, security issues, "
            "and style inconsistencies, reducing review cycle times by 40%."
        ),
    },
    {
        "id": "demo-news-2",
        "title": "Figma acquires AI design startup for $500M",
        "content": (
            "Figma has acquired an AI design assistant startup, signaling "
            "increased consolidation in the design tools market. The acquisition "
            "will integrate generative UI capabilities directly into Figma's "
            "collaborative platform for design teams."
        ),
    },
    {
        "id": "demo-news-3",
        "title": "Developer productivity tools market projected to reach $45B by 2028",
        "content": (
            "A new Gartner report forecasts the developer productivity and DevOps "
            "tools market will grow to $45 billion by 2028, driven by AI-assisted "
            "coding, automated testing, and platform engineering investments "
            "across enterprises of all sizes."
        ),
    },
    {
        "id": "demo-news-4",
        "title": "New FDA guidance opens door for AI-driven nutrition apps",
        "content": (
            "The FDA released updated guidance allowing AI-powered nutrition "
            "and meal-planning applications to provide personalized dietary "
            "recommendations without requiring medical device classification, "
            "unlocking a new wave of consumer health tech startups."
        ),
    },
    {
        "id": "demo-news-5",
        "title": "Low-code / no-code platforms see 35% YoY enterprise adoption growth",
        "content": (
            "Forrester research shows enterprise adoption of low-code and "
            "no-code platforms grew 35% year-over-year. Operations and IT "
            "teams are the primary buyers, using these tools to build internal "
            "apps and automate workflows without dedicated engineering resources."
        ),
    },
]

DEMO_PATTERNS: list[dict] = [
    {
        "id": "pattern-land-and-expand",
        "description": (
            "Land-and-expand SaaS go-to-market pattern: offer a free or low-cost "
            "entry tier targeting individual users or small teams, then expand into "
            "paid team and enterprise plans through viral adoption, usage-based "
            "pricing triggers, and admin/governance features that compel upgrades."
        ),
    },
    {
        "id": "pattern-api-first-platform",
        "description": (
            "API-first platform pattern: build the core product as a headless API "
            "with comprehensive documentation and SDKs, then layer a first-party "
            "UI on top. This enables a developer ecosystem, marketplace integrations, "
            "and white-label partnerships while keeping the core lean and extensible."
        ),
    },
    {
        "id": "pattern-community-led-growth",
        "description": (
            "Community-led growth pattern: invest in open-source tooling, educational "
            "content, and a developer community (Discord, forums, meetups) to build "
            "brand trust and organic inbound demand before layering on a paid "
            "managed service or premium features for enterprise customers."
        ),
    },
]


def seed_vector_store(vs: VectorStore | None = None) -> VectorStore:
    """Populate a VectorStore with demo data. Returns the seeded store."""
    if vs is None:
        vs = VectorStore(persist_directory=None)

    for idea in DEMO_IDEAS:
        vs.add_idea_summary(idea_id=idea["id"], summary=idea["summary"])

    for news in DEMO_NEWS:
        vs.add_news_item(
            news_id=news["id"],
            title=news["title"],
            content=news["content"],
        )

    for pattern in DEMO_PATTERNS:
        vs.add_decision_pattern(
            pattern_id=pattern["id"],
            description=pattern["description"],
        )

    return vs
