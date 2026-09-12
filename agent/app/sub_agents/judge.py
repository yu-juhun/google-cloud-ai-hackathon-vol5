def judge_accessibility(place: dict, wheelchair_width_cm: float) -> dict:
    """Stub: always returns a fixed low-confidence 'accessible' verdict.
    Real implementation (Gemini multimodal over reviews/photos) replaces
    this body only — keep the return shape.
    """
    return {
        "status": "accessible",
        "confidence": "low",
        "reasons": [
            {
                "condition": "entrance",
                "result": "unknown",
                "evidence": "スタブ判定: 実データ未接続のため固定値を返しています。",
            }
        ],
    }
