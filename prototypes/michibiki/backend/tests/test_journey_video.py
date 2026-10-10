from copy import deepcopy
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine

from michibiki import db
from michibiki.contracts import MissionInput, Profile
from michibiki.journey_video import advance, storyboard
from michibiki.server import app


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'journey.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    db.migrate(engine)
    yield engine
    engine.dispose()


def mission():
    return {"result": {"twins": [], "itinerary": {"stops": [
        {"place_id": str(i), "activity": f"activity-{i}"} for i in range(7)]}}}


def test_storyboard_spans_itinerary_and_is_bounded():
    scenes = storyboard(mission(), {str(i): f"place-{i}" for i in range(7)})
    assert [s["place_id"] for s in scenes] == ["0", "2", "4", "6"]
    assert [s["activity"] for s in scenes] == ["activity-0", "activity-2", "activity-4", "activity-6"]


def test_storyboard_excludes_known_inaccessible_stop():
    data = mission()
    data["result"]["twins"] = [{"assessments": [{"place_id": "2", "status": "not_accessible"}]}]
    assert "2" not in [s["place_id"] for s in storyboard(data, {})]


def test_journey_owner_duplicate_and_progress_lease(database):
    request = MissionInput(profile=Profile(), trip={"destination": "東京", "date": "未定",
        "time": "10:00–16:00", "wish": "美術館に行きたい"}, idempotency_key="journey-test")
    saved, _ = db.begin_mission("owner", request)
    job, created = db.begin_journey_video("owner", saved["id"], {"scenes": []})
    assert created
    same, created = db.begin_journey_video("owner", saved["id"], {})
    assert not created and same["id"] == job["id"]
    assert db.find_journey_video("other-owner", saved["id"]) is None
    assert db.claim_journey_progress(job["id"])
    assert not db.claim_journey_progress(job["id"])
    db.release_journey_progress(job["id"])
    assert db.claim_journey_progress(job["id"])


def test_create_rejects_foreign_mission_without_provider_calls():
    with patch("michibiki.db.get_mission", return_value=None), patch("michibiki.journey_video.video_rpc") as rpc:
        response = TestClient(app).post("/api/journey-videos", headers={"X-Michibiki-Client": "a" * 40},
            json={"mission_id": "foreign", "consent": True})
        assert response.status_code == 404
        rpc.assert_not_called()


def test_retry_editing_reuses_saved_job_without_generation_or_preparation():
    job = {"id": "saved-movie", "status": "failed", "body": {"prepared": True,
           "error": "invalid_video_result", "scenes": [{"status": "ready", "object_name": "saved-scene.mp4"}]}}
    with patch("michibiki.db.get_mission", return_value={"result": {"itinerary": {}}}), \
         patch("michibiki.db.find_journey_video", return_value=job), \
         patch("michibiki.db.save_journey_video") as save, \
         patch("michibiki.journey_video.video_rpc") as rpc, \
         patch("michibiki.db.begin_journey_video") as begin:
        response = TestClient(app).post("/api/journey-videos", headers={"X-Michibiki-Client": "a" * 40},
            json={"mission_id": "own-trip", "consent": True})
    assert response.status_code == 200
    assert response.json() == {"id": "saved-movie", "status": "rendering"}
    assert "error" not in save.call_args.args[2]
    rpc.assert_not_called()
    begin.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_submission_is_not_repeated():
    job = {"id": "job", "client_hash": "owner", "status": "generating", "body": {"prepared": True,
           "scenes": [{"status": "submitting"}]}}
    with patch("michibiki.db.claim_journey_progress", return_value=True), \
         patch("michibiki.db.get_journey_video", return_value=job), \
         patch("michibiki.db.save_journey_video") as save, patch("michibiki.db.release_journey_progress"), \
         patch("michibiki.journey_video.video_rpc", new_callable=AsyncMock) as rpc:
        await advance(deepcopy(job))
        rpc.assert_not_awaited()
        assert save.call_args.args[1] == "failed"
        assert save.call_args.args[2]["error"] == "submission_outcome_unknown"
