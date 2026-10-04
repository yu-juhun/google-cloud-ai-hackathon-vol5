import pytest

from michibiki import agents
from michibiki.contracts import Itinerary


async def test_judge_uses_alias_and_restores_verified_place_id(monkeypatch):
    async def generate(model, instruction, payload, schema):
        assert payload["places"][0]["place_id"] == "candidate_1"
        return {"assessments": [{"place_id": "candidate_1"}]}

    monkeypatch.setattr(agents, "generate", generate)
    answer = await agents.specialist(
        "judge", {"places": [{"place_id": "actual-place-id"}]}
    )
    assert answer["assessments"][0]["place_id"] == "actual-place-id"


async def test_unknown_ids_are_rejected(monkeypatch):
    async def generate(*args):
        return {"assessments": [{"place_id": "invented"}]}

    monkeypatch.setattr(agents, "generate", generate)
    with pytest.raises(ValueError, match="unknown place"):
        await agents.specialist("judge", {"places": [{"place_id": "actual-place-id"}]})


def test_coordinate_distance_is_not_a_travel_time():
    context = agents.distance_context(
        {
            "a": {"location": {"latitude": 0, "longitude": 0}},
            "b": {"location": {"latitude": 0, "longitude": 0.001}},
        },
        {"a": "candidate_1", "b": "candidate_2"},
    )
    assert context == [{"from": "candidate_1", "to": "candidate_2", "meters": 111}]


async def test_recommend_does_not_allow_rejected_place(monkeypatch):
    async def generate(model, instruction, payload, schema):
        assert schema is Itinerary
        return {"stops": [{"place_id": "candidate_1"}]}

    monkeypatch.setattr(agents, "generate", generate)
    with pytest.raises(ValueError, match="unsuitable"):
        await agents.specialist(
            "recommend",
            {
                "twins": [
                    {
                        "places": [{"place_id": "a"}],
                        "assessments": [{"place_id": "a", "status": "not_accessible"}],
                    }
                ]
            },
        )
