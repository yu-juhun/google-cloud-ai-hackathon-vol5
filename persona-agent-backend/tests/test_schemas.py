import pytest
from pydantic import ValidationError

from schemas import Attribute, Persona


def test_attribute_accepts_free_form_category():
    attr = Attribute(
        domain="dietary",
        category="宗教的な食事制約",
        description="ハラール対応が必要",
        rank=1,
        confidence="high",
        inferred_keywords=["ハラール", "豚肉不可", "アルコール不可"],
    )
    assert attr.category == "宗教的な食事制約"
    assert attr.inferred_keywords == ["ハラール", "豚肉不可", "アルコール不可"]


def test_attribute_defaults_inferred_keywords_to_empty_list():
    attr = Attribute(
        domain="mobility",
        category="mobility",
        description="車椅子、幅63cm",
        rank=1,
        confidence="high",
    )
    assert attr.inferred_keywords == []


def test_attribute_rejects_invalid_domain():
    with pytest.raises(ValidationError):
        Attribute(
            domain="not_a_real_domain",
            category="test",
            description="test",
            rank=1,
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
            Attribute(domain="mobility", category="mobility", description="車椅子", rank=1, confidence="medium"),
        ],
    )
    dumped = persona.model_dump()
    assert dumped["persona_id"] == "11111111-1111-1111-1111-111111111111"
    assert dumped["attributes"][0]["category"] == "mobility"
    assert dumped["attributes"][0]["inferred_keywords"] == []


def test_persona_defaults_schema_version_to_2():
    persona = Persona(persona_id="11111111-1111-1111-1111-111111111111", raw_summary="", attributes=[])
    assert persona.schema_version == "2"
    assert persona.model_dump()["schema_version"] == "2"
