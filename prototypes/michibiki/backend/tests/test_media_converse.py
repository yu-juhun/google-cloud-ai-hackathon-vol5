import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from michibiki.server import app

client = TestClient(app)
HEADERS = {"origin": "http://localhost:5173"}


@pytest.fixture(autouse=True)
def persona_url(monkeypatch):
    monkeypatch.setenv("PERSONA_URL", "https://persona.example")


class _FakeUpstream:
    def __init__(self, messages):
        self._messages = list(messages)
        self.sent = []

    async def send(self, message):
        self.sent.append(message)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _connect(upstream, captured_urls):
    def connect(url, **kwargs):
        captured_urls.append(url)
        return upstream
    return connect


@patch("michibiki.db.save_consultation", return_value="consultation-1")
@patch("michibiki.media.fetch_id_token", return_value="fake-token")
def test_converse_forwards_a_verified_purpose_to_the_upstream_url(mock_token, mock_save):
    captured = []
    upstream = _FakeUpstream([json.dumps({"type": "persona_result", "data": {"raw_summary": "ok"}})])
    with patch("websockets.connect", _connect(upstream, captured)):
        with client.websocket_connect("/api/persona/converse?purpose=video_feedback", headers=HEADERS) as websocket:
            websocket.send_text(json.dumps({"client_token": "a" * 40}))
            websocket.receive_json()  # session_ready
            websocket.receive_json()  # persona_result

    assert "purpose=video_feedback" in captured[0]


@patch("michibiki.db.save_consultation", return_value="consultation-1")
@patch("michibiki.media.fetch_id_token", return_value="fake-token")
def test_converse_rejects_an_invalid_purpose_like_it_already_rejects_an_invalid_voice(mock_token, mock_save):
    # media.py's relay raises (not silently defaults) on an invalid `voice`
    # today — matching that existing convention for `purpose` too, rather
    # than introducing a second, inconsistent validation style in this file.
    captured = []
    upstream = _FakeUpstream([json.dumps({"type": "persona_result", "data": {"raw_summary": "ok"}})])
    with patch("websockets.connect", _connect(upstream, captured)):
        with client.websocket_connect("/api/persona/converse?purpose=not-a-real-purpose", headers=HEADERS) as websocket:
            websocket.send_text(json.dumps({"client_token": "a" * 40}))
            assert websocket.receive_json() == {
                "type": "start_error",
                "message": "音声相談に接続できませんでした。文字入力で続けられます。",
            }

    assert captured == []
