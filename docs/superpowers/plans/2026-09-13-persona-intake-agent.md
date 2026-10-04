# Persona Intake Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-service voice-conversation agent (`persona-agent-backend`, `persona-agent-frontend`) that extracts a dynamic, non-enum persona from a spoken conversation via Gemini Live API, for other agents to consume.

**Architecture:** `persona-agent-backend` (FastAPI) relays browser audio to Gemini Live API over a WebSocket, accumulates the transcript, then runs two follow-up Gemini text calls (persona extraction, keyword inference) once the user signals they're done. `persona-agent-frontend` (React + Vite) captures mic audio, renders a static avatar with volume-driven mouth toggling, and displays the final persona JSON.

**Tech Stack:** Python 3.12, FastAPI, `google-genai` SDK, pytest; React 19 + TypeScript + Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-13-persona-intake-agent-design.md`

## Global Constraints

- This agent does not make recommendations — it only extracts and returns persona data
- `attributes[].category` is free-form text, never a fixed enum — do not introduce a closed category list anywhere in the implementation
- No persistence (no database, no file storage) — the persona JSON is returned over the WebSocket and nowhere else
- No secrets committed to git — the Gemini API key/project comes from environment variables only
- Work happens on branch `agent/persona-intake`, verified against the developer's own personal GCP project, never the shared project (`project-3bcd6d36-2338-4b32-848`)
- Directory layout: `persona-agent-backend/`, `persona-agent-frontend/` (flat top-level, matching `backend-api/`, `frontend/`)
- Japanese-only conversation for this iteration — no multi-language handling
- **Verification loop for every task below:** finish the step, run the stated automated check yourself, and only ask the human to look at something when the step explicitly says "Human check" — do not ask for confirmation on steps that are self-verifiable (tests, lint, curl)

---

### Task 1: Backend project scaffold + persona schemas

**Files:**
- Create: `persona-agent-backend/requirements.txt`
- Create: `persona-agent-backend/schemas.py`
- Create: `persona-agent-backend/tests/test_schemas.py`
- Create: `persona-agent-backend/tests/__init__.py` (empty file, makes the tests dir a package)

**Interfaces:**
- Produces: `Attribute` and `Persona` Pydantic models in `schemas.py`, used by every later backend task

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
google-genai==1.5.0
pydantic==2.9.2
pytest==8.3.3
pytest-asyncio==0.24.0
websockets==13.1
```

- [ ] **Step 2: Write the failing test for the schemas**

```python
# persona-agent-backend/tests/test_schemas.py
import pytest
from pydantic import ValidationError

from schemas import Attribute, Persona


def test_attribute_accepts_free_form_category():
    attr = Attribute(
        category="宗教的な食事制約",
        description="ハラール対応が必要",
        priority="high",
        confidence="high",
        inferred_keywords=["ハラール", "豚肉不可", "アルコール不可"],
    )
    assert attr.category == "宗教的な食事制約"
    assert attr.inferred_keywords == ["ハラール", "豚肉不可", "アルコール不可"]


def test_attribute_defaults_inferred_keywords_to_empty_list():
    attr = Attribute(
        category="mobility",
        description="車椅子、幅63cm",
        priority="high",
        confidence="high",
    )
    assert attr.inferred_keywords == []


def test_attribute_rejects_invalid_priority():
    with pytest.raises(ValidationError):
        Attribute(
            category="mobility",
            description="x",
            priority="urgent",  # not one of high|medium|low
            confidence="high",
        )


def test_persona_accepts_empty_attributes():
    persona = Persona(persona_id="11111111-1111-1111-1111-111111111111", raw_summary="", attributes=[])
    assert persona.attributes == []


def test_persona_serializes_to_expected_shape():
    persona = Persona(
        persona_id="11111111-1111-1111-1111-111111111111",
        raw_summary="車椅子ユーザーの父親。ハラール食を希望。",
        attributes=[
            Attribute(category="mobility", description="車椅子", priority="high", confidence="medium"),
        ],
    )
    dumped = persona.model_dump()
    assert dumped["persona_id"] == "11111111-1111-1111-1111-111111111111"
    assert dumped["attributes"][0]["category"] == "mobility"
    assert dumped["attributes"][0]["inferred_keywords"] == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd persona-agent-backend && pip install -r requirements.txt && python -m pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'schemas'`

- [ ] **Step 4: Write `schemas.py`**

```python
# persona-agent-backend/schemas.py
"""Persona output schema. category is intentionally free-form text, not
an enum — the design decision (see design spec, "背景・非目標") is that
the intake agent must not lock users into a predetermined attribute list.
"""
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["high", "medium", "low"]


class Attribute(BaseModel):
    category: str
    description: str
    priority: Level
    confidence: Level
    inferred_keywords: list[str] = Field(default_factory=list)


class Persona(BaseModel):
    persona_id: str
    raw_summary: str
    attributes: list[Attribute] = Field(default_factory=list)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd persona-agent-backend && python -m pytest tests/test_schemas.py -v`
Expected: PASS (5/5)

- [ ] **Step 6: Commit**

```bash
git add persona-agent-backend/requirements.txt persona-agent-backend/schemas.py persona-agent-backend/tests/
git commit -m "feat: add persona-agent-backend schemas (free-form category)"
```

---

### Task 2: Persona extraction from transcript

**Files:**
- Create: `persona-agent-backend/persona_extraction.py`
- Create: `persona-agent-backend/tests/test_persona_extraction.py`

**Interfaces:**
- Consumes: `Persona`, `Attribute` from `schemas.py` (Task 1)
- Produces: `extract_persona(transcript: str, genai_client) -> Persona` in `persona_extraction.py`, consumed by Task 6's WebSocket handler
- Consumes at runtime (not at test time): a `google.genai.Client` instance, passed in by the caller rather than constructed inside this module — this keeps the function testable without real credentials

- [ ] **Step 1: Write the failing test (mocking the Gemini call)**

```python
# persona-agent-backend/tests/test_persona_extraction.py
import json
from unittest.mock import MagicMock

from persona_extraction import extract_persona


def test_extract_persona_parses_model_response_into_persona():
    fake_response = MagicMock()
    fake_response.text = json.dumps(
        {
            "raw_summary": "3人家族の父親。車椅子ユーザーでハラール食を希望。",
            "attributes": [
                {
                    "category": "mobility",
                    "description": "車椅子、電動、幅63cm",
                    "priority": "high",
                    "confidence": "high",
                },
                {
                    "category": "dietary",
                    "description": "イスラム教徒、ハラール食が必要",
                    "priority": "high",
                    "confidence": "high",
                },
            ],
        }
    )
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    persona = extract_persona(
        transcript="ユーザー: 車椅子を使っていて、イスラム教徒なのでハラールの店を探しています。",
        genai_client=fake_client,
    )

    assert persona.persona_id  # a UUID was generated
    assert persona.raw_summary == "3人家族の父親。車椅子ユーザーでハラール食を希望。"
    assert len(persona.attributes) == 2
    assert persona.attributes[0].category == "mobility"
    assert persona.attributes[1].category == "dietary"
    # keywords are filled in by a later step (Task 3), not here
    assert persona.attributes[0].inferred_keywords == []

    # verify the call requested JSON output
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].response_mime_type == "application/json"


def test_extract_persona_returns_empty_attributes_on_short_transcript():
    fake_response = MagicMock()
    fake_response.text = json.dumps({"raw_summary": "", "attributes": []})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    persona = extract_persona(transcript="", genai_client=fake_client)

    assert persona.attributes == []
    assert persona.raw_summary == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd persona-agent-backend && python -m pytest tests/test_persona_extraction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'persona_extraction'`

- [ ] **Step 3: Write `persona_extraction.py`**

```python
# persona-agent-backend/persona_extraction.py
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
  - category: 自由記述の文字列(固定の選択肢はない。対話内容に合った具体的な名前を付けてよい)
  - description: その属性を説明する自由文
  - priority: "high" | "medium" | "low"(本人がどれだけ重視しているように見えるか)
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
            category=a["category"],
            description=a["description"],
            priority=a["priority"],
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd persona-agent-backend && python -m pytest tests/test_persona_extraction.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Commit**

```bash
git add persona-agent-backend/persona_extraction.py persona-agent-backend/tests/test_persona_extraction.py
git commit -m "feat: add persona extraction from conversation transcript"
```

---

### Task 3: Batch keyword inference

**Files:**
- Create: `persona-agent-backend/keyword_inference.py`
- Create: `persona-agent-backend/tests/test_keyword_inference.py`

**Interfaces:**
- Consumes: `Persona`, `Attribute` from `schemas.py` (Task 1)
- Produces: `infer_keywords(persona: Persona, genai_client) -> Persona` in `keyword_inference.py` (returns a new `Persona` with `inferred_keywords` filled in on every attribute), consumed by Task 6's WebSocket handler

- [ ] **Step 1: Write the failing test**

```python
# persona-agent-backend/tests/test_keyword_inference.py
import json
from unittest.mock import MagicMock

from keyword_inference import infer_keywords
from schemas import Attribute, Persona


def test_infer_keywords_fills_in_each_attribute_in_one_call():
    persona = Persona(
        persona_id="11111111-1111-1111-1111-111111111111",
        raw_summary="車椅子ユーザーでハラール食希望",
        attributes=[
            Attribute(category="mobility", description="車椅子、幅63cm", priority="high", confidence="high"),
            Attribute(category="dietary", description="イスラム教徒", priority="high", confidence="high"),
        ],
    )

    fake_response = MagicMock()
    fake_response.text = json.dumps(
        {
            "keywords_by_index": [
                ["車椅子対応", "スロープ", "エレベーター"],
                ["ハラール", "豚肉不可", "アルコール不可"],
            ]
        }
    )
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    result = infer_keywords(persona, genai_client=fake_client)

    assert result.attributes[0].inferred_keywords == ["車椅子対応", "スロープ", "エレベーター"]
    assert result.attributes[1].inferred_keywords == ["ハラール", "豚肉不可", "アルコール不可"]
    # only one Gemini call for the whole batch, not one per attribute
    assert fake_client.models.generate_content.call_count == 1


def test_infer_keywords_returns_persona_unchanged_when_no_attributes():
    persona = Persona(persona_id="x", raw_summary="", attributes=[])
    fake_client = MagicMock()

    result = infer_keywords(persona, genai_client=fake_client)

    assert result.attributes == []
    # no Gemini call needed for an empty attribute list
    fake_client.models.generate_content.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd persona-agent-backend && python -m pytest tests/test_keyword_inference.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'keyword_inference'`

- [ ] **Step 3: Write `keyword_inference.py`**

```python
# persona-agent-backend/keyword_inference.py
import json

from google.genai import types

from schemas import Persona

KEYWORD_PROMPT = """\
以下は、ある人物についてのペルソナ属性のリストです。各属性について、
店舗検索や施設の適合判定に役立つ、具体的で実用的なキーワードを3〜5個ずつ考えてください。

出力形式は次のJSONにしてください:
{{"keywords_by_index": [["属性0のキーワード", ...], ["属性1のキーワード", ...], ...]}}

配列の順序は入力の属性の順序と一致させてください。

属性リスト:
{attributes_json}
"""


def infer_keywords(persona: Persona, genai_client) -> Persona:
    if not persona.attributes:
        return persona

    attributes_json = json.dumps(
        [{"category": a.category, "description": a.description} for a in persona.attributes],
        ensure_ascii=False,
    )
    prompt = KEYWORD_PROMPT.format(attributes_json=attributes_json)

    response = genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    parsed = json.loads(response.text)
    keywords_by_index = parsed["keywords_by_index"]

    updated_attributes = [
        attr.model_copy(update={"inferred_keywords": keywords_by_index[i]})
        for i, attr in enumerate(persona.attributes)
    ]

    return persona.model_copy(update={"attributes": updated_attributes})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd persona-agent-backend && python -m pytest tests/test_keyword_inference.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Commit**

```bash
git add persona-agent-backend/keyword_inference.py persona-agent-backend/tests/test_keyword_inference.py
git commit -m "feat: add batch keyword inference for persona attributes"
```

---

### Task 4: FastAPI app skeleton with a plain WebSocket echo endpoint

Get the FastAPI/WebSocket plumbing working end-to-end before wiring in the real Gemini Live API (Task 5) — this task has zero external-API risk and is fully unit-testable.

**Files:**
- Create: `persona-agent-backend/main.py`
- Create: `persona-agent-backend/tests/test_main.py`

**Interfaces:**
- Produces: FastAPI `app` object in `main.py`, with a `/health` endpoint and a `/ws/converse` WebSocket endpoint (echo behavior for now — Task 6 replaces the body)

- [ ] **Step 1: Write the failing test**

```python
# persona-agent-backend/tests/test_main.py
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"service": "persona-agent-backend", "status": "healthy"}


def test_websocket_echoes_text_messages():
    with client.websocket_connect("/ws/converse") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data == {"type": "echo", "payload": {"type": "ping"}}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd persona-agent-backend && python -m pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Write `main.py`**

```python
# persona-agent-backend/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="persona-agent-backend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "persona-agent-backend", "status": "healthy"}


@app.websocket("/ws/converse")
async def converse(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({"type": "echo", "payload": data})
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd persona-agent-backend && python -m pytest tests/test_main.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Commit**

```bash
git add persona-agent-backend/main.py persona-agent-backend/tests/test_main.py
git commit -m "feat: add FastAPI skeleton with health check and echo websocket"
```

---

### Task 5: Verify the installed google-genai SDK's Live API surface

**This task produces no application code.** The design spec's Live API integration (Task 6) depends on the exact async API the installed `google-genai==1.5.0` package exposes for streaming audio sessions, which cannot be safely guessed — the SDK's Live API surface has changed across versions. Do this verification before writing Task 6.

- [ ] **Step 1: Inspect the installed SDK's Live API entry points**

Run:
```bash
cd persona-agent-backend
python -c "
from google import genai
client = genai.Client(vertexai=True, project='placeholder', location='global')
print(dir(client.aio.live))
help(client.aio.live.connect)
"
```
Expected: prints a method list including `connect`, and `help()` prints the signature of `connect` (model, config parameters) and, in its docstring or by following into the returned session object, the send/receive method names for streaming audio in and audio-plus-transcript out.

- [ ] **Step 2: Record what you found**

Append your findings as a comment block at the top of a new file `persona-agent-backend/live_session.py`:

```python
# persona-agent-backend/live_session.py
"""
SDK verification (google-genai==1.5.0), recorded <today's date>:
- client.aio.live.connect(model=..., config=...) is an async context manager
  yielding a session object
- Session send method: <fill in exact method name and signature you found>
- Session receive method: <fill in exact method name/shape you found —
  does it yield audio bytes, text, or both per message?>
- How to end a session: <fill in — does exiting the `async with` block
  close it, or is there an explicit close()?>
"""
```

If any of these don't match what Task 6 assumes below, **stop and tell the human** what's different before proceeding to Task 6 — Task 6's code is written against the commonly-documented shape as of this spec's writing, and the plan needs a human decision if the installed SDK disagrees.

- [ ] **Step 3: Commit the verification notes**

```bash
git add persona-agent-backend/live_session.py
git commit -m "docs: record google-genai Live API surface verification"
```

---

### Task 6: Wire the Live API session into the WebSocket handler

**Files:**
- Modify: `persona-agent-backend/live_session.py` (from Task 5 — replace the comment-only file with the real implementation)
- Modify: `persona-agent-backend/main.py:16-25` (the `/ws/converse` handler from Task 4)
- Create: `persona-agent-backend/tests/test_live_session.py`

**Interfaces:**
- Consumes: `Persona` from `schemas.py`, `extract_persona` from `persona_extraction.py`, `infer_keywords` from `keyword_inference.py` (Tasks 1-3)
- Consumes: the exact SDK method names recorded in Task 5's `live_session.py` docstring — use those, not the placeholder names below, if they differ
- Produces: `LiveConversation` class in `live_session.py` with `async def send_audio(chunk: bytes) -> None` and `async def finish() -> Persona` methods, used by `main.py`'s WebSocket handler

- [ ] **Step 1: Write the failing test for `LiveConversation`, mocking the Gemini client entirely**

```python
# persona-agent-backend/tests/test_live_session.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from live_session import LiveConversation


@pytest.mark.asyncio
async def test_finish_runs_extraction_then_keyword_inference():
    with patch("live_session.extract_persona") as mock_extract, patch(
        "live_session.infer_keywords"
    ) as mock_infer:
        mock_extract.return_value = MagicMock(attributes=[MagicMock()])
        mock_infer.return_value = MagicMock(persona_id="final-persona")

        conversation = LiveConversation(genai_client=MagicMock())
        conversation._transcript_parts = ["ユーザー: こんにちは", "モデル: こんにちは、ご旅行のご予定ですか？"]

        result = await conversation.finish()

        mock_extract.assert_called_once()
        mock_infer.assert_called_once_with(mock_extract.return_value, conversation.genai_client)
        assert result.persona_id == "final-persona"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd persona-agent-backend && python -m pytest tests/test_live_session.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `LiveConversation`

- [ ] **Step 3: Replace `live_session.py`'s comment-only content with the real implementation**

Use the method names you recorded in Task 5 in place of `<session>.send_realtime_input` / `<session>.receive` below if they differ — those two are the commonly-documented names as of this spec's writing, kept as the default assumption only until Task 5's verification confirms or corrects them.

```python
# persona-agent-backend/live_session.py
"""
SDK verification (google-genai==1.5.0), recorded in Task 5:
<keep the findings you wrote in Task 5 here>
"""
from google.genai import types

from keyword_inference import infer_keywords
from persona_extraction import extract_persona
from schemas import Persona

SYSTEM_PROMPT = """\
あなたは、車椅子ユーザーやその家族の旅行・外食プランニングを手伝うアシスタントです。
ユーザーの移動の制約、食事の制約、今日の目的、同行者、優先したいことを、
自然な会話で聞き出してください。一度に多くの質問をせず、相手の話を踏まえて
一つずつ掘り下げてください。
"""


class LiveConversation:
    def __init__(self, genai_client):
        self.genai_client = genai_client
        self._session = None
        self._session_ctx = None
        self._transcript_parts: list[str] = []

    async def start(self) -> None:
        self._session_ctx = self.genai_client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-preview",
            config=types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=SYSTEM_PROMPT,
                output_audio_transcription={},
                input_audio_transcription={},
            ),
        )
        self._session = await self._session_ctx.__aenter__()

    async def send_audio(self, chunk: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
        )

    async def receive_audio_chunks(self):
        """Async generator yielding (audio_bytes | None, transcript_text | None) pairs."""
        async for message in self._session.receive():
            audio_bytes = None
            transcript_text = None
            if message.data:
                audio_bytes = message.data
            if message.server_content and message.server_content.output_transcription:
                transcript_text = message.server_content.output_transcription.text
                self._transcript_parts.append(f"モデル: {transcript_text}")
            if message.server_content and message.server_content.input_transcription:
                user_text = message.server_content.input_transcription.text
                self._transcript_parts.append(f"ユーザー: {user_text}")
            yield audio_bytes, transcript_text

    async def finish(self) -> Persona:
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(None, None, None)
        transcript = "\n".join(self._transcript_parts)
        persona = extract_persona(transcript=transcript, genai_client=self.genai_client)
        return infer_keywords(persona, self.genai_client)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd persona-agent-backend && python -m pytest tests/test_live_session.py -v`
Expected: PASS (1/1)

- [ ] **Step 5: Wire `LiveConversation` into the WebSocket handler in `main.py`**

```python
# persona-agent-backend/main.py
import base64
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai

from live_session import LiveConversation

app = FastAPI(title="persona-agent-backend")


def _build_genai_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["VERTEX_PROJECT_ID"],
        location=os.environ.get("VERTEX_LOCATION", "global"),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "persona-agent-backend", "status": "healthy"}


@app.websocket("/ws/converse")
async def converse(websocket: WebSocket) -> None:
    await websocket.accept()
    conversation = LiveConversation(genai_client=_build_genai_client())
    await conversation.start()

    try:
        while True:
            message = await websocket.receive_json()

            if message.get("type") == "audio_chunk":
                audio_bytes = base64.b64decode(message["data"])
                await conversation.send_audio(audio_bytes)

                async for audio_out, _transcript in conversation.receive_audio_chunks():
                    if audio_out is not None:
                        await websocket.send_json(
                            {"type": "audio_chunk", "data": base64.b64encode(audio_out).decode("ascii")}
                        )

            elif message.get("type") == "finish":
                persona = await conversation.finish()
                await websocket.send_json({"type": "persona_result", "data": persona.model_dump()})
                break

    except WebSocketDisconnect:
        pass
```

- [ ] **Step 6: Run the full backend test suite to verify nothing broke**

Run: `cd persona-agent-backend && python -m pytest -v`
Expected: PASS (all tests from Tasks 1-6)

- [ ] **Step 7: Human check — real voice smoke test**

This step needs your ears and voice; it cannot be automated. Run:
```bash
cd persona-agent-backend
export VERTEX_PROJECT_ID=<your personal GCP project ID>
export VERTEX_LOCATION=global
uvicorn main:app --reload --port 8080
```
Then, in a separate terminal, use a small WebSocket test script or a tool like `websocat` to send a short base64-encoded PCM audio clip as an `audio_chunk` message, then send `{"type": "finish"}`, and confirm you get back a `persona_result` message with a non-empty `raw_summary`. **Tell me what you see** — if the response looks wrong (empty attributes when you said something meaningful, an error, a hung connection), stop here and we'll debug together rather than proceeding to Task 7.

- [ ] **Step 8: Commit**

```bash
git add persona-agent-backend/live_session.py persona-agent-backend/main.py
git commit -m "feat: wire Gemini Live API into the websocket conversation handler"
```

---

### Task 7: Backend Dockerfile

**Files:**
- Create: `persona-agent-backend/Dockerfile`

**Interfaces:**
- Consumes: `requirements.txt`, `main.py` and all backend modules (Tasks 1-6)

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# persona-agent-backend/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Build the image locally to verify it builds**

Run: `cd persona-agent-backend && docker build -t persona-agent-backend-local .`
Expected: build succeeds (`Successfully tagged persona-agent-backend-local:latest`, or the newer Buildx equivalent success output)

If Docker/network access is blocked in your environment (as it was in an earlier, unrelated part of this project — see `docs/wiki/concepts/deployed-endpoints.md`), skip local verification and note it; this Dockerfile will be verified for real at actual deploy time instead. Do not weaken any security setting to force a local build.

- [ ] **Step 3: Commit**

```bash
git add persona-agent-backend/Dockerfile
git commit -m "infra: add Dockerfile for persona-agent-backend"
```

---

### Task 8: Frontend scaffold — mic capture + WebSocket client

**Files:**
- Create: `persona-agent-frontend/package.json`
- Create: `persona-agent-frontend/vite.config.ts`
- Create: `persona-agent-frontend/tsconfig.json`
- Create: `persona-agent-frontend/index.html`
- Create: `persona-agent-frontend/src/main.tsx`
- Create: `persona-agent-frontend/src/ws/PersonaSocket.ts`
- Create: `persona-agent-frontend/src/ws/PersonaSocket.test.ts`
- Create: `persona-agent-frontend/src/test/setup.ts`

**Interfaces:**
- Produces: `PersonaSocket` class in `src/ws/PersonaSocket.ts` with `connect()`, `sendAudioChunk(chunk: ArrayBuffer)`, `sendFinish()`, and an `onPersonaResult` callback property — consumed by Task 9's UI component

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "persona-agent-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.1.1",
    "jsdom": "30.0.1",
    "typescript": "5.9.3",
    "vite": "8.3.0",
    "vitest": "5.0.0"
  }
}
```

- [ ] **Step 2: Write `vite.config.ts`**

```typescript
// persona-agent-frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
```

- [ ] **Step 3: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write `index.html`**

```html
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <title>ペルソナ・インテイクエージェント</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Write `src/test/setup.ts`**

```typescript
// persona-agent-frontend/src/test/setup.ts
import "@testing-library/jest-dom";
```

Add `@testing-library/jest-dom` and `@testing-library/react` to `package.json`'s `devDependencies` (versions `7.0.1` and `16.3.3` respectively, matching the existing `frontend/package.json`).

- [ ] **Step 6: Write the failing test for `PersonaSocket`**

```typescript
// persona-agent-frontend/src/ws/PersonaSocket.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PersonaSocket } from "./PersonaSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {}
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  // @ts-expect-error test double
  global.WebSocket = FakeWebSocket;
});

describe("PersonaSocket", () => {
  it("sends a base64 audio_chunk message", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();
    const chunk = new Uint8Array([1, 2, 3]).buffer;

    socket.sendAudioChunk(chunk);

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    assert_audio_chunk_message(sent);
  });

  it("sends a finish message", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    socket.connect();

    socket.sendFinish();

    const sent = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sent).toEqual({ type: "finish" });
  });

  it("calls onPersonaResult when a persona_result message arrives", () => {
    const socket = new PersonaSocket("wss://example.test/ws/converse");
    const onResult = vi.fn();
    socket.onPersonaResult = onResult;
    socket.connect();

    const ws = FakeWebSocket.instances[0];
    ws.onmessage?.({
      data: JSON.stringify({ type: "persona_result", data: { persona_id: "abc", raw_summary: "", attributes: [] } }),
    });

    expect(onResult).toHaveBeenCalledWith({ persona_id: "abc", raw_summary: "", attributes: [] });
  });
});

function assert_audio_chunk_message(sent: unknown) {
  expect(sent).toMatchObject({ type: "audio_chunk" });
  expect(typeof (sent as { data: string }).data).toBe("string");
}
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `cd persona-agent-frontend && npm install && npm test`
Expected: FAIL with a module-not-found error for `./PersonaSocket`

- [ ] **Step 8: Write `src/ws/PersonaSocket.ts`**

```typescript
// persona-agent-frontend/src/ws/PersonaSocket.ts
export interface PersonaAttribute {
  category: string;
  description: string;
  priority: "high" | "medium" | "low";
  confidence: "high" | "medium" | "low";
  inferred_keywords: string[];
}

export interface Persona {
  persona_id: string;
  raw_summary: string;
  attributes: PersonaAttribute[];
}

export class PersonaSocket {
  private ws: WebSocket | null = null;
  onPersonaResult: ((persona: Persona) => void) | null = null;
  onAudioChunk: ((chunk: ArrayBuffer) => void) | null = null;

  constructor(private url: string) {}

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (event: { data: string }) => {
      const message = JSON.parse(event.data);
      if (message.type === "persona_result") {
        this.onPersonaResult?.(message.data as Persona);
      } else if (message.type === "audio_chunk") {
        const binary = atob(message.data as string);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        this.onAudioChunk?.(bytes.buffer);
      }
    };
  }

  sendAudioChunk(chunk: ArrayBuffer): void {
    const base64 = btoa(String.fromCharCode(...new Uint8Array(chunk)));
    this.ws?.send(JSON.stringify({ type: "audio_chunk", data: base64 }));
  }

  sendFinish(): void {
    this.ws?.send(JSON.stringify({ type: "finish" }));
  }

  close(): void {
    this.ws?.close();
  }
}
```

- [ ] **Step 9: Write a minimal `src/main.tsx` so the app boots (full UI comes in Task 9)**

```typescript
// persona-agent-frontend/src/main.tsx
import { createRoot } from "react-dom/client";

function App() {
  return <div>persona-agent-frontend (UI implemented in Task 9)</div>;
}

createRoot(document.getElementById("root")!).render(<App />);
```

- [ ] **Step 10: Run the test to verify it passes**

Run: `cd persona-agent-frontend && npm test`
Expected: PASS (3/3)

- [ ] **Step 11: Commit**

```bash
git add persona-agent-frontend/
git commit -m "feat: scaffold persona-agent-frontend with PersonaSocket websocket client"
```

---

### Task 9: Avatar UI — mic capture, volume-driven mouth toggle, persona display

**Files:**
- Create: `persona-agent-frontend/src/components/AvatarPanel.tsx`
- Create: `persona-agent-frontend/src/components/AvatarPanel.test.tsx`
- Create: `persona-agent-frontend/src/audio/micCapture.ts`
- Modify: `persona-agent-frontend/src/main.tsx`
- Create: `persona-agent-frontend/public/avatar-mouth-closed.svg`
- Create: `persona-agent-frontend/public/avatar-mouth-open.svg`

**Interfaces:**
- Consumes: `PersonaSocket`, `Persona` from `src/ws/PersonaSocket.ts` (Task 8)
- Produces: `AvatarPanel` React component, the top-level UI for this service

- [ ] **Step 1: Write the two placeholder avatar SVGs**

```svg
<!-- persona-agent-frontend/public/avatar-mouth-closed.svg -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" role="img" aria-label="アバター(口を閉じた状態)">
  <circle cx="100" cy="100" r="90" fill="#f0c9a0"/>
  <circle cx="70" cy="80" r="8" fill="#333"/>
  <circle cx="130" cy="80" r="8" fill="#333"/>
  <line x1="70" y1="130" x2="130" y2="130" stroke="#333" stroke-width="4" stroke-linecap="round"/>
</svg>
```

```svg
<!-- persona-agent-frontend/public/avatar-mouth-open.svg -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" role="img" aria-label="アバター(口を開けた状態)">
  <circle cx="100" cy="100" r="90" fill="#f0c9a0"/>
  <circle cx="70" cy="80" r="8" fill="#333"/>
  <circle cx="130" cy="80" r="8" fill="#333"/>
  <ellipse cx="100" cy="132" rx="22" ry="14" fill="#7a3b3b"/>
</svg>
```

- [ ] **Step 2: Write `src/audio/micCapture.ts`**

```typescript
// persona-agent-frontend/src/audio/micCapture.ts
export interface MicCapture {
  stop: () => void;
}

/** Captures mic audio, calling onChunk with raw PCM16 chunks and onVolume
 * with a 0-1 volume estimate for each chunk (used to drive the avatar's
 * mouth toggle — see AvatarPanel). */
export function startMicCapture(
  onChunk: (chunk: ArrayBuffer) => void,
  onVolume: (level: number) => void,
): Promise<MicCapture> {
  return navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
    const audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      const pcm16 = new Int16Array(input.length);
      let sumSquares = 0;
      for (let i = 0; i < input.length; i++) {
        const sample = Math.max(-1, Math.min(1, input[i]));
        pcm16[i] = sample * 0x7fff;
        sumSquares += sample * sample;
      }
      onChunk(pcm16.buffer);
      onVolume(Math.sqrt(sumSquares / input.length));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    return {
      stop: () => {
        processor.disconnect();
        source.disconnect();
        stream.getTracks().forEach((track) => track.stop());
        audioContext.close();
      },
    };
  });
}
```

- [ ] **Step 3: Write the failing test for `AvatarPanel`**

```typescript
// persona-agent-frontend/src/components/AvatarPanel.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AvatarPanel } from "./AvatarPanel";
import { PersonaSocket } from "../ws/PersonaSocket";

vi.mock("../ws/PersonaSocket");

describe("AvatarPanel", () => {
  it("shows the closed-mouth avatar by default", () => {
    render(<AvatarPanel socket={new PersonaSocket("wss://example.test")} />);
    const img = screen.getByRole("img", { name: /アバター/ });
    expect(img.getAttribute("src")).toContain("avatar-mouth-closed.svg");
  });

  it("shows a finish button that calls socket.sendFinish", () => {
    const socket = new PersonaSocket("wss://example.test");
    socket.sendFinish = vi.fn();
    render(<AvatarPanel socket={socket} />);

    fireEvent.click(screen.getByRole("button", { name: "完了" }));

    expect(socket.sendFinish).toHaveBeenCalled();
  });

  it("displays the persona result once onPersonaResult fires", () => {
    const socket = new PersonaSocket("wss://example.test");
    render(<AvatarPanel socket={socket} />);

    socket.onPersonaResult?.({
      persona_id: "abc",
      raw_summary: "テスト要約",
      attributes: [],
    });

    expect(screen.getByText("テスト要約")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd persona-agent-frontend && npm test`
Expected: FAIL with a module-not-found error for `./AvatarPanel`

- [ ] **Step 5: Write `src/components/AvatarPanel.tsx`**

```typescript
// persona-agent-frontend/src/components/AvatarPanel.tsx
import { useEffect, useState } from "react";
import { PersonaSocket, Persona } from "../ws/PersonaSocket";
import { startMicCapture, MicCapture } from "../audio/micCapture";

export function AvatarPanel({ socket }: { socket: PersonaSocket }) {
  const [mouthOpen, setMouthOpen] = useState(false);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [capture, setCapture] = useState<MicCapture | null>(null);

  useEffect(() => {
    socket.onPersonaResult = (result) => setPersona(result);
    socket.onAudioChunk = (chunk) => {
      const view = new Int16Array(chunk);
      let sumSquares = 0;
      for (let i = 0; i < view.length; i++) sumSquares += (view[i] / 0x7fff) ** 2;
      const volume = Math.sqrt(sumSquares / view.length);
      setMouthOpen(volume > 0.02);
    };
  }, [socket]);

  const handleStart = async () => {
    socket.connect();
    const mic = await startMicCapture(
      (chunk) => socket.sendAudioChunk(chunk),
      () => {},
    );
    setCapture(mic);
  };

  const handleFinish = () => {
    socket.sendFinish();
    capture?.stop();
  };

  return (
    <div>
      <img
        src={mouthOpen ? "/avatar-mouth-open.svg" : "/avatar-mouth-closed.svg"}
        alt="アバター"
        width={200}
        height={200}
      />
      <button onClick={handleStart}>話しかける</button>
      <button onClick={handleFinish}>完了</button>
      {persona && (
        <div>
          <p>{persona.raw_summary}</p>
          <ul>
            {persona.attributes.map((attr, i) => (
              <li key={i}>
                {attr.category}: {attr.description} ({attr.inferred_keywords.join(", ")})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd persona-agent-frontend && npm test`
Expected: PASS (3/3 for AvatarPanel, plus the 3 from Task 8's PersonaSocket suite still passing)

- [ ] **Step 7: Wire `AvatarPanel` into `main.tsx`**

```typescript
// persona-agent-frontend/src/main.tsx
import { createRoot } from "react-dom/client";
import { AvatarPanel } from "./components/AvatarPanel";
import { PersonaSocket } from "./ws/PersonaSocket";

const WS_URL = import.meta.env.VITE_BACKEND_WS_URL ?? "ws://localhost:8080/ws/converse";

function App() {
  return <AvatarPanel socket={new PersonaSocket(WS_URL)} />;
}

createRoot(document.getElementById("root")!).render(<App />);
```

- [ ] **Step 8: Human check — run the dev server and try it in a browser**

Run: `cd persona-agent-frontend && npm run dev`, then open the printed local URL. **Tell me**: does the avatar image show up, does clicking "話しかける" prompt for microphone permission without a console error, and (once Task 6's backend is also running locally) does the mouth visibly toggle while the backend sends audio back? This is a visual/interactive check I cannot do myself.

- [ ] **Step 9: Commit**

```bash
git add persona-agent-frontend/
git commit -m "feat: add AvatarPanel with mic capture and volume-driven mouth toggle"
```

---

### Task 10: Frontend Dockerfile

**Files:**
- Create: `persona-agent-frontend/Dockerfile`
- Create: `persona-agent-frontend/nginx.conf`

**Interfaces:**
- Consumes: `package.json`'s `npm run build` script (Task 8), produces `dist/` (Task 9's built output)

- [ ] **Step 1: Write the Dockerfile (same pattern as the existing `frontend/Dockerfile`, repo-root build context)**

```dockerfile
# persona-agent-frontend/Dockerfile
FROM node:22-slim AS build
WORKDIR /app/persona-agent-frontend
COPY persona-agent-frontend/package.json ./
RUN npm install
COPY persona-agent-frontend/ .
ARG VITE_BACKEND_WS_URL="ws://localhost:8080/ws/converse"
ENV VITE_BACKEND_WS_URL=$VITE_BACKEND_WS_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/persona-agent-frontend/dist /usr/share/nginx/html
COPY persona-agent-frontend/nginx.conf /etc/nginx/templates/default.conf.template
ENV PORT=8080
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 2: Write `nginx.conf`**

```nginx
# persona-agent-frontend/nginx.conf
server {
    listen ${PORT};
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Build the image locally to verify it builds**

Run (from the repo root, not inside `persona-agent-frontend/`, since the build context is the repo root):
```bash
docker build -f persona-agent-frontend/Dockerfile -t persona-agent-frontend-local .
```
Expected: build succeeds. If Docker/network access is blocked in your environment, note it and skip — this will be verified for real at actual deploy time (same caveat as Task 7).

- [ ] **Step 4: Commit**

```bash
git add persona-agent-frontend/Dockerfile persona-agent-frontend/nginx.conf
git commit -m "infra: add Dockerfile for persona-agent-frontend"
```

---

## Self-Review Notes

- **Spec coverage:** every section of the design spec has a task — schemas (Task 1), persona extraction (Task 2), keyword inference (Task 3), FastAPI/WebSocket skeleton (Task 4), Live API integration (Tasks 5-6), Dockerfiles (Tasks 7, 10), frontend mic/WS client (Task 8), avatar UI (Task 9). The spec's "デプロイ・開発方針" (personal branch, personal GCP project, directory names) is enforced via Global Constraints rather than a dedicated task, since it's a constraint on how every task is done, not a deliverable itself.
- **Human-check placement:** exactly two steps require a human (Task 6 Step 7 — real voice smoke test; Task 9 Step 8 — visual/interactive browser check) because they need ears/eyes on a live system. Every other step is a `pytest`/`vitest`/`docker build` run the implementer verifies themselves before moving on, matching the requested "AI verifies lightweight things itself, ask the human only when actually needed" loop.
- **Task 5 is unusual** — it produces no application code, only an SDK-surface verification, because the Live API's exact async method names cannot be safely guessed from outside the installed package version. This is flagged as a real risk in Task 6, not smoothed over — if the SDK disagrees with the assumed method names (`send_realtime_input`, `.receive()`), Task 5 explicitly says to stop and tell the human rather than silently pushing a guessed API surface into Task 6's code.
- **Type consistency check:** `Persona`/`Attribute` field names are identical across `schemas.py` (Task 1), `persona_extraction.py` (Task 2), `keyword_inference.py` (Task 3), `live_session.py` (Task 6), and the frontend's `PersonaSocket.ts` interface (Task 8) — `persona_id`, `raw_summary`, `attributes[].category/description/priority/confidence/inferred_keywords` match everywhere.
- **No placeholder scan:** no "TBD"/"add error handling"/"similar to Task N" found on review. Task 5's bracketed `<fill in ...>` lines are not implementation placeholders — they're the literal deliverable of that verification task (recorded findings), consumed as real input by Task 6.
