from google.genai import types

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
    Nano Banana consistency behavior). Returns the base image unchanged
    if there are no attributes to reflect yet, without calling Gemini."""
    if not persona.attributes:
        return base_image_bytes

    attribute_lines = "\n".join(f"- {a.category}: {a.description}" for a in persona.attributes)
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
