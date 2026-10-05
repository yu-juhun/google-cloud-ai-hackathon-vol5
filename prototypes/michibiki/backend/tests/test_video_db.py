import pytest
from sqlalchemy import create_engine

from michibiki import db


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    db.migrate(engine)
    yield engine
    engine.dispose()


def test_get_report_returns_none_for_unknown_id(database):
    assert db.get_report("does-not-exist") is None


def test_find_latest_ready_avatar_set_returns_none_when_absent(database):
    assert db.find_latest_ready_avatar_set("hash-1") is None


def test_find_latest_ready_avatar_set_skips_non_ready(database):
    record = db.create_avatar_set("hash-1", "task-1")
    assert db.find_latest_ready_avatar_set("hash-1") is None
    db.update_avatar_set(record["id"], "ready", assets={"assets": [{"object_name": "x.png"}]})
    found = db.find_latest_ready_avatar_set("hash-1")
    assert found["id"] == record["id"]


def test_create_and_get_video_job(database):
    record = db.create_video_job("hash-1", "report-1", "もっと穏やかに", "cinematic", "calm")
    assert record["status"] == "queued"
    assert record["client_hash"] == "hash-1"

    fetched = db.get_video_job(record["id"], "hash-1")
    assert fetched["id"] == record["id"]
    assert fetched["feedback"] == "もっと穏やかに"

    assert db.get_video_job(record["id"], "wrong-hash") is None
    assert db.get_video_job("does-not-exist", "hash-1") is None


def test_update_video_job(database):
    record = db.create_video_job("hash-1", "report-1", "fb", "cinematic", "calm")
    db.update_video_job(record["id"], "generating", provider_operation_name="operations/abc")
    fetched = db.get_video_job(record["id"], "hash-1")
    assert fetched["status"] == "generating"
    assert fetched["provider_operation_name"] == "operations/abc"

    db.update_video_job(record["id"], "ready", object_name="videos/xyz")
    fetched = db.get_video_job(record["id"], "hash-1")
    assert fetched["status"] == "ready"
    assert fetched["object_name"] == "videos/xyz"


def test_find_active_video_job_only_matches_unfinished_status(database):
    record = db.create_video_job("hash-1", "report-1", "fb", "cinematic", "calm")
    assert db.find_active_video_job("hash-1", "report-1")["id"] == record["id"]

    db.update_video_job(record["id"], "ready", object_name="videos/xyz")
    assert db.find_active_video_job("hash-1", "report-1") is None


def test_video_jobs_table_survives_a_fresh_migration(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    db.migrate(engine)  # a brand-new DB must create version 3 directly, not just upgrade from 2
    record = db.create_video_job("hash-1", "report-1", "fb", "cinematic", "calm")
    assert record["status"] == "queued"
    engine.dispose()
