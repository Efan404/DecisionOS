from __future__ import annotations

import os

import pytest

from tests._test_env import ensure_required_seed_env


@pytest.fixture()
def vs():
    ensure_required_seed_env()
    # Force fresh in-memory instance
    from app.agents.memory.vector_store import VectorStore

    store = VectorStore(persist_directory=None)
    # Reset the market_evidence collection so tests are isolated
    store._client.delete_collection("market_evidence")
    store._market_evidence = store._client.get_or_create_collection(
        name="market_evidence",
        metadata={"hnsw:space": "cosine"},
    )
    return store


def test_add_and_search_competitor_chunk(vs):
    meta = {
        "entity_type": "competitor_positioning",
        "entity_id": "comp-1",
        "workspace_id": "ws-1",
        "source_type": "manual",
        "created_at": "2026-03-07T00:00:00Z",
        "confidence": 0.9,
    }
    vs.add_competitor_chunk(
        chunk_id="chunk-comp-1",
        text="Competitor X dominates the B2B SaaS market with aggressive pricing",
        metadata=meta,
    )
    results = vs.search_market_evidence(query="B2B SaaS competitor pricing")
    assert len(results) == 1
    r = results[0]
    assert r["chunk_id"] == "chunk-comp-1"
    assert r["text"] == "Competitor X dominates the B2B SaaS market with aggressive pricing"
    assert r["metadata"]["entity_type"] == "competitor_positioning"
    assert r["metadata"]["entity_id"] == "comp-1"
    assert r["metadata"]["workspace_id"] == "ws-1"
    assert r["metadata"]["source_type"] == "manual"
    assert r["metadata"]["confidence"] == 0.9
    assert "distance" in r


def test_add_and_search_signal_chunk(vs):
    meta = {
        "entity_type": "market_signal_summary",
        "entity_id": "sig-1",
        "workspace_id": "ws-1",
        "source_type": "hn",
        "created_at": "2026-03-07T00:00:00Z",
        "confidence": 0.75,
    }
    vs.add_market_signal_chunk(
        chunk_id="chunk-sig-1",
        text="Hacker News discussion shows rising interest in AI developer tools",
        metadata=meta,
    )
    results = vs.search_market_evidence(query="AI developer tools trends")
    assert len(results) == 1
    r = results[0]
    assert r["chunk_id"] == "chunk-sig-1"
    assert r["text"] == "Hacker News discussion shows rising interest in AI developer tools"
    assert r["metadata"]["entity_type"] == "market_signal_summary"
    assert r["metadata"]["entity_id"] == "sig-1"
    assert r["metadata"]["source_type"] == "hn"
    assert r["metadata"]["confidence"] == 0.75
    assert "distance" in r


def test_add_and_search_insight_chunk(vs):
    meta = {
        "entity_type": "evidence_insight",
        "entity_id": "ins-1",
        "workspace_id": "ws-1",
        "created_at": "2026-03-07T00:00:00Z",
        "confidence": 0.85,
    }
    vs.add_evidence_insight_chunk(
        chunk_id="chunk-ins-1",
        text="Cross-referencing signals suggests underserved niche in compliance tools",
        metadata=meta,
    )
    results = vs.search_market_evidence(query="compliance tools market gap")
    assert len(results) == 1
    r = results[0]
    assert r["chunk_id"] == "chunk-ins-1"
    assert r["text"] == "Cross-referencing signals suggests underserved niche in compliance tools"
    assert r["metadata"]["entity_type"] == "evidence_insight"
    assert r["metadata"]["entity_id"] == "ins-1"
    assert r["metadata"]["confidence"] == 0.85
    assert "distance" in r


def test_search_with_filter(vs):
    vs.add_competitor_chunk(
        chunk_id="chunk-f-1",
        text="Competitor Y has a free tier targeting SMBs",
        metadata={
            "entity_type": "competitor_pricing",
            "entity_id": "comp-2",
            "workspace_id": "ws-1",
            "source_type": "manual",
            "created_at": "2026-03-07T00:00:00Z",
            "confidence": 0.8,
        },
    )
    vs.add_market_signal_chunk(
        chunk_id="chunk-f-2",
        text="SMB market is growing rapidly according to recent reports",
        metadata={
            "entity_type": "market_signal_summary",
            "entity_id": "sig-2",
            "workspace_id": "ws-1",
            "source_type": "report",
            "created_at": "2026-03-07T00:00:00Z",
            "confidence": 0.7,
        },
    )
    # Filter for competitor_pricing only
    results = vs.search_market_evidence(
        query="SMB pricing",
        n_results=5,
        filters={"entity_type": "competitor_pricing"},
    )
    assert len(results) == 1
    assert results[0]["metadata"]["entity_type"] == "competitor_pricing"

    # Filter for market_signal_summary only
    results = vs.search_market_evidence(
        query="SMB pricing",
        n_results=5,
        filters={"entity_type": "market_signal_summary"},
    )
    assert len(results) == 1
    assert results[0]["metadata"]["entity_type"] == "market_signal_summary"


def test_search_empty_collection(vs):
    results = vs.search_market_evidence(query="anything at all")
    assert results == []


def test_upsert_overwrites(vs):
    meta = {
        "entity_type": "competitor_features",
        "entity_id": "comp-3",
        "workspace_id": "ws-1",
        "source_type": "manual",
        "created_at": "2026-03-07T00:00:00Z",
        "confidence": 0.6,
    }
    vs.add_competitor_chunk(
        chunk_id="chunk-upsert-1",
        text="Original text about competitor features",
        metadata=meta,
    )
    # Upsert same chunk_id with updated text and confidence
    updated_meta = {**meta, "confidence": 0.95}
    vs.add_competitor_chunk(
        chunk_id="chunk-upsert-1",
        text="Updated text about competitor features with new data",
        metadata=updated_meta,
    )
    results = vs.search_market_evidence(query="competitor features")
    assert len(results) == 1
    assert results[0]["chunk_id"] == "chunk-upsert-1"
    assert results[0]["text"] == "Updated text about competitor features with new data"
    assert results[0]["metadata"]["confidence"] == 0.95
