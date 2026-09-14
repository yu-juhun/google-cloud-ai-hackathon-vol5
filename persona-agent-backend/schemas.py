"""Persona output schema. category is intentionally free-form text, not
an enum — the design decision (see design spec, "背景・非目標") is that
the intake agent must not lock users into a predetermined attribute list.
domain IS a fixed enum (see the v2 design spec's "ペルソナJSONスキーマの変更")
— it groups attributes into a small set of buckets other agents can rely
on, while category/description underneath stay free-form.
"""
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["high", "medium", "low"]
Domain = Literal["mobility", "dietary", "purpose", "companions", "language", "background", "other"]


class Attribute(BaseModel):
    domain: Domain
    category: str
    description: str
    rank: int
    confidence: Level
    inferred_keywords: list[str] = Field(default_factory=list)


class Persona(BaseModel):
    persona_id: str
    raw_summary: str
    attributes: list[Attribute] = Field(default_factory=list)
