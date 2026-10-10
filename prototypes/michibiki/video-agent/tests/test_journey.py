from journey import scene_prompt, transition_offsets


def test_smooth_transitions_have_correct_timeline():
    assert transition_offsets([8, 8, 8, 8], .6) == [7.4, 14.8, 22.2]
    assert transition_offsets([8, 6, 6, 6], .6) == [7.4, 12.8, 18.2]


def test_itinerary_scene_is_not_an_entrance_test():
    prompt = scene_prompt({"wish": "聖地巡礼", "destination": "乃木坂"},
                          {"activity": "美術館を楽しむ"},
                          {"name": "国立新美術館", "visual_action": "Enjoy the distinctive glass facade."}, 1, 4, "手動車いす")
    assert "scene 2 of 4" in prompt
    assert "Reference 2 is the actual destination" in prompt
    assert "Never stand, walk" in prompt
    assert "not a medical demonstration or an entrance test" in prompt
