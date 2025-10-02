"""Pydantic schemas for read-only API responses.

Note: We purposefully do not enforce these via FastAPI response_model to avoid
any shape coercion. They are provided for documentation and potential future
validation. The live server returns exactly what probe helpers return.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SnapshotIdentity(BaseModel):
    name: str | None = None
    traits: dict[str, float] = Field(default_factory=dict)


class SnapshotModel(BaseModel):
    identity: SnapshotIdentity
    commitments: dict[str, Any]
    events: list[dict[str, Any]]
    directives: dict[str, Any] | None = None


class DirectiveRow(BaseModel):
    content: str
    first_seen_ts: str | None = None
    last_seen_ts: str | None = None
    first_seen_id: int | None = None
    last_seen_id: int | None = None
    seen_count: int
    sources: list[str] = Field(default_factory=list)
    last_origin_eid: int | None = None


class DirectiveActiveRow(BaseModel):
    content: str
    seen_count: int
    recent_hits: int
    score: float
    first_seen_id: int | None = None
    last_seen_id: int | None = None
    sources: list[str] = Field(default_factory=list)


class ViolationRow(BaseModel):
    ts: str | None
    id: int | None
    code: str | None
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class OpenCommitmentRow(BaseModel):
    id: int | None
    ts: str | None
    cid: str = ""
    content: str | None = None
    origin_eid: int | None = None
