from persona_validator import validate_persona
from schemas import Attribute, Persona


def _attr(rank: int, domain: str = "mobility") -> Attribute:
    return Attribute(
        domain=domain,
        category="c",
        description="d",
        rank=rank,
        confidence="high",
    )


def test_validate_persona_reports_duplicate_ranks():
    persona = Persona(
        persona_id="p1",
        raw_summary="s",
        attributes=[_attr(1), _attr(1)],
    )

    violations = validate_persona(persona)

    assert violations == ["duplicate ranks: [1]"]


def test_validate_persona_accepts_unique_ranks():
    persona = Persona(
        persona_id="p1",
        raw_summary="s",
        attributes=[_attr(1), _attr(2)],
    )

    assert validate_persona(persona) == []


def test_validate_persona_accepts_no_attributes():
    persona = Persona(persona_id="p1", raw_summary="s", attributes=[])

    assert validate_persona(persona) == []
