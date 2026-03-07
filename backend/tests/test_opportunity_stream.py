from __future__ import annotations

import asyncio
import json
import os


from unittest.mock import patch

from app.agents.stream import run_opportunity_graph_sse


def _mock_generate_structured(**kwargs):
    from app.schemas.common import Direction
    from app.schemas.idea import OpportunityOutput
    return OpportunityOutput(
        directions=[
            Direction(id="A", title="Dir A", one_liner="One-liner A", pain_tags=["t1"]),
            Direction(id="B", title="Dir B", one_liner="One-liner B", pain_tags=["t2"]),
        ]
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_stream_emits_agent_thoughts_and_done(mock_gen):
    """SSE stream from opportunity graph emits agent_thought and done events."""
    events: list[dict] = []

    async def collect():
        async for event in run_opportunity_graph_sse(
            idea_id="test-id",
            idea_seed="AI tool",
        ):
            events.append(event)

    asyncio.run(collect())

    event_types = [e["event"] for e in events]
    assert "agent_thought" in event_types, f"Expected agent_thought, got {event_types}"
    assert "done" in event_types, f"Expected done event, got {event_types}"

    # done event should have opportunity_output
    done_event = next(e for e in events if e["event"] == "done")
    done_data = json.loads(done_event["data"])
    assert "opportunity_output" in done_data
    assert done_data["opportunity_output"] is not None
