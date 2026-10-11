"""Both pre-merge database lineages must retain saved media and avatar ownership."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, create_engine, insert, inspect, select

from michibiki import db


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'compat.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    yield engine
    engine.dispose()


def test_existing_video_v5_keeps_movie_and_legacy_avatar(database):
    old = MetaData()
    profiles = Table("profiles", old, Column("owner_id", String, primary_key=True),
        Column("conditions", JSON, nullable=False), Column("version", Integer, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False))
    avatars = Table("avatar_sets", old, Column("id", String, primary_key=True),
        Column("client_hash", String, nullable=False), Column("provider_task_id", String, nullable=False),
        Column("status", String, nullable=False), Column("assets", JSON),
        Column("created_at", DateTime(timezone=True), nullable=False))
    ledger = db.migrations.to_metadata(old)
    missions = db.missions.to_metadata(old)
    jobs = db.journey_video_jobs.to_metadata(old)
    stamp = datetime.now(UTC)
    with database.begin() as conn:
        old.create_all(conn)
        conn.execute(insert(profiles).values(owner_id="owner", conditions={}, version=1, updated_at=stamp))
        conn.execute(insert(missions).values(id="trip", owner_id="owner", idempotency_key="one",
            status="completed", input_snapshot={}, result={}, created_at=stamp))
        conn.execute(insert(jobs).values(id="movie", client_hash="owner", mission_id="trip", status="ready",
            body={"scenes": [{"status": "ready", "object_name": "saved/scene.mp4"}]},
            object_name="saved/movie.mp4", created_at=stamp))
        conn.execute(insert(avatars).values(id="old-avatar", client_hash="owner", provider_task_id="old-task",
            status="ready", assets={"assets": [{"object_name": "avatars/old.png"}]}, created_at=stamp))
        conn.execute(insert(ledger), [{"version": i} for i in range(1, 6)])
    db.migrate(database)
    db.migrate(database)
    assert db.find_journey_video("owner", "trip")["object_name"] == "saved/movie.mp4"
    assert db.find_journey_video("other", "trip") is None
    assert db.find_latest_ready_avatar_set("owner")["assets"]["assets"][0]["object_name"] == "avatars/old.png"
    assert db.find_latest_ready_avatar_set("other") is None
    assert inspect(database).has_table("avatar_sets_legacy")
    assert db.get_avatar_set("old-avatar", "owner")["version"] == 1
    assert db.get_avatar_set("old-avatar", "other") is None
    assert db.get_profile_avatar("owner") == "avatars/old.png"
    assert len(db.get_avatar_pool("owner")) == 1
    with database.connect() as conn:
        assert set(conn.execute(select(db.migrations.c.version)).scalars()) == set(range(1, 9))
    new = db.create_avatar_set("owner", [{"template_id": "new-style", "task_id": "new-task"}], 1)
    assert db.get_avatar_set(new["id"], "owner")["provider_task_ids"][0]["task_id"] == "new-task"


def test_avatar_v7_adds_journey_without_resetting_pool(database):
    db.migrate(database)
    db.add_avatar_pool_entries("owner", 1, [{"template_id": "style", "object_name": "avatars/new.png"}])
    db.set_profile_avatar("owner", "avatars/new.png")
    with database.begin() as conn:
        db.journey_video_jobs.drop(conn)
        conn.execute(db.migrations.delete().where(db.migrations.c.version == 8))
    db.migrate(database)
    assert inspect(database).has_table("journey_video_jobs")
    assert db.get_profile_avatar("owner") == "avatars/new.png"
    assert len(db.get_avatar_pool("owner")) == 1


def test_video_prefers_selected_owned_avatar(database):
    db.migrate(database)
    db.add_avatar_pool_entries("owner", 1, [
        {"template_id": "first", "object_name": "avatars/first.png"},
        {"template_id": "chosen", "object_name": "avatars/chosen.jpg"}])
    db.add_avatar_pool_entries("other", 1, [{"template_id": "other", "object_name": "avatars/private.png"}])
    db.set_profile_avatar("owner", "avatars/chosen.jpg")
    assert db.find_latest_ready_avatar_set("owner")["assets"]["assets"][0]["object_name"] == "avatars/chosen.jpg"
    db.set_profile_avatar("owner", "avatars/private.png")
    assert db.find_latest_ready_avatar_set("owner")["assets"]["assets"][0]["object_name"] == "avatars/first.png"
