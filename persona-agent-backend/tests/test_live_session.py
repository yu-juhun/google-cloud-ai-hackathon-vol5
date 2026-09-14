from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from live_session import LiveConversation
from schemas import Persona


@pytest.mark.asyncio
async def test_finish_runs_extraction_then_keyword_inference():
    with patch("live_session.extract_persona") as mock_extract, patch(
        "live_session.infer_keywords"
    ) as mock_infer:
        mock_extract.return_value = MagicMock(attributes=[MagicMock()])
        mock_infer.return_value = MagicMock(persona_id="final-persona")

        conversation = LiveConversation(genai_client=MagicMock())
        conversation._transcript_parts = ["ユーザー: こんにちは", "モデル: こんにちは、ご旅行のご予定ですか？"]

        result, avatar_bytes = await conversation.finish()

        mock_extract.assert_called_once()
        mock_infer.assert_called_once_with(mock_extract.return_value, conversation.genai_client)
        assert result.persona_id == "final-persona"
        assert avatar_bytes is None


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
