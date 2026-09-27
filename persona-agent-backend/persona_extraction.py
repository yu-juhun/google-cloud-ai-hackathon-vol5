import json
import logging
import uuid

from google.genai import types

from persona_validator import validate_persona
from schemas import Attribute, Persona

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
あなたは、旅行・外食のプランニングを支援するために、ユーザーとの対話ログから
ペルソナ情報を抽出するアシスタントです。

以下の対話ログを読み、次のJSON形式で出力してください:
- raw_summary: 対話全体を1〜3文で要約した自由文
- attributes: 対話から読み取れる、ユーザーの移動制約・食事制約・目的・家族構成・
  優先事項などを表す配列。各要素は次のフィールドを持つ:
  - domain: 次の7つの固定値のいずれか — "mobility"(移動制約) / "dietary"(食事) /
    "purpose"(目的) / "companions"(同行者・人数) / "language"(言語対応) /
    "background"(居住地・出身地・国籍等) / "other"(上記に当てはまらないもの)
  - category: 自由記述の文字列(固定の選択肢はない。対話内容に合った具体的な名前を付けてよい)
  - description: その属性を説明する自由文
  - rank: 1から始まる整数。すべてのattributesを通じて一意で、1が最も重要。
    このユーザーにとって「どの属性が他の属性より重要か」を、対話のトーン・
    繰り返し・強調から相対的に判断してつけること(すべてを見た上で決めること)
  - confidence: "high" | "medium" | "low"(対話からどれだけ確信を持って読み取れるか)

対話から何も読み取れない場合は、attributesを空配列にしてください。
同じ会話内で同じ概念に別の名前を付けないよう、category名の一貫性を保ってください。

対話ログ:
{transcript}
"""


def _call_gemini(prompt: str, genai_client):
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)


def _build_persona(parsed: dict) -> Persona:
    attributes = [
        Attribute(
            domain=a["domain"],
            category=a["category"],
            description=a["description"],
            rank=a["rank"],
            confidence=a["confidence"],
        )
        for a in parsed.get("attributes", [])
    ]

    return Persona(
        persona_id=str(uuid.uuid4()),
        raw_summary=parsed.get("raw_summary", ""),
        attributes=attributes,
    )


def _reassign_ranks_by_order(persona: Persona) -> Persona:
    for i, attribute in enumerate(persona.attributes, start=1):
        attribute.rank = i
    return persona


def extract_persona(transcript: str, genai_client) -> Persona:
    prompt = EXTRACTION_PROMPT.format(transcript=transcript)
    parsed = _call_gemini(prompt, genai_client)
    persona = _build_persona(parsed)

    violations = validate_persona(persona)
    if not violations:
        return persona

    retry_prompt = (
        f"{prompt}\n\n前回の出力には次の問題がありました。修正して出力し直してください:\n"
        + "\n".join(f"- {v}" for v in violations)
    )
    parsed = _call_gemini(retry_prompt, genai_client)
    persona = _build_persona(parsed)

    violations = validate_persona(persona)
    if violations:
        logger.warning(
            "persona validation failed after retry (%s); falling back to order-based ranks",
            violations,
        )
        persona = _reassign_ranks_by_order(persona)

    return persona
