STYLE_LABELS = {"cinematic": "シネマティックな撮影スタイルで", "long_take": "ロングテイクの落ち着いた撮影で",
                "narrated": "ナレーション調の説明を添えて"}
TONE_LABELS = {"calm": "穏やかな雰囲気で", "dramatic": "ドラマチックな雰囲気で", "relaxed": "落ち着いた雰囲気で"}


def build_prompt(report_text, mobility_notes, style, tone, feedback):
    """mobility_notes must already be filtered to domain=="mobility" attributes
    only by the caller — this function does not filter anything itself."""
    parts = [report_text.strip()]
    if mobility_notes:
        parts.append(mobility_notes.strip())
    parts.append(STYLE_LABELS.get(style, ""))
    parts.append(TONE_LABELS.get(tone, ""))
    if feedback:
        parts.append(f"追加の要望: {feedback.strip()}")
    return "。".join(part for part in parts if part)
