# Persona Avatar v2 (YouCam base + Nano Banana evolution + weighted schema) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user-photo-personalized, evolving avatar (YouCam AI Avatar Generator for the base image, Gemini 2.5 Flash Image for per-conversation attribute-driven edits) and a weighted persona schema (`domain` + `rank` replacing `priority`) to the already-implemented persona-intake-agent.

**Architecture:** Frontend gains a photo-upload step before "話しかける"; the photo is sent once over the existing WebSocket, the backend runs it through YouCam's async upload→task→poll flow to get a personalized base avatar, then at `finish` (same point persona extraction already runs) edits that base image via Gemini 2.5 Flash Image using the extracted attributes, and returns both the persona JSON and the final avatar image in one `persona_result` message.

**Tech Stack:** Same as the existing implementation — Python/FastAPI/`google-genai` (Vertex AI) backend, React/Vite/Vitest frontend. New: `requests` (already installed) + `cryptography` (already installed) for the YouCam REST calls.

**Spec:** `docs/superpowers/specs/2026-09-13-persona-intake-agent-avatar-and-schema-v2-design.md` (and the base `docs/superpowers/specs/2026-09-13-persona-intake-agent-design.md` this extends)

## Global Constraints

- `PERFECTCORP_API_KEY` and `PERFECTCORP_API_SECRET` are read from environment variables only. Never hardcode, log, or print their values or any derived `id_token`/`access_token` — every YouCam-related test in this plan redacts these before printing.
- `domain` is a fixed enum of exactly 7 values: `mobility`, `dietary`, `purpose`, `companions`, `language`, `background`, `other`. `category`/`description` remain free-form text (unchanged from v1).
- `rank` replaces `priority` entirely: a 1-based integer, unique across all of a persona's `attributes`, where 1 is most important. No two attributes share a rank.
- Avatar image generation (both YouCam and Nano Banana) happens at most once per phase of the conversation: YouCam once when a photo is submitted, Nano Banana once at `finish`. Never call either mid-conversation.
- Do not weaken any TLS/certificate verification setting to work around a local build or network failure (standing project rule — see `docs/wiki/concepts/deployed-endpoints.md` and this branch's earlier SDD ledger).

---

### Task 1: Persona schema — `domain` + `rank` replacing `priority`

**Files:**
- Modify: `persona-agent-backend/schemas.py`
- Modify: `persona-agent-backend/persona_extraction.py`
- Test: `persona-agent-backend/tests/test_schemas.py`
- Test: `persona-agent-backend/tests/test_persona_extraction.py`

**Interfaces:**
- Produces: `Domain = Literal["mobility", "dietary", "purpose", "companions", "language", "background", "other"]` and `Attribute.domain: Domain`, `Attribute.rank: int` (replaces `Attribute.priority`) in `schemas.py`, consumed by every later task that touches `Attribute`.

- [ ] **Step 1: Update the failing schema test**

Read the current `persona-agent-backend/tests/test_schemas.py` first (it exists from Task 1 of the original plan). Replace any test that constructs an `Attribute` with `priority=...` to instead use `domain=...` and `rank=...`. Add this new test to the same file:

```python
def test_attribute_rejects_invalid_domain():
    with pytest.raises(ValidationError):
        Attribute(
            domain="not_a_real_domain",
            category="test",
            description="test",
            rank=1,
            confidence="high",
        )
```

Make sure `import pytest` and `from pydantic import ValidationError` are present at the top of the file (add them if missing).

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_schemas.py -v`
Expected: FAIL — `Attribute` has no field `domain` yet (or a `TypeError`/`ValidationError` mismatch, since `priority` is still required).

- [ ] **Step 3: Update `schemas.py`**

```python
"""Persona output schema. category is intentionally free-form text, not
an enum — the design decision (see design spec, "背景・非目標") is that
the intake agent must not lock users into a predetermined attribute list.
domain IS a fixed enum (see the v2 design spec's "ペルソナJSONスキーマの変更")
— it groups attributes into a small set of buckets other agents can rely
on, while category/description underneath stay free-form.
"""
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["high", "medium", "low"]
Domain = Literal["mobility", "dietary", "purpose", "companions", "language", "background", "other"]


class Attribute(BaseModel):
    domain: Domain
    category: str
    description: str
    rank: int
    confidence: Level
    inferred_keywords: list[str] = Field(default_factory=list)


class Persona(BaseModel):
    persona_id: str
    raw_summary: str
    attributes: list[Attribute] = Field(default_factory=list)
```

- [ ] **Step 4: Run the schema test to verify it passes**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Update the failing persona_extraction test**

Read `persona-agent-backend/tests/test_persona_extraction.py` first. Every mocked Gemini JSON response fixture in that file that includes `"priority": "..."` must be changed to include `"domain": "..."` (pick a valid domain matching the attribute's content) and `"rank": <int>` instead. Every assertion that reads `attr.priority` must be changed to read `attr.domain` / `attr.rank`. Add this new test to the same file:

```python
def test_extract_persona_produces_unique_ranks():
    class FakeResponse:
        text = (
            '{"raw_summary": "s", "attributes": ['
            '{"domain": "mobility", "category": "a", "description": "d1", "rank": 1, "confidence": "high"},'
            '{"domain": "dietary", "category": "b", "description": "d2", "rank": 2, "confidence": "medium"}'
            "]}"
        )

    class FakeModels:
        def generate_content(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    persona = extract_persona(transcript="test transcript", genai_client=FakeClient())
    ranks = [a.rank for a in persona.attributes]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)
    assert all(a.domain in ("mobility", "dietary", "purpose", "companions", "language", "background", "other") for a in persona.attributes)
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_persona_extraction.py -v`
Expected: FAIL — `extract_persona` still builds `Attribute(priority=...)`, which no longer exists as a field, so this raises a `TypeError`/`ValidationError`.

- [ ] **Step 7: Update `persona_extraction.py`**

```python
import json
import uuid

from google.genai import types

from schemas import Attribute, Persona

EXTRACTION_PROMPT = """\
あなたは、旅行・外食のプランニングを支援するために、ユーザーとの対話ログから
ペルソナ情報を抽出するアシスタントです。

以下の対話ログを読み、次のJSON形式で出力してください:
- raw_summary: 対話全体を1〜3文で要約した自由文
- attributes: 対話から読み取れる、ユーザーの移動制約・食事制約・目的・家族構成・
  優先事項などを表す配列。各要素は次のフィールドを持つ:
  - domain: 次の7つの固定値のいずれか — "mobility"(移動制約) / "dietary"(食事) /
    "purpose"(目的) / "companions"(同行者・人数) / "language"(言語対応) /
    "background"(居住地・出身地・国籍等) / "other"(上記に当てはまらないもの)
  - category: 自由記述の文字列(固定の選択肢はない。対話内容に合った具体的な名前を付けてよい)
  - description: その属性を説明する自由文
  - rank: 1から始まる整数。すべてのattributesを通じて一意で、1が最も重要。
    このユーザーにとって「どの属性が他の属性より重要か」を、対話のトーン・
    繰り返し・強調から相対的に判断してつけること(すべてを見た上で決めること)
  - confidence: "high" | "medium" | "low"(対話からどれだけ確信を持って読み取れるか)

対話から何も読み取れない場合は、attributesを空配列にしてください。
同じ会話内で同じ概念に別の名前を付けないよう、category名の一貫性を保ってください。

対話ログ:
{transcript}
"""


def extract_persona(transcript: str, genai_client) -> Persona:
    prompt = EXTRACTION_PROMPT.format(transcript=transcript)
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    parsed = json.loads(response.text)

    attributes = [
        Attribute(
            domain=a["domain"],
            category=a["category"],
            description=a["description"],
            rank=a["rank"],
            confidence=a["confidence"],
        )
        for a in parsed.get("attributes", [])
    ]

    return Persona(
        persona_id=str(uuid.uuid4()),
        raw_summary=parsed.get("raw_summary", ""),
        attributes=attributes,
    )
```

- [ ] **Step 8: Run both test files to verify they pass**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_schemas.py tests/test_persona_extraction.py -v`
Expected: PASS (all tests)

- [ ] **Step 9: Run the full backend suite to check for other breakage**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest -v`
Expected: any other test referencing `priority` (e.g. in `test_keyword_inference.py` or `test_main.py` fixtures) will now fail — fix those fixtures the same way (replace `priority` with `domain`+`rank`) before moving on. Do not proceed to Step 10 until the full suite is green.

- [ ] **Step 10: Commit**

```bash
git add persona-agent-backend/schemas.py persona-agent-backend/persona_extraction.py persona-agent-backend/tests/
git commit -m "feat: replace Attribute.priority with domain (fixed enum) + rank (relative order)"
```

---

### Task 2: YouCam client — auth + upload + task + poll

**Files:**
- Create: `persona-agent-backend/youcam_client.py`
- Test: `persona-agent-backend/tests/test_youcam_client.py`

**Interfaces:**
- Consumes: `PERFECTCORP_API_KEY`, `PERFECTCORP_API_SECRET` environment variables
- Produces: `generate_base_avatar(photo_bytes: bytes, content_type: str, template_id: str = "female_manga_mood") -> bytes` — a plain (non-async) function returning the generated avatar image bytes. Consumed by Task 3 (WebSocket wiring).

**Verified facts this task's code is built from** (confirmed against the real API on 2026-09-14, not guessed):
- Auth is the *legacy* flow: `PERFECTCORP_API_SECRET` is a base64-encoded DER RSA public key. Build `id_token = base64(RSA_PKCS1v15_encrypt(f"client_id={client_id}&timestamp={epoch_ms}".encode(), public_key))`, then `POST https://yce-api-01.makeupar.com/s2s/v1.0/client/auth` with JSON body `{"client_id": ..., "id_token": ...}`. Response: `{"status": 200, "result": {"access_token": "..."}}` — note this ONE endpoint nests under `"result"`, not `"data"` (every other endpoint below uses `"data"`).
- File upload: `POST https://yce-api-01.makeupar.com/s2s/v2.0/file` with header `Authorization: Bearer <access_token>` and JSON body `{"files": [{"content_type": ..., "file_name": ..., "file_size": <int>}]}`. Response: `{"status": 200, "data": {"files": [{"file_id": "...", "requests": [{"method": "PUT", "url": "...", "headers": {...}}]}]}}`. PUT the raw bytes to that `url` with those `headers`.
- Task creation: `POST https://yce-api-01.makeupar.com/s2s/v2.0/task/ai-avatar` with JSON body `{"src_file_id": <file_id>, "template_id": <template_id>, "output_count": 1}` (param name is `output_count`, not `output_cnt`). Response: `{"status": 200, "data": {"task_id": "..."}}`.
- Polling: `GET https://yce-api-01.makeupar.com/s2s/v2.0/task/ai-avatar/{task_id}` with the same Bearer header. Response while running: `{"status": 200, "data": {"task_status": "running", ...}}` (or similar non-terminal value). On success: `{"status": 200, "data": {"task_status": "success", "results": {"output": [{"url": "..."}]}}}`. GET that `url` (no auth header needed — it's a pre-signed S3 URL) to download the final image bytes.

- [ ] **Step 1: Write the failing test**

```python
# persona-agent-backend/tests/test_youcam_client.py
from unittest.mock import MagicMock, patch

from youcam_client import generate_base_avatar


@patch("youcam_client._get_access_token", return_value="fake-token")
@patch("youcam_client.requests.get")
@patch("youcam_client.requests.request")
@patch("youcam_client.requests.post")
def test_generate_base_avatar_full_flow(mock_post, mock_request, mock_get, _mock_token):
    file_create_resp = MagicMock()
    file_create_resp.json.return_value = {
        "data": {
            "files": [
                {
                    "file_id": "file-123",
                    "requests": [{"method": "PUT", "url": "https://upload.example/x", "headers": {"Content-Type": "image/png"}}],
                }
            ]
        }
    }
    task_create_resp = MagicMock()
    task_create_resp.json.return_value = {"data": {"task_id": "task-abc"}}
    mock_post.side_effect = [file_create_resp, task_create_resp]

    upload_resp = MagicMock()
    mock_request.return_value = upload_resp

    poll_resp = MagicMock()
    poll_resp.json.return_value = {
        "data": {
            "task_status": "success",
            "results": {"output": [{"url": "https://result.example/avatar.jpg"}]},
        }
    }
    download_resp = MagicMock()
    download_resp.content = b"fake-image-bytes"
    mock_get.side_effect = [poll_resp, download_resp]

    result = generate_base_avatar(photo_bytes=b"fake-photo-bytes", content_type="image/png")

    assert result == b"fake-image-bytes"
    mock_request.assert_called_once_with(
        "PUT", "https://upload.example/x", headers={"Content-Type": "image/png"}, data=b"fake-photo-bytes", timeout=30
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_youcam_client.py -v`
Expected: FAIL — `youcam_client` module doesn't exist yet (`ModuleNotFoundError`).

- [ ] **Step 3: Write `youcam_client.py`**

```python
# persona-agent-backend/youcam_client.py
"""Perfect Corp YouCam AI Avatar Generator client.

Auth flow, request/response shapes, and field names below were verified
against the real API on 2026-09-14 (see this plan's Task 2 header for the
exact verification notes) — the third-party OpenAPI mirror this was first
drafted from had the response envelope key wrong (documented "result",
actual "data" for every endpoint except /client/auth) and the task-create
param name wrong ("output_cnt" vs the real "output_count").
"""
import base64
import os
import time

import requests
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE_URL = "https://yce-api-01.makeupar.com"
POLL_INTERVAL_SECONDS = 3
MAX_POLL_ATTEMPTS = 40


def _get_access_token() -> str:
    client_id = os.environ["PERFECTCORP_API_KEY"]
    public_key_b64 = os.environ["PERFECTCORP_API_SECRET"]

    public_key_der = base64.b64decode(public_key_b64)
    public_key = load_der_public_key(public_key_der)

    timestamp_ms = int(time.time() * 1000)
    payload = f"client_id={client_id}&timestamp={timestamp_ms}".encode()
    encrypted = public_key.encrypt(payload, padding.PKCS1v15())
    id_token = base64.b64encode(encrypted).decode()

    resp = requests.post(
        f"{BASE_URL}/s2s/v1.0/client/auth",
        json={"client_id": client_id, "id_token": id_token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["result"]["access_token"]


def generate_base_avatar(
    photo_bytes: bytes,
    content_type: str,
    template_id: str = "female_manga_mood",
) -> bytes:
    """Runs the full YouCam AI Avatar Generator flow synchronously and
    returns the generated avatar image bytes. Raises requests.HTTPError or
    RuntimeError (on task failure/timeout) rather than returning a
    sentinel — callers decide how to fall back."""
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    file_resp = requests.post(
        f"{BASE_URL}/s2s/v2.0/file",
        headers=headers,
        json={"files": [{"content_type": content_type, "file_name": "photo", "file_size": len(photo_bytes)}]},
        timeout=15,
    )
    file_resp.raise_for_status()
    file_info = file_resp.json()["data"]["files"][0]
    file_id = file_info["file_id"]
    upload_req = file_info["requests"][0]

    upload_resp = requests.request(
        upload_req["method"],
        upload_req["url"],
        headers=upload_req.get("headers", {}),
        data=photo_bytes,
        timeout=30,
    )
    upload_resp.raise_for_status()

    task_resp = requests.post(
        f"{BASE_URL}/s2s/v2.0/task/ai-avatar",
        headers=headers,
        json={"src_file_id": file_id, "template_id": template_id, "output_count": 1},
        timeout=15,
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["data"]["task_id"]

    for _ in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        poll_resp = requests.get(f"{BASE_URL}/s2s/v2.0/task/ai-avatar/{task_id}", headers=headers, timeout=15)
        poll_resp.raise_for_status()
        poll_data = poll_resp.json()["data"]
        status = poll_data.get("task_status")
        if status == "success":
            result_url = poll_data["results"]["output"][0]["url"]
            image_resp = requests.get(result_url, timeout=30)
            image_resp.raise_for_status()
            return image_resp.content
        if status == "error":
            raise RuntimeError(f"YouCam ai-avatar task {task_id} failed: {poll_data}")

    raise RuntimeError(f"YouCam ai-avatar task {task_id} did not finish within {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_youcam_client.py -v`
Expected: PASS

- [ ] **Step 5: (Optional, only if you have real credentials) Real smoke test**

If `PERFECTCORP_API_KEY`/`PERFECTCORP_API_SECRET` are set as real environment variables, you may verify against the live API:

```bash
cd persona-agent-backend && .venv/bin/python -c "
from youcam_client import generate_base_avatar
img = generate_base_avatar(photo_bytes=open('some_test_photo.png', 'rb').read(), content_type='image/png')
open('/tmp/youcam_smoke_test_result.jpg', 'wb').write(img)
print('saved', len(img), 'bytes')
"
```

Never print or log the environment variable values themselves. This step is optional and does not block the task — the mocked unit test in Step 4 is the required verification.

- [ ] **Step 6: Commit**

```bash
git add persona-agent-backend/youcam_client.py persona-agent-backend/tests/test_youcam_client.py
git commit -m "feat: add YouCam AI Avatar Generator client for personalized base avatar images"
```

---

### Task 3: Nano Banana avatar evolution

**Files:**
- Create: `persona-agent-backend/avatar_generation.py`
- Test: `persona-agent-backend/tests/test_avatar_generation.py`

**Interfaces:**
- Consumes: `Persona`/`Attribute` from `schemas.py` (Task 1)
- Produces: `evolve_avatar(base_image_bytes: bytes, persona: Persona, genai_client) -> bytes`, consumed by Task 4 (WebSocket wiring)

- [ ] **Step 1: Write the failing test**

```python
# persona-agent-backend/tests/test_avatar_generation.py
from unittest.mock import MagicMock

from avatar_generation import evolve_avatar
from schemas import Attribute, Persona


def test_evolve_avatar_returns_edited_image_bytes():
    persona = Persona(
        persona_id="test-id",
        raw_summary="summary",
        attributes=[
            Attribute(domain="mobility", category="車椅子", description="電動車椅子", rank=1, confidence="high"),
        ],
    )

    fake_part = MagicMock()
    fake_part.inline_data.data = b"edited-image-bytes"
    fake_part.text = None
    fake_response = MagicMock()
    fake_response.candidates = [MagicMock(content=MagicMock(parts=[fake_part]))]

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    result = evolve_avatar(base_image_bytes=b"base-image-bytes", persona=persona, genai_client=fake_client)

    assert result == b"edited-image-bytes"
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash-image"


def test_evolve_avatar_with_no_attributes_returns_base_image_unchanged():
    persona = Persona(persona_id="test-id", raw_summary="", attributes=[])
    fake_client = MagicMock()

    result = evolve_avatar(base_image_bytes=b"base-image-bytes", persona=persona, genai_client=fake_client)

    assert result == b"base-image-bytes"
    fake_client.models.generate_content.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_avatar_generation.py -v`
Expected: FAIL — `avatar_generation` module doesn't exist yet.

- [ ] **Step 3: Write `avatar_generation.py`**

```python
# persona-agent-backend/avatar_generation.py
from google.genai import types

from schemas import Persona

EDIT_PROMPT_TEMPLATE = """\
このキャラクターと完全に同じ顔・髪型・服装・背景・アートスタイルを保ったまま、
以下の特徴を自然に反映するように編集してください。それ以外は一切変えないでください。

{attribute_lines}
"""


def evolve_avatar(base_image_bytes: bytes, persona: Persona, genai_client) -> bytes:
    """Edits the base avatar image to reflect the persona's attributes,
    preserving character identity (see the v2 design spec's verified
    Nano Banana consistency behavior). Returns the base image unchanged
    if there are no attributes to reflect yet, without calling Gemini."""
    if not persona.attributes:
        return base_image_bytes

    attribute_lines = "\n".join(f"- {a.category}: {a.description}" for a in persona.attributes)
    prompt = EDIT_PROMPT_TEMPLATE.format(attribute_lines=attribute_lines)

    response = genai_client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            types.Part.from_bytes(data=base_image_bytes, mime_type="image/png"),
            prompt,
        ],
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    return base_image_bytes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_avatar_generation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add persona-agent-backend/avatar_generation.py persona-agent-backend/tests/test_avatar_generation.py
git commit -m "feat: add Nano Banana avatar evolution from persona attributes"
```

---

### Task 4: Wire photo upload + avatar generation into the WebSocket flow

**Files:**
- Modify: `persona-agent-backend/live_session.py`
- Modify: `persona-agent-backend/main.py`
- Test: `persona-agent-backend/tests/test_live_session.py`
- Test: `persona-agent-backend/tests/test_main.py`

**Interfaces:**
- Consumes: `generate_base_avatar` (Task 2), `evolve_avatar` (Task 3)
- Produces: `LiveConversation.set_base_photo(photo_bytes: bytes, content_type: str) -> bytes` (returns the YouCam-generated base avatar image bytes) and an updated `LiveConversation.finish() -> tuple[Persona, bytes]` (now also returns the final avatar image bytes, falling back to the stored base image if no photo was ever submitted). New WebSocket message types: inbound `avatar_photo` (`{"type": "avatar_photo", "data": "<base64>", "content_type": "image/png"}`) triggering an immediate outbound `avatar_base_image` (`{"type": "avatar_base_image", "data": "<base64>"}`); `persona_result`'s `data` gains an `avatar_image` field (base64 string, may be `null` if no photo was ever submitted).

- [ ] **Step 1: Read the current `live_session.py` and `main.py` in full**

These files already exist from the original plan (Tasks 4-6). Read them before editing — the diffs below assume the exact current shape (constructor, `start`/`send_audio`/`receive_audio_chunks`/`close`/`finish` on `LiveConversation`; the `converse` WebSocket handler and `_relay_model_audio` helper in `main.py`).

- [ ] **Step 2: Write the failing test for `LiveConversation`**

Read the current `persona-agent-backend/tests/test_live_session.py` first. Add these tests to it (adjust the exact mocking pattern already used in that file for `genai_client`/`_session` to match, then layer these on top):

```python
def test_set_base_photo_calls_youcam_and_stores_result(monkeypatch):
    import live_session

    monkeypatch.setattr(live_session, "generate_base_avatar", lambda photo_bytes, content_type: b"youcam-avatar-bytes")

    conversation = live_session.LiveConversation(genai_client=MagicMock())
    result = conversation.set_base_photo(photo_bytes=b"raw-photo", content_type="image/png")

    assert result == b"youcam-avatar-bytes"
    assert conversation._base_avatar_image == b"youcam-avatar-bytes"


@pytest.mark.asyncio
async def test_finish_returns_persona_and_evolved_avatar(monkeypatch):
    import live_session

    fake_persona = Persona(persona_id="id", raw_summary="s", attributes=[])
    monkeypatch.setattr(live_session, "extract_persona", lambda transcript, genai_client: fake_persona)
    monkeypatch.setattr(live_session, "infer_keywords", lambda persona, genai_client: persona)
    monkeypatch.setattr(live_session, "evolve_avatar", lambda base_image_bytes, persona, genai_client: b"evolved-bytes")

    conversation = live_session.LiveConversation(genai_client=MagicMock())
    conversation._session_ctx = None
    conversation._base_avatar_image = b"base-bytes"

    persona, avatar_bytes = await conversation.finish()

    assert persona == fake_persona
    assert avatar_bytes == b"evolved-bytes"


@pytest.mark.asyncio
async def test_finish_with_no_photo_returns_none_avatar(monkeypatch):
    import live_session

    fake_persona = Persona(persona_id="id", raw_summary="s", attributes=[])
    monkeypatch.setattr(live_session, "extract_persona", lambda transcript, genai_client: fake_persona)
    monkeypatch.setattr(live_session, "infer_keywords", lambda persona, genai_client: persona)

    conversation = live_session.LiveConversation(genai_client=MagicMock())
    conversation._session_ctx = None

    persona, avatar_bytes = await conversation.finish()

    assert avatar_bytes is None
```

Add `from schemas import Persona` and `import pytest` and `from unittest.mock import MagicMock` at the top of the test file if not already present (check first — `test_live_session.py` likely already imports some of these).

- [ ] **Step 3: Run to verify it fails**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_live_session.py -v`
Expected: FAIL — `set_base_photo` doesn't exist, and `finish()` still returns only a `Persona`, not a tuple.

- [ ] **Step 4: Update `live_session.py`**

Add these imports at the top (alongside the existing ones):

```python
from avatar_generation import evolve_avatar
from youcam_client import generate_base_avatar
```

Add `self._base_avatar_image: bytes | None = None` to `LiveConversation.__init__`.

Add this method to `LiveConversation` (anywhere among its other methods, e.g. right before `close`):

```python
    def set_base_photo(self, photo_bytes: bytes, content_type: str) -> bytes:
        """Runs the user's uploaded photo through YouCam once to produce a
        personalized base avatar, stores it for the finish()-time Nano
        Banana edit, and returns it so the caller can show it immediately."""
        self._base_avatar_image = generate_base_avatar(photo_bytes=photo_bytes, content_type=content_type)
        return self._base_avatar_image
```

Replace the existing `finish` method with:

```python
    async def finish(self) -> tuple[Persona, bytes | None]:
        await self.close()
        transcript = "\n".join(self._transcript_parts)
        persona = extract_persona(transcript=transcript, genai_client=self.genai_client)
        persona = infer_keywords(persona, self.genai_client)

        avatar_image = None
        if self._base_avatar_image is not None:
            avatar_image = evolve_avatar(
                base_image_bytes=self._base_avatar_image,
                persona=persona,
                genai_client=self.genai_client,
            )

        return persona, avatar_image
```

- [ ] **Step 5: Run to verify `test_live_session.py` passes**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_live_session.py -v`
Expected: PASS

- [ ] **Step 6: Write the failing test for `main.py`'s new message types**

Read the current `persona-agent-backend/tests/test_main.py` first (it already has `test_websocket_finish_flow_calls_live_conversation` from the original plan — that test's assertions on the `finish` response shape will need updating in this step too, since `finish()`'s return type changed). Update that existing test's mock:

```python
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="要約", attributes=[]), b"avatar-bytes")
        )
```

and update its assertion on the received message to:

```python
        assert data == {
            "type": "persona_result",
            "data": {
                "persona_id": "test-id",
                "raw_summary": "要約",
                "attributes": [],
                "avatar_image": base64.b64encode(b"avatar-bytes").decode("ascii"),
            },
        }
```

Then add this new test to the same file:

```python
def test_websocket_avatar_photo_flow_calls_set_base_photo_and_relays_result():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()
        mock_conversation.set_base_photo = MagicMock(return_value=b"base-avatar-bytes")

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover - makes this an async generator with no items

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json(
                {"type": "avatar_photo", "data": base64.b64encode(b"photo-bytes").decode("ascii"), "content_type": "image/png"}
            )
            data = websocket.receive_json()
            websocket.send_json({"type": "finish"})

        assert data == {
            "type": "avatar_base_image",
            "data": base64.b64encode(b"base-avatar-bytes").decode("ascii"),
        }
        mock_conversation.set_base_photo.assert_called_once_with(photo_bytes=b"photo-bytes", content_type="image/png")
```

Add `from unittest.mock import MagicMock` to the top imports if not already present.

- [ ] **Step 7: Run to verify the new/changed tests fail**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL — `main.py`'s `converse` handler doesn't handle `"avatar_photo"` yet, and `persona_result`'s payload doesn't include `avatar_image` yet.

- [ ] **Step 8: Update `main.py`**

Replace the `elif message.get("type") == "finish":` branch and add a new `elif` branch for `avatar_photo`, so the relevant part of the `converse` function becomes:

```python
            if message.get("type") == "audio_chunk":
                audio_bytes = base64.b64decode(message["data"])
                await conversation.send_audio(audio_bytes)

            elif message.get("type") == "avatar_photo":
                photo_bytes = base64.b64decode(message["data"])
                content_type = message.get("content_type", "image/png")
                base_image = conversation.set_base_photo(photo_bytes=photo_bytes, content_type=content_type)
                await websocket.send_json(
                    {"type": "avatar_base_image", "data": base64.b64encode(base_image).decode("ascii")}
                )

            elif message.get("type") == "finish":
                relay_task.cancel()
                try:
                    await relay_task
                except asyncio.CancelledError:
                    pass
                persona, avatar_image = await conversation.finish()
                persona_data = persona.model_dump()
                persona_data["avatar_image"] = (
                    base64.b64encode(avatar_image).decode("ascii") if avatar_image is not None else None
                )
                await websocket.send_json({"type": "persona_result", "data": persona_data})
                break
```

- [ ] **Step 9: Run to verify `test_main.py` passes**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 10: Run the full backend suite**

Run: `cd persona-agent-backend && .venv/bin/python -m pytest -v`
Expected: PASS (all tests, all files)

- [ ] **Step 11: Commit**

```bash
git add persona-agent-backend/live_session.py persona-agent-backend/main.py persona-agent-backend/tests/
git commit -m "feat: wire YouCam base avatar + Nano Banana evolution into the WebSocket flow"
```

---

### Task 5: Frontend — photo upload UI + updated types

**Files:**
- Modify: `persona-agent-frontend/src/ws/PersonaSocket.ts`
- Modify: `persona-agent-frontend/src/ws/PersonaSocket.test.ts`
- Modify: `persona-agent-frontend/src/components/AvatarPanel.tsx`
- Modify: `persona-agent-frontend/src/components/AvatarPanel.test.tsx`

**Interfaces:**
- Consumes: nothing new from backend beyond the message shapes Task 4 produces
- Produces: `PersonaSocket.sendAvatarPhoto(bytes: ArrayBuffer, contentType: string): void`, `PersonaSocket.onAvatarBaseImage: ((imageBase64: string) => void) | null`, updated `PersonaAttribute` interface (`domain`/`rank` instead of `priority`), `Persona.avatar_image: string | null`

- [ ] **Step 1: Read the current `PersonaSocket.ts` and `PersonaSocket.test.ts` in full**

These exist from the original plan (Task 8) and were already modified once during Task 9's human-check fix round (see this branch's git log for `ff683c8`) — read the current file, not an earlier version, before editing.

- [ ] **Step 2: Update `PersonaSocket.test.ts`**

Update the `PersonaAttribute`-shaped literal in the existing "displays the persona result" test (if present in this file — it may be in `AvatarPanel.test.tsx` instead, check both) to use `domain`/`rank` instead of `priority`. Add this new test to `PersonaSocket.test.ts`:

```typescript
  it("sends a base64 avatar_photo message with content_type", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();
    const photo = new Uint8Array([9, 9, 9]).buffer;

    socket.sendAvatarPhoto(photo, "image/png");

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sent.type).toBe("avatar_photo");
    expect(sent.content_type).toBe("image/png");
    expect(typeof sent.data).toBe("string");
  });

  it("calls onAvatarBaseImage when an avatar_base_image message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onAvatarBaseImage = vi.fn();
    socket.onAvatarBaseImage = onAvatarBaseImage;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({ data: JSON.stringify({ type: "avatar_base_image", data: "base64imagedata" }) });

    expect(onAvatarBaseImage).toHaveBeenCalledWith("base64imagedata");
  });
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd persona-agent-frontend && pnpm test`
Expected: FAIL — `sendAvatarPhoto` and `onAvatarBaseImage` don't exist yet.

- [ ] **Step 4: Update `PersonaSocket.ts`**

Change the `PersonaAttribute` interface to:

```typescript
export interface PersonaAttribute {
  domain: "mobility" | "dietary" | "purpose" | "companions" | "language" | "background" | "other";
  category: string;
  description: string;
  rank: number;
  confidence: "high" | "medium" | "low";
  inferred_keywords: string[];
}
```

Change the `Persona` interface to:

```typescript
export interface Persona {
  persona_id: string;
  raw_summary: string;
  attributes: PersonaAttribute[];
  avatar_image: string | null;
}
```

Add `onAvatarBaseImage: ((imageBase64: string) => void) | null = null;` as a class field alongside the existing `onPersonaResult`/`onAudioChunk` fields.

In `connect()`'s `onmessage` handler, add a new branch:

```typescript
        } else if (message.type === "avatar_base_image") {
          this.onAvatarBaseImage?.(message.data as string);
        }
```

(This is a third `else if` alongside the existing `persona_result` and `audio_chunk` branches — keep those as they are.)

Add this method to the class (alongside `sendAudioChunk`/`sendFinish`):

```typescript
  sendAvatarPhoto(photo: ArrayBuffer, contentType: string): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const base64 = btoa(String.fromCharCode(...new Uint8Array(photo)));
    this.ws.send(JSON.stringify({ type: "avatar_photo", data: base64, content_type: contentType }));
  }
```

- [ ] **Step 5: Run to verify `PersonaSocket.test.ts` passes**

Run: `cd persona-agent-frontend && pnpm test`
Expected: PASS

- [ ] **Step 6: Read the current `AvatarPanel.tsx` and `AvatarPanel.test.tsx` in full**

These were modified during the Task 9 human-check fix round (commits `02d1c1e`, `2f3dbb0`) — read the CURRENT file (with `audioPlayback`/`micCapture` wiring already in place), not the version from the original plan text.

- [ ] **Step 7: Update `AvatarPanel.test.tsx`**

Update the existing "displays the persona result" test's literal persona object to match the new `Persona` shape (`domain`/`rank` instead of `priority`, and an `avatar_image` field — use `avatar_image: null` for that existing test since it isn't testing the photo-upload path). Add these new tests:

```typescript
  it("shows a photo upload input before the conversation starts", () => {
    render(<AvatarPanel socket={new PersonaSocket("wss://example.test")} />);
    expect(screen.getByLabelText("顔写真をアップロード")).toBeInTheDocument();
  });

  it("sends the selected photo via socket.sendAvatarPhoto", async () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.sendAvatarPhoto = vi.fn();
    render(<AvatarPanel socket={socket} />);

    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText("顔写真をアップロード") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(socket.sendAvatarPhoto).toHaveBeenCalled();
    const [, contentType] = (socket.sendAvatarPhoto as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(contentType).toBe("image/png");
  });

  it("displays the avatar_base_image once received", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    act(() => {
      socket.onAvatarBaseImage?.("base64data");
    });

    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toBe("data:image/png;base64,base64data");
  });
```

`act` is already imported in this file from Task 9's fix round — confirm the import line includes it (`import { render, screen, fireEvent, act } from "@testing-library/react";`); add it if it's missing.

- [ ] **Step 8: Run to verify these new tests fail**

Run: `cd persona-agent-frontend && pnpm test`
Expected: FAIL — no photo upload input exists yet, no `onAvatarBaseImage` wiring, `img`'s `src` still points to the static SVGs.

- [ ] **Step 9: Update `AvatarPanel.tsx`**

Add a `baseAvatarImage` state and wire the upload input and `onAvatarBaseImage` callback. The exact diff depends on the current file's structure (post-Task-9 fixes) — read it first (Step 6), then apply these changes preserving everything already there (mic capture, audio playback, breathing/crossfade mouth logic):

1. Add `const [baseAvatarImage, setBaseAvatarImage] = useState<string | null>(null);` alongside the other `useState` calls.
2. Inside the existing `useEffect` that sets `socket.onPersonaResult`/`socket.onAudioChunk`, add:
   ```typescript
   socket.onAvatarBaseImage = (imageBase64) => setBaseAvatarImage(imageBase64);
   ```
3. Add a photo upload handler function:
   ```typescript
   const handlePhotoChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
     const file = event.target.files?.[0];
     if (!file) return;
     const buffer = await file.arrayBuffer();
     socket.sendAvatarPhoto(buffer, file.type);
   };
   ```
4. In the rendered JSX, add the file input (place it above the existing avatar `<img>`, wrapped so `getByLabelText` in the tests can find it):
   ```typescript
   <label>
     顔写真をアップロード
     <input type="file" accept="image/*" onChange={handlePhotoChange} />
   </label>
   ```
5. Change the avatar `<img>`'s `src` so that once a base avatar image has arrived, it's used instead of the static SVGs — the existing mouth-open/closed crossfade logic from Task 9's fixes still drives the *animation layer* on top; this only changes what the *base* picture is. If the current file already renders two stacked `<img>` layers for the crossfade (per the Task 9 breathing/crossfade fix), update BOTH layers' `src` to derive from `baseAvatarImage` when present:
   ```typescript
   const baseSrc = baseAvatarImage ? `data:image/png;base64,${baseAvatarImage}` : "/avatar-mouth-closed.svg";
   ```
   and use `baseSrc` wherever the closed-mouth image was previously hardcoded to `/avatar-mouth-closed.svg`. Leave the open-mouth crossfade layer pointing at the static `/avatar-mouth-open.svg` for now — evolving THAT layer to match a photo-personalized base is out of scope for this task (see this plan's Open Questions).

- [ ] **Step 10: Run to verify the tests pass**

Run: `cd persona-agent-frontend && pnpm test`
Expected: PASS (all tests, both files)

- [ ] **Step 11: Run the build**

Run: `cd persona-agent-frontend && pnpm run build`
Expected: succeeds (TypeScript type-checks and Vite build both pass)

- [ ] **Step 12: Commit**

```bash
git add persona-agent-frontend/src/
git commit -m "feat: add photo upload UI and wire avatar_base_image/domain+rank into AvatarPanel"
```

---

### Task 6: Human check — real photo, real YouCam call, real Nano Banana edit, end to end

**Files:** none (verification only)

- [ ] **Step 1: Start the backend with real credentials**

```bash
cd persona-agent-backend
export VERTEX_PROJECT_ID=<your project>
export VERTEX_LOCATION=us-central1
export PERFECTCORP_API_KEY=<your key>
export PERFECTCORP_API_SECRET=<your secret>
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8080
```

- [ ] **Step 2: Start the frontend**

```bash
cd persona-agent-frontend && pnpm run dev
```

- [ ] **Step 3: Human check — full flow with a real photo**

This step needs your eyes; it cannot be automated. Open the printed local URL. Upload a real photo of a face. **Tell me**: does a personalized avatar (styled per the YouCam template) appear within a reasonable wait (expect roughly 20-40 seconds based on this plan's verification run — tell me if it's dramatically longer)? Then have a short voice conversation and press 完了 — does the final avatar shown reflect at least one attribute you mentioned (e.g., a visible change matching something you said), and does the persona JSON's `attributes` each show a `domain` and a unique `rank`?

- [ ] **Step 4: Report back**

Tell me what you saw at each step, including anything that looked wrong, slow, or ugly. This step's outcome may require a fix round before this task can be marked complete.

---

## Open Questions (carried into the SDD ledger, not blocking)

- Only one Anime-category YouCam template (`female_manga_mood`) was found; it visibly restyles a male test photo into a female-presenting character. Whether to accept this as-is, search other YouCam categories for a better match, or fall back to a Nano-Banana-only base generation when the user's YouCam result looks wrong is a design call to make after Task 6's human check, informed by what actually renders.
- Task 5 Step 9 intentionally leaves the *open-mouth* crossfade layer as the old static SVG, not photo-personalized — fully replacing it with a YouCam/Nano-Banana-generated open-mouth variant of the personalized character is a natural follow-up but was scoped out here to keep this plan's tasks independently testable.
