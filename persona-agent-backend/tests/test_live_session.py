from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from live_session import LiveConversation
from schemas import Attribute, Persona


@pytest.mark.asyncio
async def test_finish_runs_extraction_then_keyword_inference():
    with patch("live_session.extract_persona") as mock_extract, patch(
        "live_session.infer_keywords"
    ) as mock_infer, patch("live_session.evolve_avatar") as mock_evolve, patch(
        "live_session.get_default_avatar_closed", return_value=b"default-closed"
    ), patch("live_session.get_default_avatar_open", return_value=b"default-open"):
        mock_extract.return_value = MagicMock(attributes=[MagicMock()])
        mock_infer.return_value = MagicMock(persona_id="final-persona")
        mock_evolve.side_effect = lambda base_image_bytes, persona, genai_client, mime_type: base_image_bytes

        conversation = LiveConversation(genai_client=MagicMock())
        conversation._transcript_parts = ["ユーザー: こんにちは", "モデル: こんにちは、ご旅行のご予定ですか？"]

        result, avatar_bytes, avatar_bytes_open = await conversation.finish()

        mock_extract.assert_called_once()
        mock_infer.assert_called_once_with(mock_extract.return_value, conversation.genai_client)
        assert result.persona_id == "final-persona"
        assert avatar_bytes == b"default-closed"
        assert avatar_bytes_open == b"default-open"


def test_set_base_photo_calls_youcam_and_generates_open_mouth_variant(monkeypatch):
    import live_session

    monkeypatch.setattr(
        live_session,
        "generate_base_avatar",
        lambda photo_bytes, content_type: (b"youcam-avatar-bytes", "image/jpeg"),
    )
    monkeypatch.setattr(
        live_session,
        "generate_open_mouth_variant",
        lambda base_image_bytes, genai_client, mime_type: b"open-mouth-bytes",
    )

    conversation = live_session.LiveConversation(genai_client=MagicMock())
    closed, open_ = conversation.set_base_photo(photo_bytes=b"raw-photo", content_type="image/png")

    assert closed == b"youcam-avatar-bytes"
    assert open_ == b"open-mouth-bytes"
    assert conversation._base_avatar_image == b"youcam-avatar-bytes"
    assert conversation._base_avatar_image_open == b"open-mouth-bytes"
    assert conversation._base_avatar_content_type == "image/jpeg"


@pytest.mark.asyncio
async def test_finish_returns_persona_and_evolved_avatars(monkeypatch):
    import live_session

    fake_persona = Persona(persona_id="id", raw_summary="s", attributes=[])
    monkeypatch.setattr(live_session, "extract_persona", lambda transcript, genai_client: fake_persona)
    monkeypatch.setattr(live_session, "infer_keywords", lambda persona, genai_client: persona)

    def fake_evolve_avatar(base_image_bytes, persona, genai_client, mime_type):
        return b"evolved-" + base_image_bytes

    monkeypatch.setattr(live_session, "evolve_avatar", fake_evolve_avatar)

    conversation = live_session.LiveConversation(genai_client=MagicMock())
    conversation._session_ctx = None
    conversation._base_avatar_image = b"base-closed"
    conversation._base_avatar_image_open = b"base-open"
    conversation._base_avatar_content_type = "image/jpeg"

    persona, avatar_bytes, avatar_bytes_open = await conversation.finish()

    assert persona == fake_persona
    assert avatar_bytes == b"evolved-base-closed"
    assert avatar_bytes_open == b"evolved-base-open"


@pytest.mark.asyncio
async def test_finish_with_no_photo_evolves_the_default_avatar(monkeypatch):
    import live_session

    fake_persona = Persona(
        persona_id="id",
        raw_summary="s",
        attributes=[Attribute(domain="purpose", category="旅行", description="観光目的", rank=1, confidence="high")],
    )
    monkeypatch.setattr(live_session, "extract_persona", lambda transcript, genai_client: fake_persona)
    monkeypatch.setattr(live_session, "infer_keywords", lambda persona, genai_client: persona)
    monkeypatch.setattr(live_session, "get_default_avatar_closed", lambda: b"default-closed")
    monkeypatch.setattr(live_session, "get_default_avatar_open", lambda: b"default-open")

    def fake_evolve_avatar(base_image_bytes, persona, genai_client, mime_type):
        assert mime_type == live_session.DEFAULT_MIME_TYPE
        return b"evolved-" + base_image_bytes

    monkeypatch.setattr(live_session, "evolve_avatar", fake_evolve_avatar)

    conversation = live_session.LiveConversation(genai_client=MagicMock())
    conversation._session_ctx = None

    persona, avatar_bytes, avatar_bytes_open = await conversation.finish()

    assert avatar_bytes == b"evolved-default-closed"
    assert avatar_bytes_open == b"evolved-default-open"


class _FakeTranscriptMessage:
    def __init__(self, data=None, output_text=None, input_text=None):
        self.data = data
        if output_text is not None or input_text is not None:
            server_content = MagicMock()
            server_content.output_transcription = MagicMock(text=output_text) if output_text is not None else None
            server_content.input_transcription = MagicMock(text=input_text) if input_text is not None else None
            self.server_content = server_content
        else:
            self.server_content = None


class _FakeLiveSession:
    """A fake matching the real session's per-turn receive() shape: each
    call returns a fresh async generator covering exactly one turn (see
    receive_audio_chunks's own docstring on why the real SDK behaves this
    way)."""

    def __init__(self, turns):
        self._turns = turns
        self._call_count = 0

    async def receive(self):
        turn = self._turns[self._call_count]
        self._call_count += 1
        for message in turn:
            yield message


@pytest.mark.asyncio
async def test_receive_audio_chunks_yields_audio_and_appends_model_transcript():
    conversation = LiveConversation(genai_client=MagicMock())
    conversation._session = _FakeLiveSession([[_FakeTranscriptMessage(data=b"audio-out", output_text="こんにちは")]])

    gen = conversation.receive_audio_chunks()
    try:
        results = [await gen.__anext__()]
    finally:
        await gen.aclose()

    assert results == [(b"audio-out", "こんにちは")]
    assert conversation._transcript_parts == ["モデル: こんにちは"]


@pytest.mark.asyncio
async def test_receive_audio_chunks_appends_user_transcript():
    conversation = LiveConversation(genai_client=MagicMock())
    conversation._session = _FakeLiveSession([[_FakeTranscriptMessage(input_text="車椅子を使っています")]])

    gen = conversation.receive_audio_chunks()
    try:
        results = [await gen.__anext__()]
    finally:
        await gen.aclose()

    assert results == [(None, None)]
    assert conversation._transcript_parts == ["ユーザー: 車椅子を使っています"]


@pytest.mark.asyncio
async def test_receive_audio_chunks_calls_receive_again_for_the_next_turn():
    conversation = LiveConversation(genai_client=MagicMock())
    conversation._session = _FakeLiveSession(
        [
            [_FakeTranscriptMessage(output_text="ターン1")],
            [_FakeTranscriptMessage(output_text="ターン2")],
        ]
    )

    gen = conversation.receive_audio_chunks()
    try:
        results = [await gen.__anext__(), await gen.__anext__()]
    finally:
        await gen.aclose()

    assert results == [(None, "ターン1"), (None, "ターン2")]
    assert conversation._transcript_parts == ["モデル: ターン1", "モデル: ターン2"]
    assert conversation._session._call_count == 2


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session
        self.aexit_called_with = None

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        self.aexit_called_with = args


@pytest.mark.asyncio
async def test_start_connects_with_the_expected_model_and_stores_the_session():
    fake_session = MagicMock()
    fake_ctx = _FakeSessionContext(fake_session)
    fake_client = MagicMock()
    fake_client.aio.live.connect.return_value = fake_ctx

    conversation = LiveConversation(genai_client=fake_client)
    await conversation.start()

    assert conversation._session is fake_session
    assert conversation._session_ctx is fake_ctx
    call_kwargs = fake_client.aio.live.connect.call_args.kwargs
    assert call_kwargs["model"] == "gemini-live-2.5-flash-native-audio"


@pytest.mark.asyncio
async def test_send_audio_sends_a_realtime_pcm_blob():
    conversation = LiveConversation(genai_client=MagicMock())
    conversation._session = MagicMock()
    conversation._session.send_realtime_input = AsyncMock()

    await conversation.send_audio(b"pcm-bytes")

    call_kwargs = conversation._session.send_realtime_input.call_args.kwargs
    assert call_kwargs["audio"].data == b"pcm-bytes"
    assert call_kwargs["audio"].mime_type == "audio/pcm;rate=16000"


@pytest.mark.asyncio
async def test_close_exits_the_session_context_and_clears_it():
    fake_ctx = _FakeSessionContext(MagicMock())
    conversation = LiveConversation(genai_client=MagicMock())
    conversation._session_ctx = fake_ctx

    await conversation.close()

    assert fake_ctx.aexit_called_with == (None, None, None)
    assert conversation._session_ctx is None


@pytest.mark.asyncio
async def test_close_is_a_noop_when_never_started():
    conversation = LiveConversation(genai_client=MagicMock())

    await conversation.close()  # must not raise

    assert conversation._session_ctx is None
