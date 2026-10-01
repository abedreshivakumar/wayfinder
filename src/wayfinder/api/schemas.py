"""Request bodies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NarrateRequest(BaseModel):
    node_id: str


class AskRequest(BaseModel):
    repo: str
    question: str


class CheckDriftRequest(BaseModel):
    node_id: str


class ExplainPathRequest(BaseModel):
    from_id: str
    to_id: str
    max_hops: int = 5


class TraceRequest(BaseModel):
    repo: str
    file: str
    function: str | None = None
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class ExplainFileRequest(BaseModel):
    repo: str
    file: str
