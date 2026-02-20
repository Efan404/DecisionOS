from __future__ import annotations

from pydantic import BaseModel


class IdeaNodeOut(BaseModel):
    id: str
    idea_id: str
    parent_id: str | None
    content: str
    expansion_pattern: str | None
    edge_label: str | None
    depth: int
    status: str
    created_at: str


class CreateRootNodeRequest(BaseModel):
    content: str


class UserExpandRequest(BaseModel):
    description: str


class ConfirmPathRequest(BaseModel):
    node_chain: list[str]


class IdeaPathOut(BaseModel):
    id: str
    idea_id: str
    node_chain: list[str]
    path_md: str
    path_json: str
    created_at: str


EXPANSION_PATTERNS: list[dict[str, str]] = [
    {"id": "narrow_users", "label": "缩小用户群体", "description": "针对更精准的细分用户群重新定义问题"},
    {"id": "expand_features", "label": "功能边界扩展", "description": "在核心功能基础上延伸出相邻能力"},
    {"id": "shift_scenario", "label": "场景迁移", "description": "将此 idea 迁移至不同使用场景"},
    {"id": "monetize", "label": "商业模式变体", "description": "探索不同的商业化路径"},
    {"id": "simplify", "label": "极简核心", "description": "只保留最小可行内核，砍掉所有附加物"},
]
