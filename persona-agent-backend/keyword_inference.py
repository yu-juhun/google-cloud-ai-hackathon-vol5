import json

from google.genai import types

from schemas import Persona

KEYWORD_PROMPT = """\
以下は、ある人物についてのペルソナ属性のリストです。各属性について、
店舗検索や施設の適合判定に役立つ、具体的で実用的なキーワードを3〜5個ずつ考えてください。

出力形式は次のJSONにしてください:
{{"keywords_by_index": [["属性0のキーワード", ...], ["属性1のキーワード", ...], ...]}}

配列の順序は入力の属性の順序と一致させてください。

属性リスト:
{attributes_json}
"""


def infer_keywords(persona: Persona, genai_client) -> Persona:
    if not persona.attributes:
        return persona

    attributes_json = json.dumps(
        [{"category": a.category, "description": a.description} for a in persona.attributes],
        ensure_ascii=False,
    )
    prompt = KEYWORD_PROMPT.format(attributes_json=attributes_json)

    response = genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    parsed = json.loads(response.text)
    keywords_by_index = parsed.get("keywords_by_index", [])

    updated_attributes = [
        attr.model_copy(update={"inferred_keywords": keywords_by_index[i] if i < len(keywords_by_index) else []})
        for i, attr in enumerate(persona.attributes)
    ]

    return persona.model_copy(update={"attributes": updated_attributes})
