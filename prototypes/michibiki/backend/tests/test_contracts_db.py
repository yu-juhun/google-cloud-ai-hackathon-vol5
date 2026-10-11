from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
)

from michibiki import db
from michibiki.contracts import MissionInput, Profile

OWNER = "test-owner-hash"


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
    first, created = db.begin_mission(OWNER, request())
    assert created
    second, created = db.begin_mission(OWNER, request())
    assert not created and first["id"] == second["id"]
    conflicting = request().model_copy(deep=True)
    conflicting.trip.wish = "美術館に行きたい"
    with pytest.raises(ValueError, match="idempotency_conflict"):
        db.begin_mission(OWNER, conflicting)
    with database.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.missions)).scalar() == 1
        assert (
            conn.execute(select(func.count()).select_from(db.migrations)).scalar() == 5
        )


def test_reports_itinerary_and_save_survive_read(database):
    mission, _ = db.begin_mission(OWNER, request())
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
    assert db.get_mission(OWNER, mission["id"])["result"] == saved
    assert not db.is_itinerary_saved(mission["id"])
    assert db.save_itinerary(OWNER, mission["id"])
    assert db.is_itinerary_saved(mission["id"])
    assert not db.save_itinerary(OWNER, "missing")
    with database.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.twins)).scalar() == 3
        assert conn.execute(select(func.count()).select_from(db.reports)).scalar() == 3
        assert (
            conn.execute(select(func.count()).select_from(db.itineraries)).scalar() == 1
        )


def test_failure_is_persisted(database):
    mission, _ = db.begin_mission(OWNER, request())
    db.fail_mission(mission["id"], "timeout")
    assert db.get_mission(OWNER, mission["id"])["status"] == "timed_out"


def test_profile_is_scoped_by_owner(database):
    assert db.get_profile(OWNER) is None
    db.save_profile(OWNER, {"chair": "電動車いす"})
    assert db.get_profile(OWNER) == {"chair": "電動車いす"}
    assert db.get_profile("other-owner") is None


def test_missions_are_scoped_by_owner(database):
    mission, _ = db.begin_mission(OWNER, request())
    assert db.get_mission(OWNER, mission["id"]) is not None
    assert db.get_mission("other-owner", mission["id"]) is None
    assert not db.save_itinerary("other-owner", mission["id"])


def test_same_idempotency_key_does_not_collide_across_owners(database):
    first, created_first = db.begin_mission(OWNER, request())
    second, created_second = db.begin_mission("other-owner", request())
    assert created_first and created_second
    assert first["id"] != second["id"]


def test_list_missions_returns_newest_first_capped_at_limit(database):
    import time

    for i in range(3):
        req = request()
        req.idempotency_key = f"test-request-{i:03d}"
        db.begin_mission(OWNER, req)
        time.sleep(0.01)
    listed = db.list_missions(OWNER, limit=2)
    assert len(listed) == 2
    assert listed[0]["created_at"] > listed[1]["created_at"]
    assert all(m["destination"] == "東京" for m in listed)
    assert all(m["status"] == "running" for m in listed)


def test_list_missions_empty_for_brand_new_owner(database):
    assert db.list_missions("never-seen-owner") == []


def test_migrate_demo_owner_data_moves_profile_and_missions(database):
    mission, _ = db.begin_mission(db.DEMO_OWNER, request())
    db.save_profile(db.DEMO_OWNER, {"chair": "手動車いす"})

    db.migrate_demo_owner_data("real-client-hash")

    assert db.get_profile(db.DEMO_OWNER) is None
    assert db.get_profile("real-client-hash") == {"chair": "手動車いす"}
    assert db.get_mission(db.DEMO_OWNER, mission["id"]) is None
    assert db.get_mission("real-client-hash", mission["id"]) is not None


def test_migrate_demo_owner_data_keeps_existing_target_profile(database):
    db.save_profile(db.DEMO_OWNER, {"chair": "手動車いす"})
    db.save_profile("real-client-hash", {"chair": "電動車いす"})
    mission, _ = db.begin_mission(db.DEMO_OWNER, request())

    db.migrate_demo_owner_data("real-client-hash")

    assert db.get_profile("real-client-hash") == {"chair": "電動車いす"}
    assert db.get_mission("real-client-hash", mission["id"]) is not None


def test_migrate_demo_owner_data_is_a_noop_when_nothing_to_migrate(database):
    db.migrate_demo_owner_data("real-client-hash")  # must not raise
    assert db.get_profile("real-client-hash") is None


def test_avatar_pool_tracks_used_styles_per_version(database):
    assert db.get_current_avatar_version("client-1") == 1
    assert db.get_used_template_ids("client-1", 1) == set()
    db.add_avatar_pool_entries("client-1", 1, [
        {"template_id": "female_manga_mood", "object_name": "avatars/a/female_manga_mood"},
        {"template_id": "male_cool_mood", "object_name": "avatars/a/male_cool_mood"},
    ])
    assert db.get_used_template_ids("client-1", 1) == {"female_manga_mood", "male_cool_mood"}
    assert db.get_current_avatar_version("client-1") == 1
    pool = db.get_avatar_pool("client-1")
    assert len(pool) == 2
    assert db.get_used_template_ids("other-client", 1) == set()


def test_avatar_pool_wraparound_to_a_new_version(database):
    db.add_avatar_pool_entries("client-1", 1, [
        {"template_id": "female_manga_mood", "object_name": "avatars/a/female_manga_mood"},
    ])
    db.delete_avatar_pool_version("client-1", 1)
    db.add_avatar_pool_entries("client-1", 2, [
        {"template_id": "female_manga_mood", "object_name": "avatars/b/female_manga_mood"},
    ])
    assert db.get_current_avatar_version("client-1") == 2
    assert db.get_used_template_ids("client-1", 1) == set()  # version 1 was deleted
    assert db.get_used_template_ids("client-1", 2) == {"female_manga_mood"}
    assert len(db.get_avatar_pool("client-1")) == 1  # only the current version


def test_profile_avatar_selection_round_trips_and_upserts_a_missing_profile(database):
    assert db.get_profile_avatar("client-2") is None
    db.set_profile_avatar("client-2", "avatars/x/female_manga_mood")
    assert db.get_profile_avatar("client-2") == "avatars/x/female_manga_mood"
    db.set_profile_avatar("client-2", "avatars/x/male_cool_mood")
    assert db.get_profile_avatar("client-2") == "avatars/x/male_cool_mood"


def test_create_and_update_avatar_set_with_version(database):
    tasks = [{"template_id": "female_manga_mood", "task_id": "task-1"}]
    record = db.create_avatar_set("client-3", tasks, version=1)
    assert record["status"] == "generating"
    assert record["version"] == 1
    assert record["provider_task_ids"] == tasks
    db.update_avatar_set(record["id"], "ready")
    fetched = db.get_avatar_set(record["id"], "client-3")
    assert fetched["status"] == "ready"


def test_migration_5_upgrades_a_pre_existing_version_4_database(tmp_path, monkeypatch):
    """Seeds a fresh sqlite file at the pre-version-5 shape (schema_migrations with
    rows 1-4, and a profiles table WITHOUT avatar_object_name — no avatar_pool table)
    and confirms db.migrate() drives the actual UPGRADE branch: ALTER TABLE profiles
    ADD COLUMN avatar_object_name + avatar_pool.create(), not the fresh-create path
    every other fixture exercises."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)

    legacy_metadata = MetaData()
    legacy_migrations = Table(
        "schema_migrations", legacy_metadata, Column("version", Integer, primary_key=True)
    )
    legacy_profiles = Table(
        "profiles",
        legacy_metadata,
        Column("owner_id", String, primary_key=True),
        Column("conditions", JSON(), nullable=False),
        Column("version", Integer, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    with engine.begin() as conn:
        legacy_metadata.create_all(conn)
        conn.execute(insert(legacy_profiles).values(
            owner_id="legacy-owner", conditions={}, version=1, updated_at=datetime.now(UTC),
        ))
        for v in (1, 2, 3, 4):
            conn.execute(insert(legacy_migrations).values(version=v))

    db.migrate(engine)

    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.migrations)).scalar() == 5

    db.add_avatar_pool_entries("client-upgrade", 1, [
        {"template_id": "female_manga_mood", "object_name": "avatars/u/female_manga_mood"},
    ])
    assert db.get_used_template_ids("client-upgrade", 1) == {"female_manga_mood"}

    assert db.get_profile_avatar("legacy-owner") is None
    db.set_profile_avatar("legacy-owner", "avatars/u/female_manga_mood")
    assert db.get_profile_avatar("legacy-owner") == "avatars/u/female_manga_mood"

    engine.dispose()
