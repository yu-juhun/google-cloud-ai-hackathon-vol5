import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import main
from main import app
from schemas import Persona

client = TestClient(app)


from contextlib import contextmanager


@contextmanager
def connected(path="/ws/converse"):
    """Thin wrapper kept only so every test doesn't need touching if the
    connection handshake ever needs a preamble step again."""
    with client.websocket_connect(path) as websocket:
        yield websocket


def test_build_genai_client_reads_project_and_location_from_env(monkeypatch):
    monkeypatch.setenv("VERTEX_PROJECT_ID", "test-project")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")

    with patch("main.genai.Client") as mock_client_cls:
        main._build_genai_client()

    mock_client_cls.assert_called_once_with(vertexai=True, project="test-project", location="asia-northeast1")


def test_build_genai_client_defaults_location_to_us_central1(monkeypatch):
    monkeypatch.setenv("VERTEX_PROJECT_ID", "test-project")
    monkeypatch.delenv("VERTEX_LOCATION", raising=False)

    with patch("main.genai.Client") as mock_client_cls:
        main._build_genai_client()

    assert mock_client_cls.call_args.kwargs["location"] == "us-central1"


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

        with connected() as websocket:
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

        with connected() as websocket:
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

        with connected() as websocket:
            websocket.send_json({"type": "audio_chunk", "data": "not-valid-base64!!!"})
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data["type"] == "persona_result"
        mock_conversation.send_audio.assert_not_called()


def test_websocket_finish_cancels_a_still_running_relay_task():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="", attributes=[]), None, None)
        )

        async def blocking_receive_audio_chunks():
            # Never completes on its own — relay_task is still genuinely
            # in-flight when `finish` arrives, exercising the real
            # cancel()-then-await-raises-CancelledError path instead of
            # every other test's already-finished fake generator.
            await asyncio.Event().wait()
            yield  # pragma: no cover - unreachable

        mock_conversation.receive_audio_chunks = blocking_receive_audio_chunks

        with connected() as websocket:
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data["type"] == "persona_result"


def test_websocket_survives_invalid_json_text_and_still_reaches_finish():
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

        with connected() as websocket:
            websocket.send_text("this is not valid json{{{")
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data["type"] == "persona_result"


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

        with connected() as websocket:
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

        with connected() as websocket:
            websocket.send_json({"type": "avatar_photo", "data": "not-valid-base64!!!"})
            data = websocket.receive_json()

        assert data["type"] == "avatar_error"
        mock_conversation.set_base_photo.assert_not_called()


def test_avatar_templates_endpoint_allows_cross_origin_requests():
    # The frontend calls this from a different origin (a different dev
    # port, or a different Cloud Run service in prod) via plain fetch() —
    # without CORS headers the browser rejects the response outright
    # before the frontend ever sees a body, regardless of status code.
    import youcam_client

    youcam_client._template_catalog_cache = None
    response = client.get("/avatar-templates", headers={"Origin": "http://localhost:5173"})

    assert response.headers.get("access-control-allow-origin") == "*"


def test_avatar_templates_endpoint_is_plain_http_not_websocket():
    # Must not require connecting/starting a Live session at all — that's
    # the whole point of it being a separate GET endpoint (see its
    # docstring): the client needs this before choosing a voice, and
    # choosing a voice determines what a WebSocket connect() would do.
    import youcam_client

    youcam_client._template_catalog_cache = None
    response = client.get("/avatar-templates")

    assert response.status_code == 200
    body = response.json()
    assert "female" in body and "male" in body


def test_avatar_templates_endpoint_falls_back_when_catalog_file_is_missing(monkeypatch):
    import youcam_client

    monkeypatch.setattr(youcam_client, "_TEMPLATE_CATALOG_PATH", "/nonexistent/avatar_templates.json")
    youcam_client._template_catalog_cache = None

    response = client.get("/avatar-templates")

    ids = main.flatten_template_ids(response.json())
    assert ids == main.VERIFIED_TEMPLATE_IDS


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

        with connected() as websocket:
            websocket.send_json({"type": "finish"})
            data = websocket.receive_json()

        assert data["type"] == "persona_result"


def test_websocket_finish_flow_sends_finish_error_on_exception():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.finish = AsyncMock(side_effect=RuntimeError("gemini call failed"))

        with connected() as websocket:
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

        with connected() as websocket:
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
        mock_conversation.set_base_photo.assert_called_once_with(
            photo_bytes=b"photo-bytes", content_type="image/png", template_id=None
        )


def test_websocket_avatar_photo_forwards_a_verified_template_id():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()
        mock_conversation.set_base_photo = MagicMock(return_value=(b"a", b"b"))
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="", attributes=[]), None, None)
        )

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with connected() as websocket:
            websocket.send_json(
                {
                    "type": "avatar_photo",
                    "data": base64.b64encode(b"photo-bytes").decode("ascii"),
                    "template_id": "female_manga_mood",
                }
            )
            websocket.receive_json()
            websocket.send_json({"type": "finish"})

        mock_conversation.set_base_photo.assert_called_once_with(
            photo_bytes=b"photo-bytes", content_type="image/png", template_id="female_manga_mood"
        )


def test_websocket_avatar_photo_ignores_an_unverified_template_id():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()
        mock_conversation.set_base_photo = MagicMock(return_value=(b"a", b"b"))
        mock_conversation.finish = AsyncMock(
            return_value=(Persona(persona_id="test-id", raw_summary="", attributes=[]), None, None)
        )

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with connected() as websocket:
            websocket.send_json(
                {
                    "type": "avatar_photo",
                    "data": base64.b64encode(b"photo-bytes").decode("ascii"),
                    "template_id": "made_up_template",
                }
            )
            websocket.receive_json()
            websocket.send_json({"type": "finish"})

        mock_conversation.set_base_photo.assert_called_once_with(
            photo_bytes=b"photo-bytes", content_type="image/png", template_id=None
        )


def test_websocket_forwards_a_verified_voice_name_from_the_query_string():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with connected("/ws/converse?voice=Kore"):
            pass

        mock_conversation.start.assert_called_once_with(voice_name="Kore", purpose="trip_wish")


def test_websocket_forwards_a_verified_purpose_from_the_query_string():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with connected("/ws/converse?purpose=video_feedback"):
            pass

        mock_conversation.start.assert_called_once_with(voice_name=None, purpose="video_feedback")


def test_websocket_ignores_an_unverified_purpose_from_the_query_string():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with connected("/ws/converse?purpose=not-a-real-purpose"):
            pass

        mock_conversation.start.assert_called_once_with(voice_name=None, purpose="trip_wish")


def test_websocket_ignores_an_unverified_voice_name_from_the_query_string():
    with patch("main._build_genai_client"), patch("main.LiveConversation") as mock_live_conversation_cls:
        mock_conversation = mock_live_conversation_cls.return_value
        mock_conversation.start = AsyncMock()
        mock_conversation.close = AsyncMock()

        async def fake_receive_audio_chunks():
            return
            yield  # pragma: no cover

        mock_conversation.receive_audio_chunks = fake_receive_audio_chunks

        with connected("/ws/converse?voice=not-a-real-voice"):
            pass

        mock_conversation.start.assert_called_once_with(voice_name=None, purpose="trip_wish")


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

        with connected() as websocket:
            websocket.send_json(
                {"type": "avatar_photo", "data": base64.b64encode(b"photo-bytes").decode("ascii"), "content_type": "image/png"}
            )
            error_data = websocket.receive_json()
            websocket.send_json({"type": "finish"})
            finish_data = websocket.receive_json()

        assert error_data == {"type": "avatar_error", "message": "no face detected"}
        assert finish_data["type"] == "persona_result"
        mock_conversation.set_base_photo.assert_called_once()
