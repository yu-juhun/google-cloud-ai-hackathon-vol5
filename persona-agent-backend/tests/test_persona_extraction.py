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
