from sqlalchemy import create_engine

import pytest
from fastapi.testclient import TestClient

from michibiki import db
from michibiki.server import app

client = TestClient(app)
HEADERS_A = {"X-Michibiki-Client": "a" * 40}
HEADERS_B = {"X-Michibiki-Client": "b" * 40}


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    db.migrate(engine)
    yield engine
    engine.dispose()


def _trip_payload():
    return {
        "profile": {},
        "trip": {"destination": "福岡", "date": "未定", "time": "10:00–16:00", "wish": "散策したい"},
        "idempotency_key": "router-test-001",
    }


def test_profile_round_trips_per_client(database):
    assert client.get("/api/profile", headers=HEADERS_A).json()["chair"] == "手動車いす"
    client.put("/api/profile", json={"chair": "電動車いす"}, headers=HEADERS_A)
    assert client.get("/api/profile", headers=HEADERS_A).json()["chair"] == "電動車いす"
    assert client.get("/api/profile", headers=HEADERS_B).json()["chair"] == "手動車いす"


def test_profile_requires_client_header(database):
    assert client.get("/api/profile").status_code == 422
    assert client.put("/api/profile", json={"chair": "電動車いす"}).status_code == 422


def test_profile_rejects_malformed_client_token(database):
    too_short = {"X-Michibiki-Client": "short"}
    assert client.get("/api/profile", headers=too_short).status_code == 400
    assert client.put("/api/profile", json={"chair": "電動車いす"}, headers=too_short).status_code == 400


def test_mission_list_is_empty_for_a_new_client(database):
    assert client.get("/api/missions", headers=HEADERS_A).json() == {"missions": []}


def test_mission_is_only_visible_to_its_owner(database, monkeypatch):
    async def fake_rpc(role, payload):
        if role == "orchestrator":
            return {
                "status": "completed", "twins": [], "itinerary": {"title": "t", "stops": []},
                "places": [], "timings": {},
            }
        raise AssertionError("unexpected role")

    monkeypatch.setattr("michibiki.server.rpc", fake_rpc)
    create_response = client.post("/api/missions", json=_trip_payload(), headers=HEADERS_A)
    assert create_response.status_code == 200
    mission_id = create_response.json()["mission_id"]

    assert client.get(f"/api/missions/{mission_id}", headers=HEADERS_A).status_code == 200
    assert client.get(f"/api/missions/{mission_id}", headers=HEADERS_B).status_code == 404
    assert client.post(f"/api/missions/{mission_id}/save", headers=HEADERS_B).status_code == 404
    assert client.post(f"/api/missions/{mission_id}/save", headers=HEADERS_A).status_code == 200

    listed = client.get("/api/missions", headers=HEADERS_A).json()["missions"]
    assert len(listed) == 1 and listed[0]["id"] == mission_id
    assert client.get("/api/missions", headers=HEADERS_B).json() == {"missions": []}
