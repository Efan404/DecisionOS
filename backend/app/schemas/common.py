from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DirectionId = Literal["A", "B", "C", "D", "E", "F"]
PathId = Literal["pathA", "pathB", "pathC"]
PriorityLevel = Literal["P0", "P1", "P2"]


class HealthResponse(BaseModel):
    ok: bool = Field(default=True)


class Direction(BaseModel):
    id: DirectionId
    title: str
    one_liner: str
    pain_tags: list[str]


class ScoreBreakdown(BaseModel):
    technical_feasibility: float = Field(ge=0, le=10)
    market_viability: float = Field(ge=0, le=10)
    execution_risk: float = Field(ge=0, le=10)


class ReasoningBreakdown(BaseModel):
    technical_feasibility: str
    market_viability: str
    execution_risk: str


class Competitor(BaseModel):
    name: str
    url: str | None = None
    similarity: str
