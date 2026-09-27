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
            return_value=(
                Persona(persona_id="test-id", raw_summary="要約", attributes=[]),
                b"avatar-bytes",
                b"avatar-bytes-open",
            )
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
                "schema_version": "2",
                "avatar_image": base64.b64encode(b"avatar-bytes").decode("ascii"),
                "avatar_image_open": base64.b64encode(b"avatar-bytes-open").decode("ascii"),
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


def test_websocket_survives_malformed_audio_chunk_and_still_reaches_finish():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.send_audio = AsyncMock()
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="", attributes=[]), None, None)
        )

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json({"type": "audio_chunk", "data": "not-valid-base64!!!"})
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data["type"] == "persona_result"
        mock_conversation.send_audio.assert_not_called()


def test_websocket_survives_non_object_message_and_still_reaches_finish():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="", attributes=[]), None, None)
        )

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json(["not", "an", "object"])
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data["type"] == "persona_result"


def test_websocket_avatar_photo_sends_avatar_error_on_malformed_data():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()
        mock_conversation.set_base_photo = MagicMock()

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json({"type": "avatar_photo", "data": "not-valid-base64!!!"})
            data = websocket.receive_json()

        assert data["type"] == "avatar_error"
        mock_conversation.set_base_photo.assert_not_called()


def test_websocket_sends_start_error_and_closes_on_start_failure():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock(side_effect=RuntimeError("model not found"))

        with client.websocket_connect("/ws/converse") as websocket:
            data = websocket.receive_json()

        assert data == {"type": "start_error", "message": "model not found"}


def test_websocket_finish_still_succeeds_if_relay_task_already_crashed():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="", attributes=[]), None, None)
        )

        async def failing_receive_audio_chunks():
            raise RuntimeError("live api connection dropped")
            yield  # pragma: no cover - makes this an async generator

        mock_conversation.receive_audio_chunks = failing_receive_audio_chunks

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data["type"] == "persona_result"


def test_websocket_finish_flow_sends_finish_error_on_exception():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.finish = AsyncMock(side_effect=RuntimeError("gemini call failed"))

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data == {"type": "finish_error", "message": "gemini call failed"}


def test_websocket_avatar_photo_flow_calls_set_base_photo_and_relays_result():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()
        mock_conversation.set_base_photo = MagicMock(return_value=(b"base-avatar-bytes", b"base-avatar-bytes-open"))
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="要約", attributes=[]), None, None)
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
            "open_mouth_data": base64.b64encode(b"base-avatar-bytes-open").decode("ascii"),
        }
        mock_conversation.set_base_photo.assert_called_once_with(photo_bytes=b"photo-bytes", content_type="image/png")


def test_websocket_avatar_photo_flow_survives_youcam_failure():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()
        mock_conversation.set_base_photo = MagicMock(side_effect=RuntimeError("no face detected"))
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="要約", attributes=[]), None, None)
        )

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover - makes this an async generator with no items

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with client.websocket_connect("/ws/converse") as websocket:
            websocket.send_json(
                {"type": "avatar_photo", "data": base64.b64encode(b"photo-bytes").decode("ascii"), "content_type": "image/png"}
            )
            error_data = websocket.receive_json()
            websocket.send_json({"type": "finish"})
            finish_data = websocket.receive_json()

        assert error_data == {"type": "avatar_error", "message": "no face detected"}
        assert finish_data["type"] == "persona_result"
        mock_conversation.set_base_photo.assert_called_once()
