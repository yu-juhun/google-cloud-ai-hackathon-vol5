"""Persona output schema. category is intentionally free-form text, not
an enum — the design decision (see design spec, "背景・非目標") is that
the intake agent must not lock users into a predetermined attribute list.
"""
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["high", "medium", "low"]


class Attribute(BaseModel):
    category: str
    description: str
    priority: Level
    confidence: Level
    inferred_keywords: list[str] = Field(default_factory=list)


class Persona(BaseModel):
    persona_id: str
    raw_summary: str
    attributes: list[Attribute] = Field(default_factory=list)
