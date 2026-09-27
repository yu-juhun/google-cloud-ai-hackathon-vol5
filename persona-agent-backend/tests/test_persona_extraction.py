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
                    "domain": "mobility",
                    "category": "mobility",
                    "description": "車椅子、電動、幅63cm",
                    "rank": 1,
                    "confidence": "high",
                },
                {
                    "domain": "dietary",
                    "category": "dietary",
                    "description": "イスラム教徒、ハラール食が必要",
                    "rank": 2,
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


def test_extract_persona_retries_once_on_duplicate_ranks():
    bad_response = MagicMock()
    bad_response.text = json.dumps(
        {
            "raw_summary": "s",
            "attributes": [
                {"domain": "mobility", "category": "a", "description": "d1", "rank": 1, "confidence": "high"},
                {"domain": "dietary", "category": "b", "description": "d2", "rank": 1, "confidence": "medium"},
            ],
        }
    )
    good_response = MagicMock()
    good_response.text = json.dumps(
        {
            "raw_summary": "s",
            "attributes": [
                {"domain": "mobility", "category": "a", "description": "d1", "rank": 1, "confidence": "high"},
                {"domain": "dietary", "category": "b", "description": "d2", "rank": 2, "confidence": "medium"},
            ],
        }
    )
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [bad_response, good_response]

    persona = extract_persona(transcript="test transcript", genai_client=fake_client)

    assert [a.rank for a in persona.attributes] == [1, 2]
    assert fake_client.models.generate_content.call_count == 2


def test_extract_persona_falls_back_to_order_based_ranks_if_retry_still_invalid():
    bad_response = MagicMock()
    bad_response.text = json.dumps(
        {
            "raw_summary": "s",
            "attributes": [
                {"domain": "mobility", "category": "a", "description": "d1", "rank": 1, "confidence": "high"},
                {"domain": "dietary", "category": "b", "description": "d2", "rank": 1, "confidence": "medium"},
            ],
        }
    )
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [bad_response, bad_response]

    persona = extract_persona(transcript="test transcript", genai_client=fake_client)

    assert [a.rank for a in persona.attributes] == [1, 2]
    assert fake_client.models.generate_content.call_count == 2
