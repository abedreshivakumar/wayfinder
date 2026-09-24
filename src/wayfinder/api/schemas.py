"""Request bodies."""

from __future__ import annotations

from pydantic import BaseModel


class NarrateRequest(BaseModel):
    node_id: str


class CheckDriftRequest(BaseModel):
    node_id: str


class ExplainPathRequest(BaseModel):
    from_id: str
    to_id: str
    max_hops: int = 5
