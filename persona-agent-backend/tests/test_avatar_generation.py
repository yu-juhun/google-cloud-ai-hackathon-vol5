from unittest.mock import MagicMock

from avatar_generation import evolve_avatar, generate_open_mouth_variant
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


def test_evolve_avatar_excludes_non_visualizable_domains_from_prompt():
    persona = Persona(
        persona_id="test-id",
        raw_summary="summary",
        attributes=[
            Attribute(domain="mobility", category="車椅子", description="電動車椅子", rank=1, confidence="high"),
            Attribute(domain="dietary", category="ハラール", description="イスラム教徒、ハラール食が必要", rank=2, confidence="high"),
            Attribute(domain="background", category="出身", description="中東出身", rank=3, confidence="high"),
        ],
    )

    fake_part = MagicMock()
    fake_part.inline_data.data = b"edited-image-bytes"
    fake_part.text = None
    fake_response = MagicMock()
    fake_response.candidates = [MagicMock(content=MagicMock(parts=[fake_part]))]

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    evolve_avatar(base_image_bytes=b"base-image-bytes", persona=persona, genai_client=fake_client)

    prompt = fake_client.models.generate_content.call_args.kwargs["contents"][1]
    assert "車椅子" in prompt
    assert "ハラール" not in prompt
    assert "出身" not in prompt


def test_evolve_avatar_with_only_non_visualizable_attributes_returns_base_image_unchanged():
    persona = Persona(
        persona_id="test-id",
        raw_summary="summary",
        attributes=[
            Attribute(domain="dietary", category="ハラール", description="ハラール食が必要", rank=1, confidence="high"),
        ],
    )
    fake_client = MagicMock()

    result = evolve_avatar(base_image_bytes=b"base-image-bytes", persona=persona, genai_client=fake_client)

    assert result == b"base-image-bytes"
    fake_client.models.generate_content.assert_not_called()


def test_evolve_avatar_with_no_attributes_returns_base_image_unchanged():
    persona = Persona(persona_id="test-id", raw_summary="", attributes=[])
    fake_client = MagicMock()

    result = evolve_avatar(base_image_bytes=b"base-image-bytes", persona=persona, genai_client=fake_client)

    assert result == b"base-image-bytes"
    fake_client.models.generate_content.assert_not_called()


def test_generate_open_mouth_variant_returns_edited_image_bytes():
    fake_part = MagicMock()
    fake_part.inline_data.data = b"open-mouth-bytes"
    fake_part.text = None
    fake_response = MagicMock()
    fake_response.candidates = [MagicMock(content=MagicMock(parts=[fake_part]))]

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    result = generate_open_mouth_variant(base_image_bytes=b"base-image-bytes", genai_client=fake_client)

    assert result == b"open-mouth-bytes"
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash-image"


def test_generate_open_mouth_variant_falls_back_to_base_if_no_image_returned():
    fake_part = MagicMock()
    fake_part.inline_data = None
    fake_part.text = "some text response"
    fake_response = MagicMock()
    fake_response.candidates = [MagicMock(content=MagicMock(parts=[fake_part]))]

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    result = generate_open_mouth_variant(base_image_bytes=b"base-image-bytes", genai_client=fake_client)

    assert result == b"base-image-bytes"
