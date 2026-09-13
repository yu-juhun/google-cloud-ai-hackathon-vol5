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
