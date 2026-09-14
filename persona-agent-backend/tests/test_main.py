import base64
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from main import app
from schemas import Persona

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"service": "persona-agent-backend", "status": "healthy"}


# NOTE: the previous echo-based test_websocket_echoes_text_messages test was
# removed in Task 6. The /ws/converse handler now wires a real
# LiveConversation (Gemini Live API session) instead of echoing messages
# back, so that behavior no longer applies. See tests/test_live_session.py
# for coverage of LiveConversation itself. The two tests below cover the
# handler's own branching (audio_chunk vs finish) with LiveConversation and
# the genai client mocked out, so no real Gemini/env-var dependency is
# needed.


def test_websocket_finish_flow_calls_live_conversation():
    with patch("main._build_genai_client") as mock_build_client, patch(
        "main.LiveConversation"
    ) as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="要約", attributes=[]), b"avatar-bytes")
        )

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data == {
            "type": "persona_result",
            "data": {
                "persona_id": "test-id",
                "raw_summary": "要約",
                "attributes": [],
                "avatar_image": base64.b64encode(b"avatar-bytes").decode("ascii"),
            },
        }
        mock_conversation.start.assert_called_once()
        mock_conversation.finish.assert_called_once()
        mock_build_client.assert_called_once()


def test_websocket_audio_chunk_flow_calls_live_conversation():
    with patch("main._build_genai_client"), patch(
        "main.LiveConversation"
    ) as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.send_audio = AsyncMock()
        mock_conversation.close = AsyncMock()

        async def fake_receive_audio_chunks():
            yield b"audio-bytes", None

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json(
                {"type": "audio_chunk", "data": base64.b64encode(b"input-bytes").decode("ascii")}
            )
            data = websocket.receive_json()

        assert data == {
            "type": "audio_chunk",
            "data": base64.b64encode(b"audio-bytes").decode("ascii"),
        }
        mock_conversation.send_audio.assert_called_once_with(b"input-bytes")


def test_websocket_avatar_photo_flow_calls_set_base_photo_and_relays_result():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()
        mock_conversation.set_base_photo = MagicMock(return_value=b"base-avatar-bytes")
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="要約", attributes=[]), None)
        )

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
