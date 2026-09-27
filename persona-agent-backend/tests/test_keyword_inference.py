import json
from unittest.mock import MagicMock

from keyword_inference import infer_keywords
from schemas import Attribute, Persona


def test_infer_keywords_fills_in_each_attribute_in_one_call():
    persona = Persona(
        persona_id="11111111-1111-1111-1111-111111111111",
        raw_summary="車椅子ユーザーでハラール食希望",
        attributes=[
            Attribute(domain="mobility", category="mobility", description="車椅子、幅63cm", rank=1, confidence="high"),
            Attribute(domain="dietary", category="dietary", description="イスラム教徒", rank=2, confidence="high"),
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


def test_infer_keywords_falls_back_to_empty_list_when_response_is_short():
    persona = Persona(
        persona_id="11111111-1111-1111-1111-111111111111",
        raw_summary="車椅子ユーザーでハラール食希望",
        attributes=[
            Attribute(domain="mobility", category="mobility", description="車椅子、幅63cm", rank=1, confidence="high"),
            Attribute(domain="dietary", category="dietary", description="イスラム教徒", rank=2, confidence="high"),
        ],
    )

    fake_response = MagicMock()
    fake_response.text = json.dumps({"keywords_by_index": [["車椅子対応", "スロープ"]]})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    result = infer_keywords(persona, genai_client=fake_client)

    assert result.attributes[0].inferred_keywords == ["車椅子対応", "スロープ"]
    assert result.attributes[1].inferred_keywords == []


def test_infer_keywords_falls_back_to_empty_lists_when_key_is_missing():
    persona = Persona(
        persona_id="11111111-1111-1111-1111-111111111111",
        raw_summary="車椅子ユーザーでハラール食希望",
        attributes=[
            Attribute(domain="mobility", category="mobility", description="車椅子、幅63cm", rank=1, confidence="high"),
        ],
    )

    fake_response = MagicMock()
    fake_response.text = json.dumps({})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    result = infer_keywords(persona, genai_client=fake_client)

    assert result.attributes[0].inferred_keywords == []


def test_infer_keywords_returns_persona_unchanged_when_no_attributes():
    persona = Persona(persona_id="x", raw_summary="", attributes=[])
    fake_client = MagicMock()

    result = infer_keywords(persona, genai_client=fake_client)

    assert result.attributes == []
    # no Gemini call needed for an empty attribute list
    fake_client.models.generate_content.assert_not_called()
