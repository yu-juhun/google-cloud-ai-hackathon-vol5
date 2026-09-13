import json
import uuid

from google.genai import types

from schemas import Attribute, Persona

EXTRACTION_PROMPT = """\
あなたは、旅行・外食のプランニングを支援するために、ユーザーとの対話ログから
ペルソナ情報を抽出するアシスタントです。

以下の対話ログを読み、次のJSON形式で出力してください:
- raw_summary: 対話全体を1〜3文で要約した自由文
- attributes: 対話から読み取れる、ユーザーの移動制約・食事制約・目的・家族構成・
  優先事項などを表す配列。各要素は次のフィールドを持つ:
  - category: 自由記述の文字列(固定の選択肢はない。対話内容に合った具体的な名前を付けてよい)
  - description: その属性を説明する自由文
  - priority: "high" | "medium" | "low"(本人がどれだけ重視しているように見えるか)
  - confidence: "high" | "medium" | "low"(対話からどれだけ確信を持って読み取れるか)

対話から何も読み取れない場合は、attributesを空配列にしてください。
同じ会話内で同じ概念に別の名前を付けないよう、category名の一貫性を保ってください。

対話ログ:
{transcript}
"""


def extract_persona(transcript: str, genai_client) -> Persona:
    prompt = EXTRACTION_PROMPT.format(transcript=transcript)
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    parsed = json.loads(response.text)

    attributes = [
        Attribute(
            category=a["category"],
            description=a["description"],
            priority=a["priority"],
            confidence=a["confidence"],
        )
        for a in parsed.get("attributes", [])
    ]

    return Persona(
        persona_id=str(uuid.uuid4()),
        raw_summary=parsed.get("raw_summary", ""),
        attributes=attributes,
    )
