"""Pydantic schemas for read-only API responses.

Note: We purposefully do not enforce these via FastAPI response_model to avoid
any shape coercion. They are provided for documentation and potential future
validation. The live server returns exactly what probe helpers return.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SnapshotIdentity(BaseModel):
    name: Optional[str] = None
    traits: Dict[str, float] = Field(default_factory=dict)


class SnapshotModel(BaseModel):
    identity: SnapshotIdentity
    commitments: Dict[str, Any]
    events: List[Dict[str, Any]]
    directives: Dict[str, Any] | None = None


class DirectiveRow(BaseModel):
    content: str
    first_seen_ts: Optional[str] = None
    last_seen_ts: Optional[str] = None
    first_seen_id: Optional[int] = None
    last_seen_id: Optional[int] = None
    seen_count: int
    sources: List[str] = Field(default_factory=list)
    last_origin_eid: Optional[int] = None


class DirectiveActiveRow(BaseModel):
    content: str
    seen_count: int
    recent_hits: int
    score: float
    first_seen_id: Optional[int] = None
    last_seen_id: Optional[int] = None
    sources: List[str] = Field(default_factory=list)


class ViolationRow(BaseModel):
    ts: Optional[str]
    id: Optional[int]
    code: Optional[str]
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class OpenCommitmentRow(BaseModel):
    id: Optional[int]
    ts: Optional[str]
    cid: str = ""
    content: Optional[str] = None
    origin_eid: Optional[int] = None
