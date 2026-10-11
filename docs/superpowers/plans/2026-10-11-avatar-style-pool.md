# アバター生成: スタイルプール化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-style, user-chosen avatar generation with a system that randomly picks 10 unused YouCam styles per generation, accumulates them into a per-client pool, lets the user pick any pool avatar as their profile icon at any time, and lets trip creation draw a fresh random 10 from the whole pool each time.

**Architecture:** persona-agent-backend gains two new, still-stateless batch endpoints (`POST /avatar-jobs-batch`, `POST /avatar-results-batch`) that submit/collect N independent single-style YouCam tasks instead of one multi-output task. backend/michibiki owns all new state (`avatar_pool` table, used-style tracking, version/v2 wraparound, `profiles.avatar_object_name`) and does the random style selection itself before calling persona-agent-backend. The frontend drops its style picker and adds a pool grid for profile-avatar selection, plus a client-side random draw for trip-companion avatars.

**Tech Stack:** FastAPI/Python (both backend services, existing), React (frontend, existing), SQLAlchemy/Postgres (backend/michibiki).

**Spec:** `docs/superpowers/specs/2026-10-11-avatar-style-pool-design.md`

## Global Constraints

- persona-agent-backend stays stateless — it never decides which styles to use or tracks anything across requests; it only executes the exact `template_id` list it's given.
- A generation batch must still work even if some of the 10 YouCam tasks fail — partial success (fewer than 10 avatars) is acceptable; the spec explicitly allows this.
- The style-usage/version/wraparound logic (used styles, "<10 unused → delete + version+1") lives entirely in backend/michibiki, never in persona-agent-backend.
- YouCam concurrency is capped at 3 simultaneous task submissions per batch (spec's own conservative default, unverified against the real API — note this, don't remove the cap without re-verifying).
- Deviation from the spec, decided while writing this plan: `avatar_sets` needs a `version` column (the spec's table definition omitted it) — without it, there's no safe way to know which pool version a still-generating batch's results belong to once they arrive. Added as `Column("version", Integer, nullable=False)`.
- Deviation from the spec, decided while writing this plan: mouth-open (lip-sync) variant regeneration on avatar selection is explicitly OUT OF SCOPE for this plan — the spec mentions it as a design intent, but implementing it requires a new persona-agent-backend endpoint this plan doesn't otherwise need, and no existing code path currently reads a mouth-open image for anything the rest of this plan touches. `PUT /api/profile/avatar` only updates which avatar is selected; it does not generate or clear any mouth-open image. This is a deliberate scope cut, not an oversight — flag it to the user as a follow-up.

## Review Focus

- A client with zero avatars generated yet calling `GET /api/avatars/pool` or the trip-creation random draw — must get an empty list / fall back to static portraits, not a 404 or crash.
- A client whose unused-style count is exactly 10 (the boundary, not "<10") — must NOT trigger the version wraparound; only `<10` wraps, per the spec's own wording.
- `PUT /api/profile/avatar` with an `object_name` that belongs to a DIFFERENT client — must 404, not silently select another client's private avatar as this caller's profile icon.
- A generation batch where YouCam returns success for a template but `download_avatar`/`Image.verify()` then fails on the actual image bytes (corrupt download) — must be treated as a failed avatar for that one style, not crash the whole batch collection.
- Re-running `GET /api/avatars/{set_id}` after a batch has already reached `"ready"` (e.g. the frontend polls once more after success) — must not re-insert duplicate `avatar_pool` rows for the same batch.

---

### Task 1: persona-agent-backend — batch YouCam submission

**Files:**
- Modify: `persona-agent-backend/avatar_api.py`
- Test: `persona-agent-backend/tests/test_avatar_api.py` (new file — no test currently exercises `avatar_api.py`'s FastAPI routes directly)

**Interfaces:**
- Produces: `POST /avatar-jobs-batch` (body: `{photo, consent, template_ids: [str, ...]}` → `{"tasks": [{"template_id": str, "task_id": str}, ...]}`).
- Consumes: `youcam_client.start_avatar_task(photo_bytes, content_type, template_id, output_count=1)` (existing, unchanged), `flatten_template_ids`/`load_avatar_template_catalog` (existing, unchanged).

- [ ] **Step 1: Write the failing test**

```python
# persona-agent-backend/tests/test_avatar_api.py
import base64
import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from main import app

client = TestClient(app)


def _fake_photo_b64():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@patch("avatar_api.capabilities", return_value={"avatar_configured": True, "avatar_count": 10, "voice_model": "x"})
@patch("avatar_api.start_avatar_task")
@patch("avatar_api.flatten_template_ids", return_value={"female_manga_mood", "male_cool_mood", "female_sport_mood"})
@patch("avatar_api.load_avatar_template_catalog", return_value={})
def test_avatar_jobs_batch_submits_one_task_per_template(
    mock_catalog, mock_flatten, mock_start, mock_caps,
):
    mock_start.side_effect = ["task-1", "task-2"]
    response = client.post("/avatar-jobs-batch", json={
        "photo": _fake_photo_b64(), "consent": True,
        "template_ids": ["female_manga_mood", "male_cool_mood"],
    })
    assert response.status_code == 200
    assert response.json() == {"tasks": [
        {"template_id": "female_manga_mood", "task_id": "task-1"},
        {"template_id": "male_cool_mood", "task_id": "task-2"},
    ]}
    assert mock_start.call_count == 2
    for call in mock_start.call_args_list:
        assert call.args[3] == 1  # output_count=1 per template


@patch("avatar_api.capabilities", return_value={"avatar_configured": True, "avatar_count": 10, "voice_model": "x"})
@patch("avatar_api.flatten_template_ids", return_value={"female_manga_mood"})
@patch("avatar_api.load_avatar_template_catalog", return_value={})
def test_avatar_jobs_batch_rejects_an_unknown_template_id(mock_catalog, mock_flatten, mock_caps):
    response = client.post("/avatar-jobs-batch", json={
        "photo": _fake_photo_b64(), "consent": True,
        "template_ids": ["female_manga_mood", "not-a-real-style"],
    })
    assert response.status_code == 400


def test_avatar_jobs_batch_rejects_missing_consent():
    response = client.post("/avatar-jobs-batch", json={
        "photo": _fake_photo_b64(), "consent": False, "template_ids": ["female_manga_mood"],
    })
    assert response.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd persona-agent-backend && python -m pytest tests/test_avatar_api.py -v`
Expected: FAIL — `404 Not Found` for `/avatar-jobs-batch` (route doesn't exist yet).

- [ ] **Step 3: Implement the endpoint**

In `persona-agent-backend/avatar_api.py`, add the import for the thread pool near the top (with the other stdlib imports):

```python
from concurrent.futures import ThreadPoolExecutor
```

Add this new Pydantic model right after the existing `AvatarPhoto` model:

```python
class AvatarBatchPhoto(BaseModel):
    photo: str = Field(max_length=9_000_000)
    template_ids: list[str] = Field(min_length=1, max_length=10)
    consent: bool
```

Add this function right after the existing `submit` function:

```python
def submit_batch(photo):
    if not photo.consent:
        raise HTTPException(400, "写真をYouCamへ送信することへの確認が必要です。")
    if not capabilities()["avatar_configured"]:
        raise HTTPException(503, "YouCamのAPIキー・シークレットが未設定です。")
    valid_ids = flatten_template_ids(load_avatar_template_catalog())
    for template_id in photo.template_ids:
        if template_id not in valid_ids:
            raise HTTPException(400, "スタイルを選び直してください。")
    try:
        raw = base64.b64decode(photo.photo, validate=True)
        if len(raw) > 6_000_000:
            raise ValueError("Photo too large")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("JPEG", "PNG") or max(image.size) > 4096:
                raise ValueError("Unsupported photo")
            mime = Image.MIME[image.format]
            image.verify()
    except Exception:
        raise HTTPException(400, "6MB以下・長辺4096px以下のJPEG/PNG写真を選んでください。")
    # Cap concurrency at 3 — YouCam's real limit is unverified; this is a
    # conservative default (see this plan's Global Constraints).
    with ThreadPoolExecutor(max_workers=3) as pool:
        task_ids = list(pool.map(
            lambda template_id: start_avatar_task(raw, mime, template_id, 1),
            photo.template_ids,
        ))
    return {"tasks": [
        {"template_id": template_id, "task_id": task_id}
        for template_id, task_id in zip(photo.template_ids, task_ids)
    ]}
```

Add this endpoint right after the existing `create_avatar_job` endpoint:

```python
@router.post("/avatar-jobs-batch")
async def create_avatar_job_batch(photo: AvatarBatchPhoto):
    try:
        return await asyncio.to_thread(submit_batch, photo)
    except HTTPException:
        raise
    except Exception:
        logger.warning("YouCam batch submission failed", exc_info=False)
        raise HTTPException(502, "YouCamへの画像生成依頼に失敗しました。")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd persona-agent-backend && python -m pytest tests/test_avatar_api.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full persona-agent-backend suite to check for regressions**

Run: `cd persona-agent-backend && python -m pytest -q`
Expected: PASS (every existing test, unchanged)

- [ ] **Step 6: Commit**

```bash
git add persona-agent-backend/avatar_api.py persona-agent-backend/tests/test_avatar_api.py
git commit -m "feat: add batch YouCam job submission (one task per style)"
```

---

### Task 2: persona-agent-backend — batch result collection

**Files:**
- Modify: `persona-agent-backend/avatar_api.py`
- Test: `persona-agent-backend/tests/test_avatar_api.py`

**Interfaces:**
- Produces: `POST /avatar-results-batch` (body: `{tasks: [{template_id, task_id}, ...], set_id}` → `{"status": "generating" | "failed" | "ready", "avatars"?: [{"template_id", "object_name", "mime_type"}, ...]}`).
- Consumes: `youcam_client.avatar_task_status`, `download_avatar` (existing, unchanged).

- [ ] **Step 1: Write the failing tests**

```python
# Append to persona-agent-backend/tests/test_avatar_api.py

@patch("avatar_api.download_avatar", return_value=(b"fake-bytes", "image/jpeg"))
@patch("avatar_api.avatar_task_status")
@patch("avatar_api.storage.Client")
def test_avatar_results_batch_returns_generating_when_any_task_is_pending(
    mock_storage_client, mock_status, mock_download, monkeypatch,
):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    mock_status.side_effect = [("success", [{"url": "https://example.com/a.jpg"}]), ("running", [])]
    response = client.post("/avatar-results-batch", json={
        "tasks": [
            {"template_id": "female_manga_mood", "task_id": "task-1"},
            {"template_id": "male_cool_mood", "task_id": "task-2"},
        ],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    assert response.json() == {"status": "generating"}


@patch("avatar_api.download_avatar")
@patch("avatar_api.avatar_task_status")
@patch("avatar_api.storage.Client")
def test_avatar_results_batch_skips_a_failed_template_and_returns_the_rest(
    mock_storage_client, mock_status, mock_download, monkeypatch,
):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    mock_status.side_effect = [("error", []), ("success", [{"url": "https://example.com/b.jpg"}])]
    mock_download.return_value = (_fake_photo_bytes(), "image/png")
    response = client.post("/avatar-results-batch", json={
        "tasks": [
            {"template_id": "female_manga_mood", "task_id": "task-1"},
            {"template_id": "male_cool_mood", "task_id": "task-2"},
        ],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert len(body["avatars"]) == 1
    assert body["avatars"][0]["template_id"] == "male_cool_mood"


def _fake_photo_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    return buf.getvalue()


@patch("avatar_api.download_avatar", return_value=(b"not-a-real-image", "image/jpeg"))
@patch("avatar_api.avatar_task_status", return_value=("success", [{"url": "https://example.com/c.jpg"}]))
@patch("avatar_api.storage.Client")
def test_avatar_results_batch_skips_a_template_whose_download_is_corrupt(
    mock_storage_client, mock_status, mock_download, monkeypatch,
):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    response = client.post("/avatar-results-batch", json={
        "tasks": [{"template_id": "female_manga_mood", "task_id": "task-1"}],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    assert response.json() == {"status": "failed"}  # the one template failed verify(), nothing ready


@patch("avatar_api.avatar_task_status", return_value=("error", []))
def test_avatar_results_batch_returns_failed_when_every_task_failed(mock_status, monkeypatch):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    response = client.post("/avatar-results-batch", json={
        "tasks": [{"template_id": "female_manga_mood", "task_id": "task-1"}],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    assert response.json() == {"status": "failed"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd persona-agent-backend && python -m pytest tests/test_avatar_api.py -v -k batch`
Expected: FAIL — `404 Not Found` for `/avatar-results-batch`.

- [ ] **Step 3: Implement the endpoint**

Add this Pydantic model right after `AvatarBatchPhoto`:

```python
class AvatarBatchTask(BaseModel):
    template_id: str
    task_id: str


class AvatarBatchResult(BaseModel):
    tasks: list[AvatarBatchTask]
    set_id: UUID
```

Add this function right after the existing `collect` function:

```python
def collect_batch(request):
    bucket = storage.Client().bucket(os.environ["AVATAR_BUCKET"])
    ready = []
    pending = False
    for task in request.tasks:
        status, outputs = avatar_task_status(task.task_id)
        if status == "error" or not outputs:
            continue
        if status != "success":
            pending = True
            continue
        try:
            raw, mime = download_avatar(outputs[0]["url"])
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
        except Exception:
            logger.warning("Skipping one corrupt avatar download for template_id=%s", task.template_id)
            continue
        object_name = f"avatars/{request.set_id}/{task.template_id}"
        blob = bucket.blob(object_name)
        blob.cache_control = "private, max-age=3600"
        blob.upload_from_string(raw, content_type=mime)
        ready.append({"template_id": task.template_id, "object_name": object_name, "mime_type": mime})
    if pending:
        return {"status": "generating"}
    if not ready:
        return {"status": "failed"}
    return {"status": "ready", "avatars": ready}
```

Add this endpoint right after the existing `avatar_result` endpoint:

```python
@router.post("/avatar-results-batch")
async def avatar_result_batch(request: AvatarBatchResult):
    try:
        return await asyncio.to_thread(collect_batch, request)
    except Exception as exc:
        logger.warning("Avatar batch collection failed error_type=%s", type(exc).__name__, exc_info=False)
        raise HTTPException(502, "生成画像を取得・保存できませんでした。再確認してください。")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd persona-agent-backend && python -m pytest tests/test_avatar_api.py -v`
Expected: PASS (7 tests total in the file)

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `cd persona-agent-backend && python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add persona-agent-backend/avatar_api.py persona-agent-backend/tests/test_avatar_api.py
git commit -m "feat: add batch YouCam result collection (partial success allowed)"
```

---

### Task 3: backend/michibiki — avatar_pool table and CRUD

**Files:**
- Modify: `backend/michibiki/michibiki/db.py`
- Test: `backend/tests/test_contracts_db.py`

**Interfaces:**
- Produces: `db.avatar_pool` (Table), `db.get_current_avatar_version(client_hash) -> int`, `db.get_used_template_ids(client_hash, version) -> set[str]`, `db.add_avatar_pool_entries(client_hash, version, entries: list[dict]) -> None`, `db.get_avatar_pool(client_hash, version=None) -> list[dict]`, `db.delete_avatar_pool_version(client_hash, version) -> None`, `db.set_profile_avatar(owner_id, object_name) -> None`, `db.get_profile_avatar(owner_id) -> str | None`. Modifies `db.avatar_sets` (adds `version` column, replaces `provider_task_id` with `provider_task_ids`, drops `assets`), `db.create_avatar_set(client_hash, provider_task_ids, version)`, `db.update_avatar_set(set_id, status)`. Modifies `db.profiles` (adds `avatar_object_name` column).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_contracts_db.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_contracts_db.py -v -k avatar`
Expected: FAIL — `AttributeError: module 'michibiki.db' has no attribute 'get_current_avatar_version'`.

- [ ] **Step 3: Implement the schema and functions**

Add `delete` to the existing `from sqlalchemy import (...)` block if not already imported (it already was, from an earlier task on this branch — verify before adding a duplicate).

Replace the existing `avatar_sets` table definition:

```python
avatar_sets = Table(
    "avatar_sets", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("provider_task_ids", json_type, nullable=False),
    Column("status", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

Add the new `avatar_pool` table right after it:

```python
avatar_pool = Table(
    "avatar_pool", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("template_id", String, nullable=False),
    Column("object_name", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

Find the existing `profiles` table definition and add the new column:

```python
profiles = Table(
    "profiles",
    metadata,
    Column("owner_id", String, primary_key=True),
    Column("conditions", json_type, nullable=False),
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("avatar_object_name", String),
)
```

In `migrate()`, add a new version-5 branch. Find the existing version-4 branch (added by an earlier task on this branch) and add a sibling block right after it, inside the same `if conn.execute(... version == 1 ...).first():` section:

```python
            if not conn.execute(select(migrations.c.version).where(migrations.c.version == 5)).first():
                avatar_pool.create(conn, checkfirst=True)
                conn.execute(text("ALTER TABLE profiles ADD COLUMN avatar_object_name VARCHAR"))
                conn.execute(insert(migrations).values(version=5))
```

(`text` needs importing inside this function the same way the existing `pg_advisory_xact_lock` line already does — add `from sqlalchemy import text` right where that existing line already does it, reusing the same import statement if it's already there in that function body.)

In the fresh-database path (the `metadata.create_all(conn)` branch), add a version=5 insert after the existing version inserts:

```python
        conn.execute(insert(migrations).values(version=5))
```

Replace `create_avatar_set` and `update_avatar_set`:

```python
def create_avatar_set(client_hash, provider_task_ids, version):
    record = dict(id=str(uuid4()), client_hash=client_hash, provider_task_ids=provider_task_ids,
                  status="generating", version=version, created_at=now())
    with engine().begin() as conn:
        conn.execute(insert(avatar_sets).values(**record))
    return record


def update_avatar_set(set_id, status):
    with engine().begin() as conn:
        conn.execute(update(avatar_sets).where(avatar_sets.c.id == set_id).values(status=status))
```

`get_avatar_set` is unchanged (still `select(avatar_sets).where(id==..., client_hash==...)`), leave it as-is.

Add the new avatar_pool functions after `update_avatar_set`:

```python
def get_current_avatar_version(client_hash):
    with engine().connect() as conn:
        version = conn.execute(
            select(avatar_pool.c.version).where(avatar_pool.c.client_hash == client_hash)
            .order_by(avatar_pool.c.version.desc()).limit(1)
        ).scalar()
    return version or 1


def get_used_template_ids(client_hash, version):
    with engine().connect() as conn:
        rows = conn.execute(
            select(avatar_pool.c.template_id).where(
                avatar_pool.c.client_hash == client_hash, avatar_pool.c.version == version,
            )
        ).scalars().all()
    return set(rows)


def add_avatar_pool_entries(client_hash, version, entries):
    with engine().begin() as conn:
        for entry in entries:
            conn.execute(insert(avatar_pool).values(
                id=str(uuid4()), client_hash=client_hash, version=version,
                template_id=entry["template_id"], object_name=entry["object_name"], created_at=now(),
            ))


def get_avatar_pool(client_hash, version=None):
    version = version if version is not None else get_current_avatar_version(client_hash)
    with engine().connect() as conn:
        rows = conn.execute(
            select(avatar_pool).where(
                avatar_pool.c.client_hash == client_hash, avatar_pool.c.version == version,
            ).order_by(avatar_pool.c.created_at)
        ).mappings().all()
    return [dict(row) for row in rows]


def delete_avatar_pool_version(client_hash, version):
    with engine().begin() as conn:
        conn.execute(delete(avatar_pool).where(
            avatar_pool.c.client_hash == client_hash, avatar_pool.c.version == version,
        ))


def set_profile_avatar(owner_id, object_name):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    database = engine()
    upsert = pg_insert if database.dialect.name == "postgresql" else sqlite_insert
    statement = (
        upsert(profiles)
        .values(owner_id=owner_id, conditions={}, version=1, updated_at=now(), avatar_object_name=object_name)
        .on_conflict_do_update(
            index_elements=[profiles.c.owner_id],
            set_={"avatar_object_name": object_name, "updated_at": now()},
        )
    )
    with database.begin() as conn:
        conn.execute(statement)


def get_profile_avatar(owner_id):
    with engine().connect() as conn:
        return conn.execute(
            select(profiles.c.avatar_object_name).where(profiles.c.owner_id == owner_id)
        ).scalar()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_contracts_db.py -v`
Expected: PASS (every test in the file, old and new)

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd backend && uv run pytest -q`
Expected: PASS. If any existing test constructs an `avatar_sets` row or calls `create_avatar_set`/`update_avatar_set` with the old signature, update that call site to the new one shown above as part of this task (search for `create_avatar_set(` and `update_avatar_set(` across `backend/tests/` and `backend/michibiki/michibiki/media.py` — `media.py`'s own call sites are Task 4's job to update, but if any *test* directly calls these `db` functions with the old shape, fix it here).

- [ ] **Step 6: Commit**

```bash
git add backend/michibiki/michibiki/db.py backend/tests/test_contracts_db.py
git commit -m "feat: add avatar_pool table, versioned style tracking, profile avatar selection"
```

---

### Task 4: backend/michibiki — rewire the avatar endpoints

**Files:**
- Modify: `backend/michibiki/michibiki/media.py`
- Test: `backend/tests/test_media_avatars.py` (new file — mirrors the WS-relay test file's TestClient pattern already established in `test_media_converse.py` on this branch)

**Interfaces:**
- Consumes: every function from Task 3; `persona_rpc(path, body=None)` (existing, unchanged).
- Produces: `POST /api/avatars` (body `{photo, consent}`, no `template_id`), `GET /api/avatars/{set_id}`, `GET /api/avatars/pool`, `PUT /api/profile/avatar` (body `{object_name}`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_media_avatars.py
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from michibiki import db
from michibiki.server import app
from sqlalchemy import create_engine
import pytest

client = TestClient(app)
HEADERS = {"X-Michibiki-Client": "a" * 40}


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    db.migrate(engine)
    yield engine
    engine.dispose()


def _catalog():
    return {"female": {"mood": [
        {"id": f"female_style_{i}", "title": f"Style {i}"} for i in range(12)
    ]}}


@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_picks_ten_unused_styles(mock_rpc, database):
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(10)]},
    ]
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["avatar_count"] == 10
    batch_call = mock_rpc.call_args_list[1]
    assert batch_call.args[0] == "/avatar-jobs-batch"
    chosen = batch_call.args[1]["template_ids"]
    assert len(chosen) == 10
    assert len(set(chosen)) == 10  # no duplicates
    assert all(t in {f"female_style_{i}" for i in range(12)} for t in chosen)


@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_avoids_already_used_styles_on_a_second_generation(mock_rpc, database):
    db.add_avatar_pool_entries("x" * 64, 1, [
        {"template_id": f"female_style_{i}", "object_name": f"avatars/prev/{i}"} for i in range(10)
    ])
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": "female_style_10", "task_id": "task-a"},
                   {"template_id": "female_style_11", "task_id": "task-b"}]},
    ]
    headers = {"X-Michibiki-Client": "x" * 40}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200
    chosen = mock_rpc.call_args_list[1].args[1]["template_ids"]
    assert set(chosen) <= {"female_style_10", "female_style_11"}  # only the 2 unused styles remain


@patch("michibiki.media.storage.Client")
@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_wraps_to_a_new_version_when_fewer_than_ten_styles_remain(
    mock_rpc, mock_storage, database,
):
    owner = "y" * 64
    db.add_avatar_pool_entries(owner, 1, [
        {"template_id": f"female_style_{i}", "object_name": f"avatars/prev/{i}"} for i in range(8)
    ])  # only 4 styles unused (12 total - 8 used) — below the 10 threshold
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(10)]},
    ]
    headers = {"X-Michibiki-Client": owner}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200
    assert db.get_avatar_pool(owner, 1) == []  # version 1 was deleted
    assert db.get_current_avatar_version(owner) == 2
    chosen = mock_rpc.call_args_list[1].args[1]["template_ids"]
    assert len(set(chosen)) == 10  # full 12-style catalog was available again


@patch("michibiki.media.storage.Client")
@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_does_not_wrap_when_exactly_ten_styles_remain(mock_rpc, database):
    # 12-style catalog, 2 already used → exactly 10 unused remain. The spec's
    # wraparound only triggers on FEWER than 10, so this must NOT delete the pool.
    owner = "u" * 64
    db.add_avatar_pool_entries(owner, 1, [
        {"template_id": "female_style_0", "object_name": "avatars/prev/0"},
        {"template_id": "female_style_1", "object_name": "avatars/prev/1"},
    ])
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(2, 12)]},
    ]
    headers = {"X-Michibiki-Client": owner}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200
    assert db.get_current_avatar_version(owner) == 1  # did not wrap
    assert len(db.get_avatar_pool(owner, 1)) == 2  # old entries preserved, not deleted
    chosen = mock_rpc.call_args_list[1].args[1]["template_ids"]
    assert set(chosen) == {f"female_style_{i}" for i in range(2, 12)}


@patch("michibiki.media.storage.Client")
def test_pool_endpoint_returns_signed_urls_and_selected_avatar(mock_storage, database):
    owner = "z" * 64
    db.add_avatar_pool_entries(owner, 1, [{"template_id": "female_style_0", "object_name": "avatars/a/0"}])
    db.set_profile_avatar(owner, "avatars/a/0")
    mock_bucket = mock_storage.return_value.bucket.return_value
    mock_bucket.blob.return_value.generate_signed_url.return_value = "https://signed.example/a0"
    with patch("michibiki.media.google.auth.default", return_value=(None, None)):
        response = client.get("/api/avatars/pool", headers={"X-Michibiki-Client": owner})
    assert response.status_code == 200
    body = response.json()
    assert body["avatars"][0]["url"] == "https://signed.example/a0"
    assert body["selected"] == "avatars/a/0"


def test_select_avatar_rejects_an_object_name_not_in_the_callers_pool(database):
    owner = "w" * 64
    db.add_avatar_pool_entries(owner, 1, [{"template_id": "female_style_0", "object_name": "avatars/a/0"}])
    response = client.put("/api/profile/avatar", json={"object_name": "avatars/someone-else/9"},
                          headers={"X-Michibiki-Client": owner})
    assert response.status_code == 404


def test_select_avatar_accepts_an_object_name_in_the_callers_pool(database):
    owner = "v" * 64
    db.add_avatar_pool_entries(owner, 1, [{"template_id": "female_style_0", "object_name": "avatars/a/0"}])
    response = client.put("/api/profile/avatar", json={"object_name": "avatars/a/0"},
                          headers={"X-Michibiki-Client": owner})
    assert response.status_code == 200
    assert db.get_profile_avatar(owner) == "avatars/a/0"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_media_avatars.py -v`
Expected: FAIL — the existing `POST /api/avatars` still expects a `template_id` field and calls the old single-task flow; `/api/avatars/pool` and `PUT /api/profile/avatar` don't exist (404/422).

- [ ] **Step 3: Implement the changes in `media.py`**

Add `random` to the top-level imports.

Replace the `AvatarPhoto` model:

```python
class AvatarPhoto(BaseModel):
    photo: str = Field(max_length=9_000_000)
    consent: bool
```

Replace the `create` endpoint:

```python
@router.post("/avatars")
async def create(photo: AvatarPhoto, x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    catalog = await persona_rpc("/avatar-templates")
    all_ids = {t["id"] for categories in catalog.values() for templates in categories.values() for t in templates}
    version = await asyncio.to_thread(db.get_current_avatar_version, owner)
    used = await asyncio.to_thread(db.get_used_template_ids, owner, version)
    unused = list(all_ids - used)
    if len(unused) < 10:
        old_pool = await asyncio.to_thread(db.get_avatar_pool, owner, version)
        if old_pool:
            bucket = storage.Client().bucket(os.environ["AVATAR_BUCKET"])
            for entry in old_pool:
                bucket.blob(entry["object_name"]).delete()
            await asyncio.to_thread(db.delete_avatar_pool_version, owner, version)
        version += 1
        unused = list(all_ids)
    chosen = random.sample(unused, min(10, len(unused)))
    result = await persona_rpc("/avatar-jobs-batch", {
        "photo": photo.photo, "consent": photo.consent, "template_ids": chosen,
    })
    record = await asyncio.to_thread(db.create_avatar_set, owner, result["tasks"], version)
    return {"id": record["id"], "status": record["status"], "avatar_count": len(chosen)}
```

(`min(10, len(unused))` guards the pathological case where the real catalog ever has fewer than 10 templates total — `random.sample` raises if asked for more items than exist.)

Replace `signed_assets` with `signed_pool_assets`:

```python
def signed_pool_assets(pool):
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    bucket = storage.Client(credentials=credentials).bucket(os.environ["AVATAR_BUCKET"])
    def sign(name):
        return bucket.blob(name).generate_signed_url(
            version="v4", expiration=timedelta(hours=1), method="GET",
            service_account_email=os.environ["AVATAR_SIGNER"], access_token=credentials.token,
        )
    return {"status": "ready",
            "avatars": [{"object_name": a["object_name"], "template_id": a["template_id"], "url": sign(a["object_name"])}
                       for a in pool],
            "expires_in": 3600}
```

Replace the `get` endpoint (`GET /avatars/{set_id}`):

```python
@router.get("/avatars/{set_id}")
async def get(set_id: str, x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    record = await asyncio.to_thread(db.get_avatar_set, set_id, owner)
    if not record:
        raise HTTPException(404, "このブラウザの画像セットが見つかりません。")
    if record["status"] == "generating":
        result = await persona_rpc("/avatar-results-batch", {
            "tasks": record["provider_task_ids"], "set_id": set_id,
        })
        if result["status"] == "ready":
            await asyncio.to_thread(db.add_avatar_pool_entries, owner, record["version"], [
                {"template_id": a["template_id"], "object_name": a["object_name"]} for a in result["avatars"]
            ])
            current_avatar = await asyncio.to_thread(db.get_profile_avatar, owner)
            if not current_avatar:
                await asyncio.to_thread(db.set_profile_avatar, owner, result["avatars"][0]["object_name"])
            await asyncio.to_thread(db.update_avatar_set, set_id, "ready")
            record["status"] = "ready"
        elif result["status"] == "failed":
            await asyncio.to_thread(db.update_avatar_set, set_id, "failed")
            record["status"] = "failed"
    if record["status"] == "ready":
        pool = await asyncio.to_thread(db.get_avatar_pool, owner, record["version"])
        return await asyncio.to_thread(signed_pool_assets, pool)
    return {"id": set_id, "status": record["status"]}
```

Add two new endpoints and a request model right after it:

```python
@router.get("/avatars/pool")
async def pool(x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    pool_rows = await asyncio.to_thread(db.get_avatar_pool, owner)
    selected = await asyncio.to_thread(db.get_profile_avatar, owner)
    signed = await asyncio.to_thread(signed_pool_assets, pool_rows)
    signed["selected"] = selected
    return signed


class AvatarSelection(BaseModel):
    object_name: str


@router.put("/profile/avatar")
async def select_avatar(selection: AvatarSelection, x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    pool_rows = await asyncio.to_thread(db.get_avatar_pool, owner)
    if not any(row["object_name"] == selection.object_name for row in pool_rows):
        raise HTTPException(404, "指定されたアバターが見つかりません。")
    await asyncio.to_thread(db.set_profile_avatar, owner, selection.object_name)
    return {"status": "ok"}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_media_avatars.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd backend && uv run pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/michibiki/michibiki/media.py backend/tests/test_media_avatars.py
git commit -m "feat: rewire avatar endpoints for random style pooling and profile selection"
```

---

### Task 5: Frontend — avatar setup UI without the style picker

**Files:**
- Modify: `frontend/src/AvatarSetup.jsx`

**Interfaces:**
- Consumes: `POST /api/avatars` (body `{photo, consent}`, no `template_id`), `GET /api/avatars/pool`, `PUT /api/profile/avatar` (all from Task 4).

No automated test — `frontend/` has no test runner (confirmed on this branch already). Verified by `npm run build` plus reading the real code paths.

- [ ] **Step 1: Replace `AvatarSetup.jsx`'s contents**

```jsx
import { useEffect, useState } from 'react'
import { api } from './api'
import './avatar-setup.css'

// Refresh expiring URLs; the database stores object names, never signed URLs.
export function useAvatarSet(profile, setProfile) {
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const id = profile.avatarSetId
  useEffect(() => {
    if (!id) { setStatus(''); return }
    let active = true, timer
    const refresh = async () => {
      try {
        const data = await api(`/api/avatars/${encodeURIComponent(id)}`)
        if (!active) return
        setStatus(data.status); setError('')
        if (data.status === 'ready') timer = setTimeout(refresh, 50 * 60 * 1000)
        else if (data.status === 'generating') timer = setTimeout(refresh, 5000)
        else setError('画像生成に失敗しました。写真を選び直してください。')
      } catch (err) {
        if (active) { setError(err.message); timer = setTimeout(refresh, 15000) }
      }
    }
    refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [id, setProfile])
  return { status, error }
}

export function usePool(refreshKey) {
  const [pool, setPool] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api('/api/avatars/pool').then(data => active && setPool(data)).catch(err => active && setError(err.message))
    return () => { active = false }
  }, [refreshKey])
  return { pool, error, reload: () => setPool(null) }
}

export default function AvatarSetup({ profile, setProfile, mediaState }) {
  const [photo, setPhoto] = useState(null)
  const [consent, setConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [configured, setConfigured] = useState(null)
  const [poolVersion, setPoolVersion] = useState(0)
  const { pool, reload } = usePool(`${poolVersion}-${mediaState.status}`)
  useEffect(() => {
    let active = true
    api('/api/persona/capabilities').then(caps => active && setConfigured(caps.avatar_configured))
      .catch(err => active && setError(err.message))
    return () => { active = false }
  }, [])
  const generating = submitting || mediaState.status === 'generating'
  const create = async () => {
    if (!photo || !consent || generating) return
    if (photo.size > 6_000_000) { setError('6MB以下のJPEG/PNG写真を選んでください。'); return }
    setSubmitting(true); setError('')
    try {
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(',')[1])
        reader.onerror = reject
        reader.readAsDataURL(photo)
      })
      const job = await api('/api/avatars', { method: 'POST', body: { photo: encoded, consent } })
      setProfile(current => {
        const next = { ...current, avatarSetId: job.id }
        localStorage.setItem('michibiki-profile', JSON.stringify(next))
        return next
      })
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }
  const selectAvatar = async objectName => {
    try {
      await api('/api/profile/avatar', { method: 'PUT', body: { object_name: objectName } })
      setPoolVersion(v => v + 1)
      reload()
    } catch (err) { setError(err.message) }
  }
  return <section className="avatar-setup"><h3>ひとりのあなたから、探検隊を。</h3><p>あなたの写真から、ランダムなスタイルで旅の相棒のアイコンを作ります。生成するたびに新しいスタイルが追加されます。</p>
    <label className="avatar-file"><span>あなたの写真</span><span className="avatar-upload"><span aria-hidden="true">＋</span>{photo ? '写真を選び直す' : '写真を選ぶ'}<input type="file" accept="image/jpeg,image/png" disabled={generating} onChange={event => { setPhoto(event.target.files?.[0] || null); setError('') }} /></span><small>{photo ? photo.name : 'JPEG・PNG / 6MBまで'}</small></label>
    <label className="avatar-consent"><input type="checkbox" checked={consent} disabled={generating} onChange={event => setConsent(event.target.checked)} /><span>この写真をYouCamへ送信してアバターを生成することに同意します。</span></label>
    <button type="button" className="journey-button" disabled={!photo || !consent || generating || configured !== true} onClick={create}>{generating ? '探検隊を準備しています…' : 'あなたの探検隊をつくる →'}</button>
    {configured === false && <div className="avatar-unavailable"><b>画像生成は準備中です</b><p>サービスの接続設定がまだ完了していません。今は表示中のアイコンで旅をつくれます。</p></div>}
    {generating && <p aria-live="polite">生成には数分かかります。生成依頼は保存されるので、再読み込みしても確認できます。</p>}
    {(error || mediaState.error) && <p className="avatar-warning" role="alert">{error || mediaState.error}</p>}
    {pool?.avatars?.length > 0 && <div className="avatar-roster"><b>生成済みのアバター(クリックでプロフィールに設定)</b><div>{pool.avatars.map(a => <button key={a.object_name} type="button" className={pool.selected === a.object_name ? 'selected' : ''} onClick={() => selectAvatar(a.object_name)}><img src={a.url} alt="" /></button>)}</div></div>}
    <details className="data-handling"><summary>写真とデータの扱い</summary><p>元の写真はアプリに保存せず、生成したアバターだけを非公開で保存します。ブラウザの保存データを消すと再表示できなくなる場合があります。</p></details>
  </section>
}
```

(`usePool`'s `refreshKey` re-fetches whenever `mediaState.status` changes — i.e. right after a generation finishes — or when `poolVersion` is bumped after selecting a new profile avatar.)

- [ ] **Step 2: Update `avatar-setup.css` for the new clickable roster buttons**

Find the existing `.avatar-roster` rule (it currently styles plain `<img>` children). Read the real current rule in `frontend/src/avatar-setup.css` first, then add a sibling rule for the new `<button>` wrapper so the images stay visually identical but become clickable with a visible "selected" state:

```css
.avatar-roster button { border: 2px solid transparent; border-radius: 8px; padding: 0; background: none; cursor: pointer; }
.avatar-roster button.selected { border-color: #4b79a9; }
.avatar-roster button img { display: block; }
```

- [ ] **Step 3: Update `main.jsx`'s use of `profile.avatar`/`profile.twinAvatars`**

`profile.avatar` and `profile.twinAvatars` no longer exist — the old `useAvatarSet` set both from the single most recent generation; the new one doesn't (profile avatar is now `db.get_profile_avatar`-backed, not client-cached). Read `frontend/src/main.jsx` for every place it reads `profile.avatar` (the nav bar's `<img src={profile.avatar}>`, the `<Profile>` page's photo preview) and replace those reads with a small local fetch instead: add a `profileAvatarUrl` piece of state in the top-level `App` component, populated via `api('/api/avatars/pool').then(data => setProfileAvatarUrl(data.avatars.find(a => a.object_name === data.selected)?.url))`, refreshed whenever `mediaState.status` becomes `'ready'` or right after `AvatarSetup`'s `selectAvatar` runs (thread a `setProfileAvatarUrl` callback prop down, or simply re-fetch on an interval matching `useAvatarSet`'s own 50-minute signed-URL refresh cadence). Use `profileAvatarUrl || defaultAvatar` (the existing `defaultAvatar` constant already in `main.jsx`) everywhere `profile.avatar` was read, so a client with no avatars yet still sees the existing static fallback image.

- [ ] **Step 4: Run the build to verify no syntax/import errors**

Run: `cd frontend && npm run build`
Expected: builds successfully, no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/AvatarSetup.jsx frontend/src/avatar-setup.css frontend/src/main.jsx
git commit -m "feat: replace the style picker with a clickable generated-avatar pool"
```

---

### Task 6: Frontend — random trip-companion avatars from the pool

**Files:**
- Modify: `frontend/src/main.jsx`

**Interfaces:**
- Consumes: `GET /api/avatars/pool` (Task 4), `travelersFor(result, count, avatars)` (existing, unchanged signature — `avatars[i]` is just a URL string or `undefined`, per `avatar-fallback.js`'s existing `avatarFor(index, generated)`).

No automated test — same as Task 5, verified by `npm run build`.

- [ ] **Step 1: Add a shuffle helper and trip-avatar state**

In `frontend/src/main.jsx`, inside the top-level `App` function, find the line:

```js
const travelers = travelersFor(result, displayTrip.twin_count || 3, profile.twinAvatars)
```

Replace `profile.twinAvatars` with a new state variable `tripAvatars` (add the state declaration near the other `useState` calls in `App`):

```js
const [tripAvatars, setTripAvatars] = useState([])
```

```js
const travelers = travelersFor(result, displayTrip.twin_count || 3, tripAvatars)
```

- [ ] **Step 2: Draw 10 random pool avatars at dispatch time**

Find the `dispatch` function in `App` (the one that calls `POST /api/missions`). Add a random draw right before it starts the mission — read the real current `dispatch` body in `main.jsx` first to insert this correctly relative to its existing `inFlight`/`setLoading` lines, then add:

```js
try {
  const poolData = await api('/api/avatars/pool')
  const shuffled = [...poolData.avatars].sort(() => Math.random() - 0.5)
  setTripAvatars(shuffled.slice(0, 10).map(a => a.url))
} catch { setTripAvatars([]) }
```

placed before the existing `go('map')` call in `dispatch`, so the companions are picked once per trip and don't reshuffle on every re-render. On any failure (no avatars yet, network error), `tripAvatars` stays `[]` and `avatarFor`'s existing fallback to the static `portraits` array in `avatar-fallback.js` takes over — no crash.

- [ ] **Step 3: Run the build to verify no syntax/import errors**

Run: `cd frontend && npm run build`
Expected: builds successfully, no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.jsx
git commit -m "feat: draw trip-companion avatars randomly from the whole pool each trip"
```
