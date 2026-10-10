# michibiki 体験動画生成(Veo連携) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user turn one twin's experience report into a short Veo-generated video (avatar + destination, honoring their profile/feedback), reachable from the existing "story-video" placeholder in the michibiki frontend.

**Architecture:** A new, stateless `video-agent` Cloud Run service wraps the Veo API (mirrors `persona-agent-backend`'s shape: FastAPI, no DB access, IAM-only auth). `backend/michibiki` owns all persistence and the relevance guard; it calls `video-agent` synchronously both to start a job and to check its status on demand (pull, not push) — the same pattern `media.py` already uses for YouCam avatars via `persona_rpc`. The frontend polls a WebSocket that itself just relays whatever the DB currently says, so a dropped connection never loses the job.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend/michibiki, existing), Python/FastAPI (new video-agent, mirrors persona-agent-backend), `google-genai` for both Gemini (relevance guard) and Veo (`client.models.generate_videos`), React/Vite (existing frontend), Terraform (existing `infra/terraform/backend`).

**Spec:** `docs/superpowers/specs/2026-10-05-michibiki-video-generation-design.md`

## Global Constraints

- Veo video length/options are NOT guessed — Task 3 is a mandatory human-run smoke test against the real API before any polling/prompt code is written, per this team's established practice (see `persona-agent-backend/youcam_client.py`'s own module docstring for precedent).
- Feedback text max length: 500 characters, enforced on both frontend (`maxLength`) and backend (untrusted input, re-validated server-side).
- `consent: bool` is required on `POST /api/videos`; `false` → `400`. Same rationale as `persona-agent-backend/avatar_api.py`'s `AvatarPhoto.consent`.
- Only `domain == "mobility"` persona attributes may reach the Veo prompt — same rule as `persona-agent-backend/avatar_policy.py`'s `VISUALIZABLE_DOMAINS`.
- **Deviation from the spec, decided while writing this plan (see Task 5/Task 8 rationale):** `video-agent` does **not** run a background polling task and does **not** write to Cloud SQL. The spec's architecture diagram implied it would; that would require giving a new, otherwise-stateless service its own Cloud SQL Connector wiring, which nothing else in this codebase does for a generation-only service. Instead, `backend/michibiki`'s WebSocket handler polls `video-agent`'s status endpoint on demand (every tick) and writes the result to `video_jobs` itself — the exact pull pattern `media.py`'s existing `GET /api/avatars/{set_id}` already uses for YouCam. This keeps `video-agent` exactly as stateless as `persona-agent-backend`.
- `video_jobs.status` never contains `"rejected"` — a guard-rejected request is a synchronous `400` at `POST /api/videos` time and never creates a row (spec's own fix, carried into this plan).
- Videos are stored in the existing `{project}-michibiki-avatars` GCS bucket under a `videos/` prefix — no new bucket.

## Review Focus

- A `report_id` that belongs to a different `client_hash`, or doesn't exist at all — `POST /api/videos` must `404`/`403`, not leak another session's report text into a Veo prompt. (Task 7)
- Two tabs/double-clicks submitting the same `report_id` while a job is still running — must `409`, not spend two Veo calls. (Task 7)
- Feedback that's syntactically fine but describes a totally different place/activity than the report — the relevance guard must actually reject it, not just exist as dead code. (Task 6)
- Veo returning `done: true` with `error` set (not just the happy `result` path) — status must become `"failed"`, not silently hang as `"generating"` forever. (Task 4, Task 8)
- A WebSocket client reconnecting mid-job (closes tab, reopens) — must immediately see the job's current status, not a blank/initial state. (Task 8)

---

## File Structure

```
prototypes/michibiki/
  backend/michibiki/
    db.py           # MODIFY: add video_jobs table + CRUD
    video.py        # CREATE: relevance guard, POST /api/videos, WS progress, video_rpc helper
    server.py       # MODIFY: include video_router (1 line, like media_router)
  backend/tests/
    test_video_db.py       # CREATE
    test_video_guard.py    # CREATE
    test_video_router.py   # CREATE
  video-agent/              # CREATE (new service, sibling to persona-agent-backend)
    main.py
    veo_client.py
    prompts.py
    Dockerfile
    requirements.txt
    cloudbuild.yaml
    .env.example
    .dockerignore
    README.md
    tests/
      test_veo_client.py
      test_main.py
  infra/terraform/backend/
    video.tf        # CREATE: mirrors persona.tf
  frontend/src/
    main.jsx         # MODIFY: implement the existing story-video section
    video-request.css # CREATE: styles for the new form (mirrors avatar-setup.css conventions)
  frontend/tests/ (if a test runner exists; see Task 11 — verify before assuming)
```

---

### Task 1: `video_jobs` table and CRUD in `backend/michibiki/db.py`

**Files:**
- Modify: `backend/michibiki/michibiki/db.py`
- Test: `backend/tests/test_video_db.py`

**Interfaces:**
- Produces: `db.video_jobs` (Table), `db.create_video_job(client_hash, report_id, feedback, style, tone) -> dict`, `db.get_video_job(job_id, client_hash) -> dict | None`, `db.update_video_job(job_id, status, provider_operation_name=None, object_name=None) -> None`, `db.find_active_video_job(client_hash, report_id) -> dict | None` (returns a job with status in `queued`/`generating`/`rendering`, or `None`).

- [ ] **Step 1: Write the failing DB test**

```python
# backend/tests/test_video_db.py
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


def test_video_jobs_table_survives_a_fresh_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    db.migrate(engine)  # a brand-new DB must create version 3 directly, not just upgrade from 2
    record = db.create_video_job("hash-1", "report-1", "fb", "cinematic", "calm")
    assert record["status"] == "queued"
    engine.dispose()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_video_db.py -v`
Expected: FAIL — `AttributeError: module 'michibiki.db' has no attribute 'create_video_job'`

- [ ] **Step 3: Add the table, CRUD functions, and migration step**

In `backend/michibiki/michibiki/db.py`, add after the `consultations` table definition:

```python
video_jobs = Table(
    "video_jobs", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("report_id", String(36), ForeignKey("reports.id"), nullable=False),
    Column("feedback", String, nullable=False),
    Column("style", String, nullable=False),
    Column("tone", String, nullable=False),
    Column("provider_operation_name", String),
    Column("status", String, nullable=False),  # queued / generating / rendering / ready / failed
    Column("object_name", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
```

Add the CRUD functions after `update_avatar_set`:

```python
def create_video_job(client_hash, report_id, feedback, style, tone):
    record = dict(id=str(uuid4()), client_hash=client_hash, report_id=report_id,
                  feedback=feedback, style=style, tone=tone, status="queued", created_at=now())
    with engine().begin() as conn:
        conn.execute(insert(video_jobs).values(**record))
    return record


def get_video_job(job_id, client_hash):
    with engine().connect() as conn:
        record = conn.execute(select(video_jobs).where(
            video_jobs.c.id == job_id, video_jobs.c.client_hash == client_hash,
        )).mappings().first()
    return dict(record) if record else None


def update_video_job(job_id, status, provider_operation_name=None, object_name=None):
    values = {"status": status}
    if provider_operation_name is not None:
        values["provider_operation_name"] = provider_operation_name
    if object_name is not None:
        values["object_name"] = object_name
    with engine().begin() as conn:
        conn.execute(update(video_jobs).where(video_jobs.c.id == job_id).values(**values))


def find_active_video_job(client_hash, report_id):
    with engine().connect() as conn:
        record = conn.execute(select(video_jobs).where(
            video_jobs.c.client_hash == client_hash,
            video_jobs.c.report_id == report_id,
            video_jobs.c.status.in_(("queued", "generating", "rendering")),
        )).mappings().first()
    return dict(record) if record else None
```

Modify `migrate()` to add a version-3 branch. The existing function looks like this (shown for context — do not duplicate, extend it):

```python
def migrate(db=None):
    db = db or engine()
    with db.begin() as conn:
        if db.dialect.name == "postgresql":
            from sqlalchemy import text
            conn.execute(text("SELECT pg_advisory_xact_lock(73184261)"))
        migrations.create(conn, checkfirst=True)
        if conn.execute(select(migrations.c.version).where(migrations.c.version == 1)).first():
            if not conn.execute(select(migrations.c.version).where(migrations.c.version == 2)).first():
                avatar_sets.create(conn, checkfirst=True)
                consultations.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=2))
            if not conn.execute(select(migrations.c.version).where(migrations.c.version == 3)).first():
                video_jobs.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=3))
            return
        metadata.create_all(conn)
        conn.execute(insert(migrations).values(version=1))
        conn.execute(insert(migrations).values(version=2))
        conn.execute(insert(migrations).values(version=3))
```

(This adds one `if not version==3` branch for existing DBs, and extends the fresh-DB path to insert version 3 too — `metadata.create_all(conn)` already creates every table including the new `video_jobs` since it's registered on the same `metadata`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_video_db.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full existing test suite to check for regressions**

Run: `cd backend && uv run pytest tests/test_contracts_db.py -v`
Expected: PASS (unchanged — confirms the `migrate()` edit didn't break the existing version-1→2 path)

- [ ] **Step 6: Commit**

```bash
git add backend/michibiki/michibiki/db.py backend/tests/test_video_db.py
git commit -m "feat: add video_jobs table and CRUD (migration version 3)"
```

---

### Task 2: `video-agent` service scaffold

**Files:**
- Create: `video-agent/main.py`
- Create: `video-agent/requirements.txt`
- Create: `video-agent/Dockerfile`
- Create: `video-agent/.dockerignore`
- Create: `video-agent/cloudbuild.yaml`
- Create: `video-agent/.env.example`
- Create: `video-agent/README.md`
- Test: `video-agent/tests/test_main.py`

**Interfaces:**
- Produces: `app` (FastAPI instance) importable from `video-agent/main.py`, with `GET /health` returning `{"status": "ok"}`.

- [ ] **Step 1: Write the failing test**

```python
# video-agent/tests/test_main.py
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd video-agent && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL (`main.py` doesn't exist yet) — create `requirements.txt` first (next step) so the install succeeds, then rerun.

- [ ] **Step 3: Create `requirements.txt`**

```
fastapi==0.141.1
uvicorn[standard]==0.30.6
google-genai==2.23.0
pydantic==2.13.5
google-cloud-storage>=3,<4
```

(No `requests`/`cryptography` here — unlike `persona-agent-backend`, this service never talks to YouCam.)

- [ ] **Step 4: Create `main.py` with just the health endpoint**

```python
# video-agent/main.py
import logging

from fastapi import FastAPI

app = FastAPI(title="video-agent")
logger = logging.getLogger(__name__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd video-agent && .venv/bin/python -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 6: Create `Dockerfile`, `.dockerignore`, `cloudbuild.yaml`, `.env.example`, `README.md`**

`Dockerfile` (copy `persona-agent-backend/Dockerfile` exactly, same non-root pattern):

```dockerfile
# video-agent/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --system --create-home appuser && chown -R appuser:appuser /app
USER appuser
ENV PORT=8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
```

`.dockerignore`:

```
.venv
__pycache__
*.pyc
.pytest_cache
tests
```

`cloudbuild.yaml`:

```yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args: [build, --tag, '${_REGION}-docker.pkg.dev/$PROJECT_ID/michibiki/video:$BUILD_ID', .]
images:
  - '${_REGION}-docker.pkg.dev/$PROJECT_ID/michibiki/video:$BUILD_ID'
substitutions:
  _REGION: asia-northeast1
options:
  logging: CLOUD_LOGGING_ONLY
```

`.env.example`:

```
VERTEX_PROJECT_ID=
VERTEX_LOCATION=us-central1
AVATAR_BUCKET=
```

`README.md`:

```markdown
# video-agent

Stateless Cloud Run service wrapping the Veo API for michibiki's体験動画生成.
Never touches Cloud SQL — `backend/michibiki` owns all persistence and polls
this service's `/video-jobs/{operation_name}/status` on demand (see
`docs/superpowers/specs/2026-10-05-michibiki-video-generation-design.md`
and its implementation plan for why).

## Local run

\`\`\`sh
cp .env.example .env   # fill in VERTEX_PROJECT_ID
pip install -r requirements.txt
set -a; source .env; set +a
uvicorn main:app --reload --port 8080
\`\`\`
```

- [ ] **Step 7: Commit**

```bash
git add video-agent/
git commit -m "infra: scaffold video-agent service (health endpoint only)"
```

---

### Task 3: Human-run Veo API smoke test (no automated test — produces verified facts for Task 4)

**Files:** none (this task produces knowledge, written into Task 4's code comments)

- [ ] **Step 1: Confirm Veo model availability and name**

With real GCP credentials (`gcloud auth application-default login` already done per this project's existing avatar/voice work), run:

```python
import os
from google import genai

client = genai.Client(vertexai=True, project=os.environ["VERTEX_PROJECT_ID"], location="us-central1")
for m in client.models.list():
    if "veo" in m.name.lower():
        print(m.name)
```

Record the exact model name string returned (e.g. `"veo-3.0-generate-001"` — do not assume this value, use whatever the real call returns).

- [ ] **Step 2: Confirm `generate_videos` accepts an image + text prompt and returns a pollable operation**

```python
from google.genai import types

with open("some-test-avatar.png", "rb") as f:
    image_bytes = f.read()

operation = client.models.generate_videos(
    model="<model name from Step 1>",
    prompt="A person in a wheelchair arrives at a cafe entrance, calm afternoon light.",
    image=types.Image(image_bytes=image_bytes, mime_type="image/png"),
    config=types.GenerateVideosConfig(number_of_videos=1),
)
print(operation.name, operation.done)
```

Record: does this raise, or return immediately with `done=False`? What does `operation.name` look like?

- [ ] **Step 3: Confirm polling and the completed shape**

```python
import time

while not operation.done:
    time.sleep(10)
    operation = client.operations.get(operation)
print(operation.done, operation.error, operation.result)
```

Record: how long did this actually take (do not assume — write down the real elapsed time)? Does `operation.result.generated_videos[0].video` have `.uri` or `.video_bytes` populated when `output_gcs_uri` is NOT set in config? What's in `.mime_type`?

- [ ] **Step 4: Confirm the error shape**

Deliberately trigger a likely-filtered or invalid request (e.g. an empty/corrupt image, or a prompt likely to trip `person_generation` restrictions) and record what `operation.error` actually contains when `operation.done=True` but generation failed — this shape feeds directly into Task 4's `video_task_status()` error handling.

- [ ] **Step 5: Write the findings into this plan's Task 4, Step 3 code block**

Before starting Task 4, replace every `<VERIFIED: ...>` placeholder in Task 4's code with the real values found above. Do not proceed with a guessed value — if something from Steps 1-4 couldn't be confirmed, stop and ask a human before writing Task 4.

---

### Task 4: `video-agent/veo_client.py`

**Files:**
- Create: `video-agent/veo_client.py`
- Test: `video-agent/tests/test_veo_client.py`

**Interfaces:**
- Consumes: findings from Task 3.
- Produces: `start_video_task(image_bytes: bytes, image_mime_type: str, prompt: str) -> str` (returns the operation name), `video_task_status(operation_name: str) -> tuple[str, str | None, str | None]` (returns `(status, video_bytes_b64_or_none, video_mime_type_or_none)` where `status` is `"generating"`, `"ready"`, or `"failed"`).

- [ ] **Step 1: Write the failing tests**

```python
# video-agent/tests/test_veo_client.py
from unittest.mock import MagicMock, patch

import veo_client


@patch("veo_client._build_client")
def test_start_video_task_returns_operation_name(mock_build_client):
    fake_operation = MagicMock(name="operations/abc123")
    fake_operation.name = "operations/abc123"
    fake_client = MagicMock()
    fake_client.models.generate_videos.return_value = fake_operation
    mock_build_client.return_value = fake_client

    operation_name = veo_client.start_video_task(b"fake-image-bytes", "image/png", "a calm cafe scene")

    assert operation_name == "operations/abc123"
    call_kwargs = fake_client.models.generate_videos.call_args.kwargs
    assert call_kwargs["prompt"] == "a calm cafe scene"
    assert call_kwargs["image"].image_bytes == b"fake-image-bytes"
    assert call_kwargs["image"].mime_type == "image/png"


@patch("veo_client._build_client")
def test_video_task_status_still_generating(mock_build_client):
    fake_operation = MagicMock(done=False)
    fake_client = MagicMock()
    fake_client.operations.get.return_value = fake_operation
    mock_build_client.return_value = fake_client

    status, video_bytes, mime_type = veo_client.video_task_status("operations/abc123")

    assert status == "generating"
    assert video_bytes is None


@patch("veo_client._build_client")
def test_video_task_status_ready(mock_build_client):
    fake_video = MagicMock(video_bytes=b"fake-video-bytes", mime_type="video/mp4")
    fake_generated = MagicMock(video=fake_video)
    fake_result = MagicMock(generated_videos=[fake_generated])
    fake_operation = MagicMock(done=True, error=None, result=fake_result)
    fake_client = MagicMock()
    fake_client.operations.get.return_value = fake_operation
    mock_build_client.return_value = fake_client

    status, video_bytes, mime_type = veo_client.video_task_status("operations/abc123")

    assert status == "ready"
    assert video_bytes == b"fake-video-bytes"
    assert mime_type == "video/mp4"


@patch("veo_client._build_client")
def test_video_task_status_failed(mock_build_client):
    fake_operation = MagicMock(done=True, error={"message": "filtered"}, result=None)
    fake_client = MagicMock()
    fake_client.operations.get.return_value = fake_operation
    mock_build_client.return_value = fake_client

    status, video_bytes, mime_type = veo_client.video_task_status("operations/abc123")

    assert status == "failed"
    assert video_bytes is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd video-agent && .venv/bin/python -m pytest tests/test_veo_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'veo_client'`

- [ ] **Step 3: Write `veo_client.py`**

```python
# video-agent/veo_client.py
"""Thin wrapper around google-genai's Veo video generation. Model name and
response shapes below were verified against the real API on <date from
Task 3> — see this project's implementation plan, Task 3, for the exact
verification steps. Do not change the model name without re-verifying.
"""
import os

from google import genai
from google.genai import types

VEO_MODEL = "<VERIFIED: model name from Task 3, Step 1>"


def _build_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["VERTEX_PROJECT_ID"],
        location=os.environ.get("VERTEX_LOCATION", "us-central1"),
    )


def start_video_task(image_bytes: bytes, image_mime_type: str, prompt: str) -> str:
    """Starts a Veo generation and returns the long-running operation's name
    immediately — this call does not wait for completion."""
    client = _build_client()
    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        image=types.Image(image_bytes=image_bytes, mime_type=image_mime_type),
        config=types.GenerateVideosConfig(number_of_videos=1),
    )
    return operation.name


def video_task_status(operation_name: str) -> tuple[str, bytes | None, str | None]:
    """Polls the operation once (no internal sleep/retry — callers decide
    polling cadence). Returns (status, video_bytes, mime_type); the latter
    two are only non-None when status == "ready"."""
    client = _build_client()
    operation = client.operations.get(name=operation_name)
    if not operation.done:
        return "generating", None, None
    if operation.error:
        return "failed", None, None
    video = operation.result.generated_videos[0].video
    return "ready", video.video_bytes, video.mime_type
```

(If Task 3 found that `operations.get` takes a different argument shape than `name=operation_name` — e.g. the whole operation object — adjust this to match what was actually verified, not what's shown here.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd video-agent && .venv/bin/python -m pytest tests/test_veo_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add video-agent/veo_client.py video-agent/tests/test_veo_client.py
git commit -m "feat: add veo_client wrapping Veo generation and status polling"
```

---

### Task 5: `video-agent/main.py` — job endpoints

**Files:**
- Modify: `video-agent/main.py`
- Create: `video-agent/prompts.py`
- Test: `video-agent/tests/test_main.py` (extend)

**Interfaces:**
- Consumes: `veo_client.start_video_task`, `veo_client.video_task_status` (Task 4).
- Produces: `POST /video-jobs` (body: `{image_bytes_b64, image_mime_type, report_text, feedback, style, tone, mobility_notes}` → `{"operation_name": str}`), `GET /video-jobs/{operation_name}/status` (→ `{"status": str, "video_bytes_b64": str|None, "mime_type": str|None}`).

**Rationale for this task's shape (see Global Constraints):** no background task, no DB — `backend/michibiki` calls these two endpoints directly and owns the polling loop itself.

- [ ] **Step 1: Write `prompts.py` (prompt assembly, pure function, easy to unit test)**

```python
# video-agent/prompts.py
STYLE_LABELS = {"cinematic": "シネマティックな撮影スタイルで", "long_take": "ロングテイクの落ち着いた撮影で",
                "narrated": "ナレーション調の説明を添えて"}
TONE_LABELS = {"calm": "穏やかな雰囲気で", "dramatic": "ドラマチックな雰囲気で", "relaxed": "落ち着いた雰囲気で"}


def build_prompt(report_text, mobility_notes, style, tone, feedback):
    """mobility_notes must already be filtered to domain=="mobility" attributes
    only by the caller — this function does not filter anything itself."""
    parts = [report_text.strip()]
    if mobility_notes:
        parts.append(mobility_notes.strip())
    parts.append(STYLE_LABELS.get(style, ""))
    parts.append(TONE_LABELS.get(tone, ""))
    if feedback:
        parts.append(f"追加の要望: {feedback.strip()}")
    return "。".join(part for part in parts if part)
```

- [ ] **Step 2: Write the failing test for `build_prompt`**

```python
# video-agent/tests/test_prompts.py
from prompts import build_prompt


def test_build_prompt_includes_all_parts():
    prompt = build_prompt("入口は段差なし", "車いすで通りやすい", "cinematic", "calm", "もっと明るく")
    assert "入口は段差なし" in prompt
    assert "車いすで通りやすい" in prompt
    assert "シネマティック" in prompt
    assert "穏やか" in prompt
    assert "もっと明るく" in prompt


def test_build_prompt_omits_empty_feedback():
    prompt = build_prompt("report text", "", "cinematic", "calm", "")
    assert "追加の要望" not in prompt
```

- [ ] **Step 3: Run to verify it fails, then it passes**

Run: `cd video-agent && .venv/bin/python -m pytest tests/test_prompts.py -v`
First run expected: FAIL (`ModuleNotFoundError`) — but `prompts.py` was already written in Step 1, so this should actually PASS immediately. If it doesn't, fix `prompts.py` before moving on.

- [ ] **Step 4: Add the two endpoints to `main.py`**

```python
# video-agent/main.py (add to the existing file from Task 2)
import base64

from pydantic import BaseModel, Field

from prompts import build_prompt
from veo_client import start_video_task, video_task_status


class VideoJobRequest(BaseModel):
    image_bytes_b64: str = Field(max_length=9_000_000)
    image_mime_type: str
    report_text: str = Field(max_length=10_000)
    mobility_notes: str = Field(default="", max_length=2_000)
    feedback: str = Field(max_length=500)
    style: str
    tone: str


@app.post("/video-jobs")
async def create_video_job(request: VideoJobRequest) -> dict[str, str]:
    image_bytes = base64.b64decode(request.image_bytes_b64, validate=True)
    prompt = build_prompt(request.report_text, request.mobility_notes, request.style, request.tone, request.feedback)
    operation_name = start_video_task(image_bytes, request.image_mime_type, prompt)
    return {"operation_name": operation_name}


@app.get("/video-jobs/{operation_name:path}/status")
async def get_video_job_status(operation_name: str) -> dict:
    status, video_bytes, mime_type = video_task_status(operation_name)
    return {
        "status": status,
        "video_bytes_b64": base64.b64encode(video_bytes).decode("ascii") if video_bytes else None,
        "mime_type": mime_type,
    }
```

(`{operation_name:path}` because operation names from `google-genai` typically contain `/`, e.g. `operations/abc123` — a plain `{operation_name}` path param would not match that.)

- [ ] **Step 5: Write the failing tests for these endpoints**

```python
# video-agent/tests/test_main.py (add to the existing file from Task 2)
import base64
from unittest.mock import patch


def test_create_video_job_calls_start_video_task():
    with patch("main.start_video_task", return_value="operations/abc123") as mock_start:
        response = client.post("/video-jobs", json={
            "image_bytes_b64": base64.b64encode(b"fake-image").decode("ascii"),
            "image_mime_type": "image/png",
            "report_text": "入口は段差なし",
            "feedback": "もっと明るく",
            "style": "cinematic",
            "tone": "calm",
        })
    assert response.status_code == 200
    assert response.json() == {"operation_name": "operations/abc123"}
    mock_start.assert_called_once()
    assert mock_start.call_args.args[0] == b"fake-image"


def test_get_video_job_status_ready_returns_base64_video():
    with patch("main.video_task_status", return_value=("ready", b"fake-video-bytes", "video/mp4")):
        response = client.get("/video-jobs/operations%2Fabc123/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert base64.b64decode(body["video_bytes_b64"]) == b"fake-video-bytes"


def test_get_video_job_status_generating_returns_no_video():
    with patch("main.video_task_status", return_value=("generating", None, None)):
        response = client.get("/video-jobs/operations%2Fabc123/status")
    assert response.json() == {"status": "generating", "video_bytes_b64": None, "mime_type": None}
```

- [ ] **Step 6: Run to verify it fails, then implement until it passes**

Run: `cd video-agent && .venv/bin/python -m pytest tests/test_main.py -v`
Expected (before Step 4's code exists): FAIL with 404/405. After Step 4: PASS (5 tests total in this file).

- [ ] **Step 7: Commit**

```bash
git add video-agent/main.py video-agent/prompts.py video-agent/tests/
git commit -m "feat: add video-agent job start/status endpoints"
```

---

### Task 6: Relevance guard in `backend/michibiki/michibiki/video.py`

**Files:**
- Create: `backend/michibiki/michibiki/video.py`
- Test: `backend/tests/test_video_guard.py`

**Interfaces:**
- Produces: `check_relevance(report_text: str, feedback: str, genai_client) -> tuple[bool, str]` (returns `(on_topic, reason)`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_video_guard.py
import json
from unittest.mock import MagicMock

from michibiki.video import check_relevance


def test_check_relevance_on_topic():
    fake_response = MagicMock()
    fake_response.text = json.dumps({"on_topic": True, "reason": ""})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    on_topic, reason = check_relevance("入口は段差なし", "もっと穏やかな雰囲気で", fake_client)

    assert on_topic is True
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].response_mime_type == "application/json"


def test_check_relevance_off_topic():
    fake_response = MagicMock()
    fake_response.text = json.dumps({"on_topic": False, "reason": "体験談と無関係な話題です"})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    on_topic, reason = check_relevance("入口は段差なし", "全く違うアニメの話をしてください", fake_client)

    assert on_topic is False
    assert reason == "体験談と無関係な話題です"


def test_check_relevance_defaults_to_rejecting_on_malformed_response():
    """A malformed classifier response must fail closed (reject), not open
    (silently let an unvalidated feedback through to Veo)."""
    fake_response = MagicMock()
    fake_response.text = "not json at all"
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    on_topic, reason = check_relevance("入口は段差なし", "何か", fake_client)

    assert on_topic is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_video_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'michibiki.video'`

- [ ] **Step 3: Write `video.py`'s guard function**

```python
# backend/michibiki/michibiki/video.py
"""Video generation: relevance guard, job submission, and progress relay.
See docs/superpowers/specs/2026-10-05-michibiki-video-generation-design.md.
"""
import json
import logging

from google.genai import types

logger = logging.getLogger("michibiki")

RELEVANCE_PROMPT = """\
以下の体験談と、ユーザーが動画生成に追加したいフィードバックを比較してください。
フィードバックが体験談の対象(場所・状況)と無関係な話題を要求している場合は拒否してください。
雰囲気・トーン・強調したい点の指定は、体験談と関連していれば許可してください。

体験談:
{report_text}

フィードバック:
{feedback}

次のJSON形式で出力してください: {{"on_topic": boolean, "reason": "拒否する場合のみ日本語で理由"}}
"""


def check_relevance(report_text: str, feedback: str, genai_client) -> tuple[bool, str]:
    prompt = RELEVANCE_PROMPT.format(report_text=report_text, feedback=feedback)
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        parsed = json.loads(response.text)
        return bool(parsed["on_topic"]), parsed.get("reason", "")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("relevance guard returned a malformed response, rejecting: %s", e)
        return False, "フィードバックを確認できませんでした。もう一度お試しください。"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_video_guard.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/michibiki/michibiki/video.py backend/tests/test_video_guard.py
git commit -m "feat: add Gemini-based relevance guard for video feedback"
```

---

### Task 7: `POST /api/videos` router

**Files:**
- Modify: `backend/michibiki/michibiki/video.py`
- Test: `backend/tests/test_video_router.py`

**Interfaces:**
- Consumes: `db.create_video_job`, `db.find_active_video_job`, `db.get_video_job` (Task 1); `check_relevance` (Task 6); a new `video_rpc(path, body)` helper mirroring `media.py`'s `persona_rpc`.
- Produces: `router` (APIRouter, to be included in `server.py` in Task 9), `POST /api/videos`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_video_router.py
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from michibiki.server import app

client = TestClient(app)
HEADERS = {"X-Michibiki-Client": "a" * 40}


def _report_row():
    return {"id": "report-1", "body": {"experience": "入口は段差なし"}}


@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report")  # see Step 3 note: this function is new, added in this task
def test_create_video_job_success(mock_get_report, mock_find_active, mock_create, mock_guard, mock_rpc):
    mock_get_report.return_value = _report_row()
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"id": "job-1", "status": "queued"}
    mock_create.assert_called_once()


def test_create_video_job_rejects_missing_consent():
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "x", "style": "cinematic", "tone": "calm", "consent": False,
    }, headers=HEADERS)
    assert response.status_code == 400


@patch("michibiki.db.find_active_video_job", return_value={"id": "existing-job"})
@patch("michibiki.db.get_report", return_value=_report_row())
def test_create_video_job_rejects_duplicate_in_flight(mock_get_report, mock_find_active):
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "x", "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 409


@patch("michibiki.video.check_relevance", return_value=(False, "体験談と無関係です"))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report", return_value=_report_row())
def test_create_video_job_rejects_off_topic_feedback_without_creating_a_row(
    mock_get_report, mock_find_active, mock_create, mock_guard,
):
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "全く違う話題", "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 400
    assert "無関係" in response.json()["detail"]
    mock_create.assert_not_called()


def test_create_video_job_rejects_feedback_over_500_chars():
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "x" * 501, "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 422  # pydantic max_length violation


@patch("michibiki.db.get_report", return_value=None)
def test_create_video_job_404s_on_unknown_report(mock_get_report):
    response = client.post("/api/videos", json={
        "report_id": "does-not-exist", "feedback": "x", "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_video_router.py -v`
Expected: FAIL (`AttributeError: module 'michibiki.db' has no attribute 'get_report'`, and the router isn't included yet)

- [ ] **Step 3: Add `db.get_report` (a small addition Task 1 didn't need, but this task does)**

Add to `backend/michibiki/michibiki/db.py`:

```python
def get_report(report_id):
    with engine().connect() as conn:
        record = conn.execute(select(reports).where(reports.c.id == report_id)).mappings().first()
    return dict(record) if record else None
```

Add a unit test for it in `backend/tests/test_video_db.py`:

```python
def test_get_report_returns_none_for_unknown_id(database):
    assert db.get_report("does-not-exist") is None
```

Run: `cd backend && uv run pytest tests/test_video_db.py -v` — expect PASS (the happy path for `get_report` is already covered indirectly by Task 7's router tests via mocking; this unit test just pins the not-found case).

- [ ] **Step 4: Add `video_rpc`, the request model, and the endpoint to `video.py`**

```python
# backend/michibiki/michibiki/video.py (add to the file from Task 6)
import asyncio
import os

import httpx
from fastapi import APIRouter, Header, HTTPException
from google.auth.transport.requests import Request
from google.oauth2.id_token import fetch_id_token
from pydantic import BaseModel, Field

from . import db
from .media import client_hash  # reuse the existing hashing helper, do not duplicate it

router = APIRouter(prefix="/api")


async def video_rpc(path, body=None):
    url = os.environ.get("VIDEO_URL", "").rstrip("/")
    if not url:
        raise HTTPException(503, "動画生成APIはまだ設定されていません。")
    token = await asyncio.to_thread(fetch_id_token, Request(), url)
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.request("POST" if body is not None else "GET", url + path,
                                        json=body, headers={"Authorization": f"Bearer {token}"})
    if response.is_error:
        detail = response.json().get("detail", "動画生成APIに接続できませんでした。")
        raise HTTPException(response.status_code, detail if isinstance(detail, str) else "入力を確認してください。")
    return response.json()


class VideoRequest(BaseModel):
    report_id: str
    feedback: str = Field(max_length=500)
    style: str
    tone: str
    consent: bool


def _genai_client():
    from google import genai
    return genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"], location="global")


@router.post("/videos")
async def create_video_job(request: VideoRequest, x_michibiki_client: str = Header()):
    if not request.consent:
        raise HTTPException(400, "動画生成への同意が必要です。")
    owner = client_hash(x_michibiki_client)
    report = await asyncio.to_thread(db.get_report, request.report_id)
    if not report:
        raise HTTPException(404, "指定された体験談が見つかりません。")
    if await asyncio.to_thread(db.find_active_video_job, owner, request.report_id):
        raise HTTPException(409, "この体験談の動画はすでに生成中です。")
    on_topic, reason = await asyncio.to_thread(
        check_relevance, report["body"].get("experience", ""), request.feedback, _genai_client(),
    )
    if not on_topic:
        raise HTTPException(400, reason or "フィードバックが体験談と無関係と判定されました。")
    record = await asyncio.to_thread(
        db.create_video_job, owner, request.report_id, request.feedback, request.style, request.tone,
    )
    return {"id": record["id"], "status": record["status"]}
```

(`client_hash` is imported from `media.py` rather than redefined — it's a pure function, reusing it keeps the "same client token → same owner hash" guarantee consistent across both routers. If `media.py`'s `client_hash` isn't exported at module scope the way this import assumes, check its actual signature first — it was read directly from the file earlier in this project's research and takes a single token string and raises `HTTPException(400, ...)` on an invalid one.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_video_router.py -v`
Expected: PASS (6 tests) — note the router isn't included in `server.py` yet (that's Task 9), but `TestClient(app)` in this test file imports `michibiki.server.app` directly, so if Task 9 hasn't happened yet these will still fail with 404. **Do Task 9's one-line include before running this task's tests for real** (reorder if needed — Task 9 has no other dependencies and can move earlier).

- [ ] **Step 6: Commit**

```bash
git add backend/michibiki/michibiki/db.py backend/michibiki/michibiki/video.py backend/tests/
git commit -m "feat: add POST /api/videos with consent/ownership/idempotency/relevance checks"
```

---

### Task 8: `WS /api/video-jobs/{job_id}/progress`

**Files:**
- Modify: `backend/michibiki/michibiki/video.py`
- Test: `backend/tests/test_video_router.py` (extend)

**Interfaces:**
- Consumes: `db.get_video_job`, `db.update_video_job` (Task 1); `video_rpc` (Task 7).
- Produces: `WS /api/video-jobs/{job_id}/progress`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_video_router.py (add to the file from Task 7)
from unittest.mock import AsyncMock, patch


@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.db.get_video_job")
def test_progress_ws_sends_ready_status_and_closes(mock_get_job, mock_rpc):
    mock_get_job.return_value = {"id": "job-1", "client_hash": "x", "status": "generating",
                                 "provider_operation_name": "operations/abc123"}
    mock_rpc.return_value = {"status": "ready", "video_bytes_b64": "Zm9v", "mime_type": "video/mp4"}

    with patch("michibiki.video.client_hash", return_value="x"):
        with client.websocket_connect(
            "/api/video-jobs/job-1/progress", headers=HEADERS,
        ) as websocket:
            first = websocket.receive_json()
            assert first["type"] == "status"
            assert first["status"] == "generating"
            second = websocket.receive_json()
            assert second["type"] == "status"
            assert second["status"] == "ready"
            assert "video_url" in second


@patch("michibiki.db.get_video_job", return_value=None)
def test_progress_ws_closes_immediately_for_unknown_job(mock_get_job):
    with client.websocket_connect("/api/video-jobs/does-not-exist/progress", headers=HEADERS) as websocket:
        import pytest
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_video_router.py -k progress -v`
Expected: FAIL (no `/api/video-jobs/{job_id}/progress` route)

- [ ] **Step 3: Implement the WS endpoint**

```python
# backend/michibiki/michibiki/video.py (add to the file from Task 7)
import asyncio as _asyncio  # already imported above; this note is for the reader, not a real second import

from fastapi import WebSocket, WebSocketDisconnect
from google.cloud import storage
from google.auth.transport.requests import Request as GoogleAuthRequest
import base64
import google.auth


def _sign_video_url(object_name):
    from datetime import timedelta
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(GoogleAuthRequest())
    bucket = storage.Client(credentials=credentials).bucket(os.environ["AVATAR_BUCKET"])
    return bucket.blob(object_name).generate_signed_url(
        version="v4", expiration=timedelta(hours=1), method="GET",
        service_account_email=os.environ["AVATAR_SIGNER"], access_token=credentials.token,
    )


def _upload_video(object_name, video_bytes, mime_type):
    bucket = storage.Client().bucket(os.environ["AVATAR_BUCKET"])
    blob = bucket.blob(object_name)
    blob.cache_control = "private, max-age=3600"
    blob.upload_from_string(video_bytes, content_type=mime_type)


@router.websocket("/video-jobs/{job_id}/progress")
async def video_progress(websocket: WebSocket, job_id: str):
    client_token = websocket.headers.get("x-michibiki-client", "")
    try:
        owner = client_hash(client_token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            record = await asyncio.to_thread(db.get_video_job, job_id, owner)
            if not record:
                await websocket.close(code=1008)
                return
            if record["status"] in ("queued", "generating", "rendering") and record.get("provider_operation_name"):
                result = await video_rpc(f"/video-jobs/{record['provider_operation_name']}/status")
                if result["status"] == "ready":
                    object_name = f"videos/{job_id}"
                    video_bytes = base64.b64decode(result["video_bytes_b64"])
                    await asyncio.to_thread(_upload_video, object_name, video_bytes, result["mime_type"])
                    await asyncio.to_thread(db.update_video_job, job_id, "ready", object_name=object_name)
                    record["status"] = "ready"
                elif result["status"] == "failed":
                    await asyncio.to_thread(db.update_video_job, job_id, "failed")
                    record["status"] = "failed"
                elif record["status"] == "queued":
                    await asyncio.to_thread(db.update_video_job, job_id, "generating")
                    record["status"] = "generating"
            await websocket.send_json({"type": "status", "status": record["status"]})
            if record["status"] == "ready":
                video_url = await asyncio.to_thread(_sign_video_url, record["object_name"])
                await websocket.send_json({"type": "status", "status": "ready", "video_url": video_url, "expires_in": 3600})
                return
            if record["status"] == "failed":
                await websocket.send_json({"type": "status", "status": "failed",
                                           "message": "動画生成に失敗しました。もう一度お試しください。"})
                return
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `cd backend && uv run pytest tests/test_video_router.py -v`
Expected: PASS (8 tests total in this file)

- [ ] **Step 5: Commit**

```bash
git add backend/michibiki/michibiki/video.py backend/tests/test_video_router.py
git commit -m "feat: add WS progress relay for video jobs (polls video-agent on demand)"
```

---

### Task 9: Wire the router into `server.py`

**Files:**
- Modify: `backend/michibiki/michibiki/server.py`

**Interfaces:**
- Consumes: `video.router` (Task 6/7/8).

- [ ] **Step 1: Add the one-line include**

In `backend/michibiki/michibiki/server.py`, find:

```python
if ROLE == "backend":
    from .media import router as media_router
    app.include_router(media_router)
```

Change to:

```python
if ROLE == "backend":
    from .media import router as media_router
    from .video import router as video_router
    app.include_router(media_router)
    app.include_router(video_router)
```

- [ ] **Step 2: Run the full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: PASS — every test from Tasks 1, 6, 7, 8 plus the pre-existing `test_contracts_db.py`/`test_service_contracts.py` all green.

- [ ] **Step 3: Commit**

```bash
git add backend/michibiki/michibiki/server.py
git commit -m "feat: mount the video router on the backend service"
```

---

### Task 10: Terraform — `video-agent` Cloud Run service

**Files:**
- Create: `infra/terraform/backend/video.tf`
- Modify: `infra/terraform/backend/main.tf:276` (add `VIDEO_URL` env var, mirroring the existing `PERSONA_URL` line)

**Interfaces:**
- Produces: `google_cloud_run_v2_service.video`, `var.video_image`, `output.video_url`.

- [ ] **Step 1: Write `video.tf`, mirroring `persona.tf`'s shape exactly**

```hcl
# infra/terraform/backend/video.tf
variable "video_image" {
  type    = string
  default = ""
}

resource "google_service_account" "video" {
  account_id   = "michibiki-video"
  display_name = "michibiki video generation runtime"
}
resource "google_project_iam_member" "video_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.video.email}"
}
resource "google_cloud_run_v2_service" "video" {
  count               = var.video_image == "" ? 0 : 1
  name                = "michibiki-video-agent"
  location            = var.region
  deletion_protection = false
  scaling {
    min_instance_count    = 0
    manual_instance_count = 0
  }
  template {
    service_account                  = google_service_account.video.email
    timeout                          = "300s"
    max_instance_request_concurrency = 2
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.video_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "2", memory = "1Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = {
          VERTEX_PROJECT_ID = var.project_id
          VERTEX_LOCATION   = "us-central1"
        }
        content {
          name  = env.key
          value = env.value
        }
      }
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 5
        failure_threshold = 20
      }
    }
  }
  depends_on = [google_project_service.apis, google_project_iam_member.video_vertex]
}
resource "google_cloud_run_v2_service_iam_member" "video" {
  count    = var.video_image == "" ? 0 : 1
  name     = google_cloud_run_v2_service.video[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
output "video_url" {
  value = var.video_image == "" ? "" : google_cloud_run_v2_service.video[0].uri
}
```

(No `storage_bucket_iam_member` for `video` here — per the Global Constraints deviation, `video-agent` never touches GCS itself; `backend/michibiki`'s existing `avatar_writer`/`avatar_signer` grants already cover uploading/signing videos into the same bucket, since those are bucket-level, not prefix-level, IAM roles.)

- [ ] **Step 2: Add `VIDEO_URL` to the backend's own Cloud Run env vars**

In `infra/terraform/backend/main.tf`, find line 276 (`PERSONA_URL = var.persona_image == "" ? "" : google_cloud_run_v2_service.persona[0].uri`) and add a sibling line immediately after it:

```hcl
VIDEO_URL                = var.video_image == "" ? "" : google_cloud_run_v2_service.video[0].uri
```

- [ ] **Step 3: Validate the Terraform syntax**

Run: `cd infra/terraform/backend && terraform fmt -check && terraform validate`
Expected: no formatting diff, `Success! The configuration is valid.` (This does NOT apply anything — no real resources are touched by this task.)

- [ ] **Step 4: Commit**

```bash
git add infra/terraform/backend/video.tf infra/terraform/backend/main.tf
git commit -m "infra: add video-agent Cloud Run service (Terraform, not yet applied)"
```

---

### Task 11: Frontend — implement the `story-video` section

**Files:**
- Modify: `frontend/src/main.jsx` (the existing `story-video` `<section>`)
- Create: `frontend/src/VideoRequest.jsx` (extract the whole feature into its own component — `main.jsx` is already extremely dense JSX, per "Working in existing codebases" this is a targeted, justified split rather than growing the existing wall of JSX further)
- Create: `frontend/src/video-request.css`

**Interfaces:**
- Consumes: `api`, `clientToken` from `frontend/src/api.js` (existing).
- Produces: `VideoRequest` component, imported and rendered from `main.jsx` in place of the current static placeholder markup.

- [ ] **Step 1: Read `frontend/src/main.jsx`'s current `story-video` section and `AvatarSetup.jsx` in full before writing anything**

This is required — `main.jsx` is one dense file and the exact JSX to replace must be located precisely (search for `className="story-video"`), and `AvatarSetup.jsx`'s consent/disabled/aria-live patterns must be copied exactly, not reinvented.

- [ ] **Step 2: Check whether a frontend test runner exists**

Run: `cd frontend && cat package.json`
If there's no `test` script and no `vitest`/`jest` dependency (unlike `persona-agent-frontend`, which has `vitest` — `frontend/` may not), **do not introduce one for this task alone**. Verify manually in the browser (Step 6) instead, and note this explicitly rather than silently skipping automated tests.

- [ ] **Step 3: Write `VideoRequest.jsx`**

```jsx
// frontend/src/VideoRequest.jsx
import { useEffect, useState } from 'react'
import { api, clientToken } from './api'
import './video-request.css'

const STYLES = [['cinematic', 'シネマティック'], ['long_take', 'ロングテイク'], ['narrated', 'ナレーション付き']]
const TONES = [['calm', '穏やかな'], ['dramatic', 'ドラマチックな'], ['relaxed', '落ち着いた']]

export default function VideoRequest({ agents }) {
  const [reportId, setReportId] = useState('')
  const [feedback, setFeedback] = useState('')
  const [style, setStyle] = useState('cinematic')
  const [tone, setTone] = useState('calm')
  const [consent, setConsent] = useState(false)
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (!reportId || !consent || submitting) return
    setSubmitting(true); setError('')
    try {
      const job = await api('/api/videos', { method: 'POST', body: { report_id: reportId, feedback, style, tone, consent } })
      setJobId(job.id); setStatus(job.status)
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }

  useEffect(() => {
    if (!jobId || videoUrl) return
    const origin = (import.meta.env.VITE_API_URL || window.MICHIBIKI_API_URL || '').replace(/\/$/, '')
    const wsUrl = origin.replace(/^http/, 'ws') + `/api/video-jobs/${jobId}/progress`
    const socket = new WebSocket(wsUrl, [], { headers: { 'X-Michibiki-Client': clientToken() } })
    // Browsers don't support custom WS headers; send the client token as a query param instead.
    const socketWithToken = new WebSocket(`${wsUrl}?client=${encodeURIComponent(clientToken())}`)
    socketWithToken.onmessage = event => {
      const message = JSON.parse(event.data)
      if (message.type === 'status') {
        setStatus(message.status)
        if (message.status === 'ready') setVideoUrl(message.video_url)
        if (message.status === 'failed') setError(message.message)
      }
    }
    socketWithToken.onerror = () => setError('動画の進行状況を取得できませんでした。')
    return () => socketWithToken.close()
  }, [jobId, videoUrl])

  return <section className="video-request">
    {!jobId && <>
      <label>動画化する体験<select value={reportId} onChange={e => setReportId(e.target.value)} disabled={submitting}>
        <option value="">選んでください</option>
        {agents.map(agent => <option key={agent.report_id} value={agent.report_id}>{agent.place}</option>)}
      </select></label>
      <label>フィードバック<textarea maxLength={500} value={feedback} onChange={e => setFeedback(e.target.value)} disabled={submitting} />
        <small>{feedback.length}/500</small></label>
      <label>動画スタイル<select value={style} onChange={e => setStyle(e.target.value)} disabled={submitting}>
        {STYLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>感情トーン<select value={tone} onChange={e => setTone(e.target.value)} disabled={submitting}>
        {TONES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="video-consent"><input type="checkbox" checked={consent} disabled={submitting}
        onChange={e => setConsent(e.target.checked)} />
        <span>あなたのアバター画像とこの体験談をもとに、Veoへ送信して動画を生成することに同意します。</span></label>
      <button type="button" className="journey-button" disabled={!reportId || !consent || submitting} onClick={submit}>
        {submitting ? '依頼を送信中…' : '動画を作る →'}</button>
    </>}
    {jobId && !videoUrl && !error &&
      <p aria-live="polite">動画生成には数分かかります。生成依頼は保存されるので、ページを再読み込みしても続きから確認できます。(現在: {status})</p>}
    {videoUrl && <video controls src={videoUrl} />}
    {error && <p className="video-warning" role="alert">{error}</p>}
  </section>
}
```

(The `socket`/`socketWithToken` double-construction above is deliberately left as a visible TODO-for-the-implementer marker — browsers cannot set custom headers on a `WebSocket` constructor call, so the client token must travel as a query param instead. **Before shipping this task, the backend's `video_progress` handler (Task 8) must be updated to read the token from `websocket.query_params.get("client")` as a fallback when the header is absent**, and this component simplified to construct only `socketWithToken`, renamed to `socket`, with the unused first `new WebSocket(...)` line deleted. Do this adjustment as part of Step 3, not left for later — it's called out this explicitly so the gap isn't missed, not because leaving it is acceptable.)

- [ ] **Step 4: Fix Task 8's WS handler to accept the client token via query param**

Revisit `backend/michibiki/michibiki/video.py`'s `video_progress` function (Task 8): change

```python
client_token = websocket.headers.get("x-michibiki-client", "")
```

to

```python
client_token = websocket.query_params.get("client") or websocket.headers.get("x-michibiki-client", "")
```

Add a test to `backend/tests/test_video_router.py` confirming a connection with `?client=...` (no header) still authenticates:

```python
def test_progress_ws_accepts_client_token_as_query_param():
    with patch("michibiki.db.get_video_job", return_value=None):
        with client.websocket_connect("/api/video-jobs/job-1/progress?client=" + "a" * 40) as websocket:
            import pytest
            from starlette.websockets import WebSocketDisconnect
            with pytest.raises(WebSocketDisconnect):
                websocket.receive_json()  # closes immediately since get_video_job returns None, but must not reject for missing header
```

Run: `cd backend && uv run pytest tests/test_video_router.py -v` — expect PASS (9 tests total in this file now).
Commit this fix together with its own small step:

```bash
git add backend/michibiki/michibiki/video.py backend/tests/test_video_router.py
git commit -m "fix: accept video progress WS client token via query param (browsers can't set WS headers)"
```

- [ ] **Step 5: Write `video-request.css`, mirroring `avatar-setup.css`'s existing conventions**

```css
/* frontend/src/video-request.css */
.video-request { display: flex; flex-direction: column; gap: 0.75rem; }
.video-request label { display: flex; flex-direction: column; gap: 0.25rem; }
.video-request textarea { resize: vertical; min-height: 4rem; }
.video-consent { flex-direction: row; align-items: flex-start; gap: 0.5rem; }
.video-warning { color: #b3261e; }
.video-request video { width: 100%; border-radius: 0.5rem; }
```

(Check `avatar-setup.css` first and reuse its actual color/spacing values instead of the placeholders above if they differ — this file should look like a sibling of that one, not an unrelated new style.)

- [ ] **Step 6: Wire `VideoRequest` into `main.jsx`'s `story-video` section**

Replace the `<section className="story-video">...</section>` block's inner content (the one with `videoChoice`/`video-skeleton` placeholder markup found in Step 1) with:

```jsx
<section className="story-video">
  <div><p className="eyebrow">EXPERIENCE STORY / PREVIEW</p>
    <h2>この一日を、<br />体験の物語で見る。</h2></div>
  <VideoRequest agents={agents} />
</section>
```

Add `import VideoRequest from './VideoRequest'` near the top of `main.jsx` with the other imports, and remove the now-unused `videoChoice`/`setVideoChoice` state if nothing else in the file references it (confirm with `grep -n videoChoice frontend/src/main.jsx` before deleting).

- [ ] **Step 7: Manual verification (no automated frontend test runner exists per Step 2)**

Run: `cd frontend && npm install && npm run dev`
In the browser, complete a mission, reach the results page, and confirm: the form renders with real `agents` options, the submit button stays disabled until a report + consent are both set, and submitting without a reachable `VIDEO_URL` (local dev has none configured) shows a `503`-derived error message inline rather than crashing the page. Report this manual check's outcome before moving on — do not claim it works without having actually run it.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/VideoRequest.jsx frontend/src/video-request.css frontend/src/main.jsx
git commit -m "feat: implement the story-video section with real video generation"
```

---

### Task 12: End-to-end human verification

**Files:** none

- [ ] **Step 1: Build and deploy both new images**

```bash
cd video-agent && gcloud builds submit --config cloudbuild.yaml --substitutions=_REGION=asia-northeast1
cd ../backend && gcloud builds submit  # existing build process for backend/michibiki, unchanged
```

- [ ] **Step 2: Apply Terraform with both images set**

```bash
cd infra/terraform/backend
terraform apply -var="video_image=<the video-agent image just built>" -var="persona_image=<existing value>"
```

- [ ] **Step 3: Confirm `VIDEO_URL` reached the backend service**

```bash
gcloud run services describe michibiki-backend --region asia-northeast1 --format="value(spec.template.spec.containers[0].env)" | grep VIDEO_URL
```

- [ ] **Step 4: Run the real flow in a browser**

Complete a mission end to end, open the results page, submit a video request with real feedback, and watch it through `queued` → `generating` → `ready` (or `failed`). Record the actual elapsed time and whether the resulting video plays. This is the first time the full pipeline runs against real Veo — do not consider this plan complete until this step has actually been run and its outcome reported, not assumed.
