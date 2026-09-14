from unittest.mock import MagicMock

from avatar_generation import evolve_avatar
from schemas import Attribute, Persona


def test_evolve_avatar_returns_edited_image_bytes():
    persona = Persona(
        persona_id="test-id",
        raw_summary="summary",
        attributes=[
            Attribute(domain="mobility", category="車椅子", description="電動車椅子", rank=1, confidence="high"),
        ],
    )

    fake_part = MagicMock()
    fake_part.inline_data.data = b"edited-image-bytes"
    fake_part.text = None
    fake_response = MagicMock()
    fake_response.candidates = [MagicMock(content=MagicMock(parts=[fake_part]))]

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    result = evolve_avatar(base_image_bytes=b"base-image-bytes", persona=persona, genai_client=fake_client)

    assert result == b"edited-image-bytes"
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash-image"


def test_evolve_avatar_with_no_attributes_returns_base_image_unchanged():
    persona = Persona(persona_id="test-id", raw_summary="", attributes=[])
    fake_client = MagicMock()

    result = evolve_avatar(base_image_bytes=b"base-image-bytes", persona=persona, genai_client=fake_client)

    assert result == b"base-image-bytes"
    fake_client.models.generate_content.assert_not_called()
