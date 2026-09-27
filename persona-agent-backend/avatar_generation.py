from google.genai import types

from avatar_policy import build_edit_instructions, select_visual_attributes
from schemas import Persona

EDIT_PROMPT_TEMPLATE = """\
このキャラクターと完全に同じ顔・髪型・服装・背景・アートスタイルを保ったまま、
以下の特徴を自然に反映するように編集してください。それ以外は一切変えないでください。

{attribute_lines}
"""

OPEN_MOUTH_PROMPT = """\
このキャラクターと完全に同じ顔・髪型・服装・背景・アートスタイル・ポーズを保ったまま、
話しているように口を自然に開けた表情に変えてください。それ以外は一切変えないでください。
"""


def generate_open_mouth_variant(base_image_bytes: bytes, genai_client, mime_type: str = "image/jpeg") -> bytes:
    """Generates a mouth-open variant of the given avatar image, preserving
    character identity. Used so the avatar's "talking" animation shows the
    same personalized character instead of falling back to a generic
    stock image — verified against the real API during this project's
    avatar-quality spike (see conversation history: base+open-mouth pairs
    generated consistently for both a generic character and a
    YouCam-personalized one)."""
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            types.Part.from_bytes(data=base_image_bytes, mime_type=mime_type),
            OPEN_MOUTH_PROMPT,
        ],
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data
    return base_image_bytes


def evolve_avatar(base_image_bytes: bytes, persona: Persona, genai_client, mime_type: str = "image/jpeg") -> bytes:
    """Edits the base avatar image to reflect the persona's attributes,
    preserving character identity (see the v2 design spec's verified
    Nano Banana consistency behavior). Only attributes allowed by
    avatar_policy (domain allowlist, confidence >= medium) may influence
    the appearance (see the v3 design spec's "トラックB"). Returns the
    base image unchanged if there's nothing visualizable, without
    calling Gemini."""
    visual_attributes = select_visual_attributes(persona)
    attribute_lines = build_edit_instructions(visual_attributes)
    if not attribute_lines:
        return base_image_bytes

    prompt = EDIT_PROMPT_TEMPLATE.format(attribute_lines=attribute_lines)

    response = genai_client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            types.Part.from_bytes(data=base_image_bytes, mime_type=mime_type),
            prompt,
        ],
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    return base_image_bytes
