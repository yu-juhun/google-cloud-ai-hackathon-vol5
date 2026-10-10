# 旅行履歴機能 (client_hashベース所有者モデル) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `DEMO_OWNER` single-owner model for `profiles`/`missions` with the existing `client_hash` pattern (already used by `avatar_sets`/`video_jobs`), and add the missing "list my trip history" and "get my profile" endpoints.

**Architecture:** Reuse `media.py`'s existing `client_hash(token)` function (SHA256 of a per-browser token sent as the `X-Michibiki-Client` header, already sent by every frontend `api()` call) as the `owner_id` for `profiles`/`missions`, replacing the `DEMO_OWNER` constant everywhere it's read/written. No schema change — `owner_id` columns are already unbounded `String`. One-time manual data migration moves existing `DEMO_OWNER` rows to a real client's hash.

**Tech Stack:** FastAPI, SQLAlchemy, existing `backend/michibiki` codebase (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-10-06-mission-history-client-identity-design.md`

## Global Constraints

- `GET /api/missions` returns `{"missions": [{id, destination, date, status, created_at}, ...]}`, newest first, capped at 20, no pagination.
- `GET /api/missions/{mission_id}` and `POST /api/missions/{mission_id}/save` return `404` for a mission_id that exists but belongs to a different `client_hash` — never distinguish "doesn't exist" from "not yours" in the response.
- `GET /api/profile` returns `Profile().model_dump()` defaults (not `404`) when the caller has no saved profile yet — a first-time visitor must get a normal response.
- No `migrate()` version bump — `owner_id` columns are already unbounded `String`; this is a data/logic change, not a schema change.
- Existing `DEMO_OWNER` ("hackathon-demo") rows are preserved and migrated to a real `client_hash` via a one-time manual data migration, never deleted outright.
- `client_hash` is computed with the existing `media.client_hash(token)` function — do not write a second implementation.

## Review Focus

- Missing or malformed `X-Michibiki-Client` header on any of the 5 touched endpoints — must behave like the existing avatar/video endpoints (`400` via `client_hash()`'s own validation, or FastAPI's `422` if the header is absent entirely), never a `500`/`KeyError`.
- A brand-new client (no profile, no missions ever) calling `GET /api/profile` — must get `Profile()` defaults, not `404`/`500`.
- A brand-new client calling `GET /api/missions` — must get `{"missions": []}`, not an error.
- Client A passing Client B's real `mission_id` to `GET /api/missions/{id}` or `POST /api/missions/{id}/save` — must `404`, not leak Client B's trip data or let Client A mark Client B's itinerary saved.
- Two different clients using the same `idempotency_key` string for `POST /api/missions` — must NOT collide with each other (the existing `UniqueConstraint("owner_id", "idempotency_key")` already scopes this correctly once `owner_id` is a real per-client value instead of the shared `DEMO_OWNER` constant; a test should pin this explicitly since it's easy to accidentally regress if `owner_id` threading is incomplete).

---

### Task 1: `db.py` — owner-scoped functions and data migration helper

**Files:**
- Modify: `backend/michibiki/michibiki/db.py`
- Modify: `backend/tests/test_contracts_db.py` (existing calls to `begin_mission`/`get_mission`/`save_profile`/`save_itinerary` need an `owner_id` argument added)
- Test: `backend/tests/test_contracts_db.py` (new tests added to the same file)

**Interfaces:**
- Produces: `db.save_profile(owner_id, conditions) -> dict`, `db.get_profile(owner_id) -> dict | None`, `db.begin_mission(owner_id, request, retry=True) -> tuple[dict, bool]`, `db.get_mission(owner_id, mission_id) -> dict | None`, `db.list_missions(owner_id, limit=20) -> list[dict]`, `db.save_itinerary(owner_id, mission_id) -> bool`, `db.migrate_demo_owner_data(target_client_hash) -> None`.
- Consumes: nothing new (pure signature/logic changes to existing functions plus two new ones).

- [ ] **Step 1: Update existing test call sites to pass `owner_id`**

The current `backend/tests/test_contracts_db.py` calls `db.begin_mission(request())`, `db.get_mission(mission["id"])`, and `db.save_itinerary(mission["id"])`/`db.save_itinerary("missing")` with no owner argument. Update every call site in that file to pass an explicit owner_id as the first argument, using a module-level constant for test readability:

```python
# At the top of backend/tests/test_contracts_db.py, after the imports:
OWNER = "test-owner-hash"
```

Then change each call:
- `db.begin_mission(request())` → `db.begin_mission(OWNER, request())` (all three occurrences in `test_migration_and_idempotency`)
- `db.get_mission(mission["id"])` → `db.get_mission(OWNER, mission["id"])` (both occurrences, in `test_reports_itinerary_and_save_survive_read` and `test_failure_is_persisted`)
- `db.save_itinerary(mission["id"])` → `db.save_itinerary(OWNER, mission["id"])`
- `db.save_itinerary("missing")` → `db.save_itinerary(OWNER, "missing")`

This step alone will not pass yet (the implementation hasn't changed) — that's expected; Step 2 confirms the current failure mode, Step 4 makes it pass.

- [ ] **Step 2: Run the existing tests to verify they fail the way we expect**

Run: `cd backend && uv run pytest tests/test_contracts_db.py -v`
Expected: FAIL — `TypeError: begin_mission() takes from 1 to 2 positional arguments but 2 were given` (or similar arity mismatch), confirming the old signatures don't accept `owner_id` yet.

- [ ] **Step 3: Write the new failing tests for this task's new functions**

Add to `backend/tests/test_contracts_db.py`:

```python
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
    db.save_profile(db.DEMO_OWNER, {"chair": "手動車いす"})
    mission, _ = db.begin_mission(db.DEMO_OWNER, request())

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
```

- [ ] **Step 4: Run to verify the new tests fail**

Run: `cd backend && uv run pytest tests/test_contracts_db.py -v`
Expected: FAIL — `AttributeError: module 'michibiki.db' has no attribute 'get_profile'` (and similar for the other new functions/signatures).

- [ ] **Step 5: Implement the signature and logic changes in `db.py`**

Add `delete` to the existing `from sqlalchemy import (...)` block at the top of `db.py` (it currently imports `insert, select, update` from sqlalchemy — add `delete` to that same import list).

Replace `save_profile`:

```python
def save_profile(owner_id, conditions):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    database = engine()
    upsert = pg_insert if database.dialect.name == "postgresql" else sqlite_insert
    statement = (
        upsert(profiles)
        .values(owner_id=owner_id, conditions=conditions, version=1, updated_at=now())
        .on_conflict_do_update(
            index_elements=[profiles.c.owner_id],
            set_={
                "conditions": conditions,
                "version": profiles.c.version + 1,
                "updated_at": now(),
            },
        )
    )
    with database.begin() as conn:
        version = conn.execute(statement.returning(profiles.c.version)).scalar_one()
    return {"conditions": conditions, "version": version}
```

Add `get_profile` right after `save_profile`:

```python
def get_profile(owner_id):
    with engine().connect() as conn:
        row = conn.execute(
            select(profiles.c.conditions).where(profiles.c.owner_id == owner_id)
        ).first()
    return row[0] if row else None
```

Replace `begin_mission`:

```python
def begin_mission(owner_id, request, retry=True):
    from sqlalchemy.exc import IntegrityError

    payload = request.model_dump()
    payload.pop("idempotency_key")
    with engine().connect() as conn:
        old = (
            conn.execute(
                select(missions).where(
                    missions.c.owner_id == owner_id,
                    missions.c.idempotency_key == request.idempotency_key,
                )
            )
            .mappings()
            .first()
        )
    if old:
        if old["input_snapshot"] != payload:
            raise ValueError("idempotency_conflict")
        return dict(old), False
    save_profile(owner_id, payload["profile"])
    mission = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "idempotency_key": request.idempotency_key,
        "input_snapshot": payload,
        "status": "running",
        "created_at": now(),
    }
    try:
        with engine().begin() as conn:
            conn.execute(insert(missions).values(**mission))
    except IntegrityError:
        if not retry:
            raise
        return begin_mission(owner_id, request, retry=False)
    return mission, True
```

Replace `get_mission`:

```python
def get_mission(owner_id, mission_id):
    with engine().connect() as conn:
        row = (
            conn.execute(
                select(missions).where(
                    missions.c.id == mission_id, missions.c.owner_id == owner_id
                )
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None
```

Add `list_missions` right after `get_mission`:

```python
def list_missions(owner_id, limit=20):
    with engine().connect() as conn:
        rows = conn.execute(
            select(
                missions.c.id,
                missions.c.status,
                missions.c.created_at,
                missions.c.input_snapshot,
            )
            .where(missions.c.owner_id == owner_id)
            .order_by(missions.c.created_at.desc())
            .limit(limit)
        ).mappings().all()
    return [
        {
            "id": row["id"],
            "destination": row["input_snapshot"]["trip"]["destination"],
            "date": row["input_snapshot"]["trip"]["date"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
```

Replace `save_itinerary` (it currently has no owner check at all):

```python
def save_itinerary(owner_id, mission_id):
    if not get_mission(owner_id, mission_id):
        return False
    with engine().begin() as conn:
        result = conn.execute(
            update(itineraries)
            .where(itineraries.c.mission_id == mission_id)
            .values(saved_at=now())
        )
    return result.rowcount > 0
```

Add `migrate_demo_owner_data` near the bottom of the file, after `save_consultation`:

```python
def migrate_demo_owner_data(target_client_hash):
    """One-time, manually-invoked data migration — never called from migrate() or
    any endpoint. Moves DEMO_OWNER's profile and missions to a real client_hash.
    Inserts a new profiles row before updating missions.owner_id (not the other way
    around) because missions.owner_id has a plain, non-deferrable FK to
    profiles.owner_id — updating either side first in the wrong order would violate
    that FK mid-transaction."""
    with engine().begin() as conn:
        old_profile = conn.execute(
            select(profiles).where(profiles.c.owner_id == DEMO_OWNER)
        ).mappings().first()
        if not old_profile:
            return
        target_exists = conn.execute(
            select(profiles.c.owner_id).where(profiles.c.owner_id == target_client_hash)
        ).first()
        if not target_exists:
            conn.execute(
                insert(profiles).values(
                    owner_id=target_client_hash,
                    conditions=old_profile["conditions"],
                    version=old_profile["version"],
                    updated_at=old_profile["updated_at"],
                )
            )
        conn.execute(
            update(missions)
            .where(missions.c.owner_id == DEMO_OWNER)
            .values(owner_id=target_client_hash)
        )
        conn.execute(delete(profiles).where(profiles.c.owner_id == DEMO_OWNER))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_contracts_db.py -v`
Expected: PASS (all tests in the file, old and new)

- [ ] **Step 7: Run the full backend suite to check for regressions**

Run: `cd backend && uv run pytest -v`
Expected: PASS (every test in the backend suite, including the video-generation feature's tests from the earlier plan on this same branch)

- [ ] **Step 8: Commit**

```bash
git add backend/michibiki/michibiki/db.py backend/tests/test_contracts_db.py
git commit -m "feat: scope profiles/missions by owner_id instead of DEMO_OWNER"
```

---

### Task 2: `server.py` — client_hash-scoped endpoints + new GET /api/profile and GET /api/missions

**Files:**
- Modify: `backend/michibiki/michibiki/server.py`
- Create: `backend/tests/test_mission_history_router.py`

**Interfaces:**
- Consumes: every function from Task 1 (`db.save_profile`, `db.get_profile`, `db.begin_mission`, `db.get_mission`, `db.list_missions`, `db.save_itinerary`); `media.client_hash(token) -> str` (existing, raises `HTTPException(400, ...)` on an invalid/missing token).
- Produces: `PUT /api/profile`, `GET /api/profile`, `POST /api/missions`, `GET /api/missions`, `GET /api/missions/{mission_id}`, `POST /api/missions/{mission_id}/save` — all now require the `X-Michibiki-Client` header.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_mission_history_router.py
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
```

- [ ] **Step 2: Run to verify the tests fail**

Run: `cd backend && uv run pytest tests/test_mission_history_router.py -v`
Expected: FAIL — `404 Not Found` for `GET /api/profile` (route doesn't exist yet), and `TypeError` from the existing endpoints calling `db.*` functions with the old (now-wrong) arity.

- [ ] **Step 3: Update `server.py`**

Add `client_hash` to the existing media import line:

```python
    from .media import router as media_router
```

becomes:

```python
    from .media import client_hash, router as media_router
```

Replace the `/api/profile` PUT handler:

```python
@app.put("/api/profile")
async def put_profile(profile: Profile, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    return await asyncio.to_thread(db.save_profile, owner_id, profile.model_dump())


@app.get("/api/profile")
async def get_profile_endpoint(x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    conditions = await asyncio.to_thread(db.get_profile, owner_id)
    return conditions if conditions is not None else Profile().model_dump()
```

(The PUT handler is renamed from `profile` to `put_profile` only to free up the name — it was shadowing nothing important, but having both a GET and a PUT needs two distinct function names.)

Add `Header` to the existing `from fastapi import FastAPI, HTTPException` line:

```python
from fastapi import FastAPI, Header, HTTPException
```

Replace `create_mission`:

```python
@app.post("/api/missions")
async def create_mission(request: MissionInput, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    started = time.monotonic()
    try:
        mission, created = await asyncio.to_thread(db.begin_mission, owner_id, request)
    except ValueError:
        raise HTTPException(409, "同じ依頼キーが別の入力に使われています。")
    if not created:
        if mission.get("result"):
            return await hydrate(mission["result"])
        raise HTTPException(
            409,
            {
                "mission_id": mission["id"],
                "status": mission["status"],
                "message": "この依頼は実行中または終了済みです。二重実行はしません。",
            },
        )
    try:
        async with asyncio.timeout(240):
            result = await rpc("orchestrator", request.model_dump())
            result["timings"]["request_ms"] = round((time.monotonic() - started) * 1000)
            transient_places = result["places"]
            result["places"] = [{"place_id": p["place_id"]} for p in transient_places]
            saved = await asyncio.to_thread(db.finish_mission, mission["id"], result)
            response = deepcopy(saved)
            response["places"] = transient_places
            response["timings"]["request_ms"] = round(
                (time.monotonic() - started) * 1000
            )
            response["saved"] = False
            logger.info(
                "mission_completed id=%s elapsed_ms=%s",
                mission["id"],
                result["timings"]["request_ms"],
            )
            return response
    except TimeoutError:
        await asyncio.to_thread(db.fail_mission, mission["id"], "timeout")
        raise HTTPException(
            504, {"mission_id": mission["id"], "message": "処理期限を超えました。"}
        )
    except Exception:
        logger.exception("mission_failed id=%s", mission["id"])
        await asyncio.to_thread(db.fail_mission, mission["id"], "execution_failed")
        raise HTTPException(
            502,
            {
                "mission_id": mission["id"],
                "message": "分析に失敗しました。条件やAPI設定を確認してください。",
            },
        )
```

(Only the signature and the single `db.begin_mission` call changed — the rest of the function body is unchanged, shown in full so the task is self-contained.)

Replace the `GET /api/missions/{mission_id}` handler and add the new list endpoint right before it:

```python
@app.get("/api/missions")
async def list_missions_endpoint(x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    return {"missions": await asyncio.to_thread(db.list_missions, owner_id)}


@app.get("/api/missions/{mission_id}")
async def get_mission(mission_id: str, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    mission = await asyncio.to_thread(db.get_mission, owner_id, mission_id)
    if not mission:
        raise HTTPException(404, "依頼が見つかりません。")
    if not mission.get("result"):
        return {
            "mission_id": mission_id,
            "status": mission["status"],
            "error_code": mission.get("error_code"),
        }
    result = await hydrate(mission["result"])
    result["input"] = mission["input_snapshot"]
    result["saved"] = await asyncio.to_thread(db.is_itinerary_saved, mission_id)
    return result
```

**Important: the new `GET /api/missions` route must be registered before `GET /api/missions/{mission_id}`** in the file (as shown above) — FastAPI matches routes in registration order, and a literal `/api/missions` path registered after the `{mission_id}` path would never be reached (every request to it would instead match `{mission_id}="missions"`... actually the opposite problem applies here: register the static `/api/missions` path before the dynamic `/api/missions/{mission_id}` one, or a request to `GET /api/missions` would itself get captured by `{mission_id}`-shaped routes defined earlier for other paths; to avoid any ambiguity, always declare the no-parameter list route above the single-resource route in the same file).

Replace the `/save` handler:

```python
@app.post("/api/missions/{mission_id}/save")
async def save(mission_id: str, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    found = await asyncio.to_thread(db.save_itinerary, owner_id, mission_id)
    if not found:
        raise HTTPException(404)
    return {"mission_id": mission_id, "saved": True}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_mission_history_router.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd backend && uv run pytest -v`
Expected: PASS (every test in the backend suite)

- [ ] **Step 6: Commit**

```bash
git add backend/michibiki/michibiki/server.py backend/tests/test_mission_history_router.py
git commit -m "feat: add GET /api/profile and GET /api/missions, scope all mission/profile endpoints by client_hash"
```

---

### Task 3: Deploy-time data migration — ready-to-run script (not executed by this task)

**Files:**
- Create: `backend/scripts/migrate_demo_owner.py`

**Interfaces:**
- Consumes: `db.migrate_demo_owner_data(target_client_hash)` from Task 1.
- Produces: a standalone script a human runs once, manually, against the real deployed database — never imported by the application, never run as part of this plan's own test suite.

- [ ] **Step 1: Write the script**

```python
# backend/scripts/migrate_demo_owner.py
"""One-time, manually-run data migration: moves the DEMO_OWNER profile and
missions (created before per-client ownership existed) to a real client_hash.

Usage (from backend/, with the same environment variables the deployed
backend service uses — INSTANCE_CONNECTION_NAME/DB_USER/DB_NAME/DB_PASSWORD,
or DATABASE_URL for a local database):

    uv run python scripts/migrate_demo_owner.py <target_client_hash>

This script is NOT called from migrate(), NOT called from any endpoint, and
NOT part of the automated test suite — it is meant to be run exactly once,
by a human, against the real database, after deploying the code from this
plan's Tasks 1-2.
"""
import sys

from michibiki import db


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/migrate_demo_owner.py <target_client_hash>")
        sys.exit(1)
    target_client_hash = sys.argv[1]
    db.migrate_demo_owner_data(target_client_hash)
    print(f"Migrated DEMO_OWNER data to client_hash={target_client_hash}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Confirm the script imports cleanly**

Run: `cd backend && uv run python -c "import scripts.migrate_demo_owner"` — if this fails because `scripts/` isn't a package, instead run: `cd backend && uv run python scripts/migrate_demo_owner.py` (with no arguments) and confirm it prints the usage message and exits with status 1, rather than raising an `ImportError`.
Expected: usage message printed, exit code 1 (no arguments given) — confirms the script's own code loads and runs without a real database connection being required for this check.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/migrate_demo_owner.py
git commit -m "chore: add deploy-time script to migrate DEMO_OWNER data to a real client_hash"
```

**Note for whoever deploys this:** do not run this script until Tasks 1-2 are deployed to the target environment. Running it against the currently-deployed (pre-this-plan) backend code would move the data, but the still-old server code would keep reading/writing `DEMO_OWNER` until the new code is also deployed — run the migration script only after confirming the new backend image is live.
