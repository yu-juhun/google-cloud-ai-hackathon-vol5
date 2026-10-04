from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chair: str = Field(default="手動車いす", max_length=40)
    width: float = Field(default=70, gt=0, le=200)
    step: float = Field(default=2, ge=0, le=50)
    stamina: int = Field(default=20, ge=1, le=180)
    companion: str = Field(default="ひとり", max_length=40)
    home: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=500)
    priorities: list[str] = Field(default_factory=list, max_length=10)


class Trip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(min_length=1, max_length=100)
    date: str = Field(min_length=1, max_length=40)
    time: str = Field(min_length=1, max_length=40)
    wish: str = Field(min_length=1, max_length=1000)
    twin_count: int = Field(default=3, ge=1, le=10)


class MissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Profile
    trip: Trip
    idempotency_key: str = Field(min_length=8, max_length=100)


class Assignment(BaseModel):
    role: str = Field(min_length=1, max_length=60)
    goal: str = Field(min_length=1, max_length=500)
    search_query: str = Field(min_length=1, max_length=160)


class Plan(BaseModel):
    assignments: list[Assignment] = Field(min_length=1, max_length=10)
    clarification: str = Field(default="", max_length=500)


class Assessment(BaseModel):
    place_id: str
    status: Literal["uncertain", "accessible", "not_accessible"]
    facts: list[str]
    unknowns: list[str]
    experience: str
    fit_reason: str
    precautions: list[str]
    source_ids: list[str] = Field(default_factory=list)


class AssessmentBatch(BaseModel):
    assessments: list[Assessment] = Field(min_length=1, max_length=4)


class Stop(BaseModel):
    place_id: str
    activity: str
    duration_minutes: int = Field(ge=5, le=180)
    rest_after: bool
    reasoning: str


class Itinerary(BaseModel):
    title: str
    summary: str
    stops: list[Stop] = Field(min_length=1, max_length=6)
    unknowns: list[str]
    alternatives: list[str]
    assumptions: list[str]
