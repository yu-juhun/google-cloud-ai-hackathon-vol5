from avatar_policy import build_edit_instructions, select_visual_attributes
from schemas import Attribute, Persona


def _attr(domain: str, rank: int, confidence: str = "high", category: str = "c", description: str = "d") -> Attribute:
    return Attribute(
        domain=domain,
        category=category,
        description=description,
        rank=rank,
        confidence=confidence,
    )


def test_select_visual_attributes_filters_to_allowlisted_domains():
    persona = Persona(
        persona_id="p1",
        raw_summary="s",
        attributes=[
            _attr("mobility", rank=1),
            _attr("dietary", rank=2),
            _attr("background", rank=3),
            _attr("purpose", rank=4),
            _attr("companions", rank=5),
            _attr("language", rank=6),
            _attr("other", rank=7),
        ],
    )

    selected = select_visual_attributes(persona)

    assert [a.domain for a in selected] == ["mobility"]


def test_select_visual_attributes_excludes_low_confidence():
    persona = Persona(
        persona_id="p1",
        raw_summary="s",
        attributes=[
            _attr("mobility", rank=1, confidence="low"),
            _attr("mobility", rank=2, confidence="medium"),
        ],
    )

    selected = select_visual_attributes(persona)

    assert [a.rank for a in selected] == [2]


def test_select_visual_attributes_sorts_by_rank_ascending():
    persona = Persona(
        persona_id="p1",
        raw_summary="s",
        attributes=[
            _attr("mobility", rank=3),
            _attr("mobility", rank=1),
            _attr("mobility", rank=2),
        ],
    )

    selected = select_visual_attributes(persona)

    assert [a.rank for a in selected] == [1, 2, 3]


def test_build_edit_instructions_marks_only_first_as_mandatory():
    attrs = [
        _attr("mobility", rank=1, category="wheelchair", description="電動車椅子"),
        _attr("mobility", rank=2, category="posture", description="前傾姿勢"),
    ]

    text = build_edit_instructions(attrs)

    lines = text.splitlines()
    assert "必ず反映してください" in lines[0]
    assert "可能なら反映してください" in lines[1]
    assert "必ず反映してください" not in lines[1]


def test_build_edit_instructions_returns_empty_for_no_attributes():
    assert build_edit_instructions([]) == ""
