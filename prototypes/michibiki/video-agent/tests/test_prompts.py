from prompts import build_prompt


def test_build_prompt_includes_all_parts():
    prompt = build_prompt("入口は段差なし", "車いすで通りやすい", "cinematic", "calm", "もっと明るく")
    assert "入口は段差なし" in prompt
    assert "車いすで通りやすい" in prompt
    assert "シネマティック" in prompt
    assert "穏やか" in prompt
    assert "もっと明るく" in prompt


def test_build_prompt_omits_empty_feedback():
    prompt = build_prompt("report text", "", "cinematic", "calm", "")
    assert "追加の要望" not in prompt


def test_rejected_place_is_an_exterior_check_not_a_successful_visit():
    prompt = build_prompt("カフェの入口", "手動車いす", "cinematic", "calm", "",
                          {"scene_kind": "exterior_check", "assessment_status": "not_accessible"})
    assert "Do not show entering" in prompt
    assert "Never stand, walk, climb stairs" in prompt
    assert "Unknown conditions stay unknown" in prompt
