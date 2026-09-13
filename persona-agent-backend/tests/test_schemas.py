import pytest
from pydantic import ValidationError

from schemas import Attribute, Persona


def test_attribute_accepts_free_form_category():
    attr = Attribute(
        category="宗教的な食事制約",
        description="ハラール対応が必要",
        priority="high",
        confidence="high",
        inferred_keywords=["ハラール", "豚肉不可", "アルコール不可"],
    )
    assert attr.category == "宗教的な食事制約"
    assert attr.inferred_keywords == ["ハラール", "豚肉不可", "アルコール不可"]


def test_attribute_defaults_inferred_keywords_to_empty_list():
    attr = Attribute(
        category="mobility",
        description="車椅子、幅63cm",
        priority="high",
        confidence="high",
    )
    assert attr.inferred_keywords == []


def test_attribute_rejects_invalid_priority():
    with pytest.raises(ValidationError):
        Attribute(
            category="mobility",
            description="x",
            priority="urgent",  # not one of high|medium|low
            confidence="high",
        )


def test_persona_accepts_empty_attributes():
    persona = Persona(persona_id="11111111-1111-1111-1111-111111111111", raw_summary="", attributes=[])
    assert persona.attributes == []


def test_persona_serializes_to_expected_shape():
    persona = Persona(
        persona_id="11111111-1111-1111-1111-111111111111",
        raw_summary="車椅子ユーザーの父親。ハラール食を希望。",
        attributes=[
            Attribute(category="mobility", description="車椅子", priority="high", confidence="medium"),
        ],
    )
    dumped = persona.model_dump()
    assert dumped["persona_id"] == "11111111-1111-1111-1111-111111111111"
    assert dumped["attributes"][0]["category"] == "mobility"
    assert dumped["attributes"][0]["inferred_keywords"] == []
