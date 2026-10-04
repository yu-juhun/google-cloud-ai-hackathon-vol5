from copy import deepcopy

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select

from michibiki import db
from michibiki.contracts import MissionInput, Profile


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    db.migrate(engine)
    yield engine
    engine.dispose()


def request():
    return MissionInput(
        profile=Profile(),
        trip={
            "destination": "東京",
            "date": "未定",
            "time": "10:00–16:00",
            "wish": "推し活をしたい",
        },
        idempotency_key="test-request-001",
    )


def test_rejects_avatar_and_client_owner():
    with pytest.raises(ValidationError):
        Profile(avatar="private-photo")
    with pytest.raises(ValidationError):
        MissionInput(**request().model_dump(), owner_id="other")


def test_migration_and_idempotency(database):
    db.migrate(database)
    first, created = db.begin_mission(request())
    assert created
    second, created = db.begin_mission(request())
    assert not created and first["id"] == second["id"]
    conflicting = request().model_copy(deep=True)
    conflicting.trip.wish = "美術館に行きたい"
    with pytest.raises(ValueError, match="idempotency_conflict"):
        db.begin_mission(conflicting)
    with database.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.missions)).scalar() == 1
        assert (
            conn.execute(select(func.count()).select_from(db.migrations)).scalar() == 2
        )


def test_reports_itinerary_and_save_survive_read(database):
    mission, _ = db.begin_mission(request())
    result = {
        "status": "completed",
        "twins": [
            {
                "assignment": {"role": f"role-{i}"},
                "status": "completed",
                "assessments": [],
            }
            for i in range(3)
        ],
        "itinerary": {"title": "test", "stops": []},
        "places": [{"place_id": "test-place"}],
    }
    saved = db.finish_mission(mission["id"], deepcopy(result))
    assert saved["persisted"]
    assert db.get_mission(mission["id"])["result"] == saved
    assert not db.is_itinerary_saved(mission["id"])
    assert db.save_itinerary(mission["id"])
    assert db.is_itinerary_saved(mission["id"])
    assert not db.save_itinerary("missing")
    with database.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.twins)).scalar() == 3
        assert conn.execute(select(func.count()).select_from(db.reports)).scalar() == 3
        assert (
            conn.execute(select(func.count()).select_from(db.itineraries)).scalar() == 1
        )


def test_failure_is_persisted(database):
    mission, _ = db.begin_mission(request())
    db.fail_mission(mission["id"], "timeout")
    assert db.get_mission(mission["id"])["status"] == "timed_out"
