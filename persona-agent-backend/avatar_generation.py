from google.genai import types

from schemas import Persona

EDIT_PROMPT_TEMPLATE = """\
このキャラクターと完全に同じ顔・髪型・服装・背景・アートスタイルを保ったまま、
以下の特徴を自然に反映するように編集してください。それ以外は一切変えないでください。

{attribute_lines}
"""


def evolve_avatar(base_image_bytes: bytes, persona: Persona, genai_client) -> bytes:
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
            types.Part.from_bytes(data=base_image_bytes, mime_type="image/png"),
            prompt,
        ],
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    return base_image_bytes
