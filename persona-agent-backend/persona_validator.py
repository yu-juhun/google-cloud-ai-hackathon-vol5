"""Structural validation for the Persona JSON other agents consume (see
the v3 design spec's "トラックA"). Gemini is asked to produce unique
ranks via prompt wording alone; this module enforces that guarantee in
code so a prompt-following slip never reaches downstream agents.
"""
from schemas import Persona


def validate_persona(persona: Persona) -> list[str]:
    violations: list[str] = []

    ranks = [a.rank for a in persona.attributes]
    seen: dict[int, int] = {}
    for rank in ranks:
        seen[rank] = seen.get(rank, 0) + 1
    duplicates = sorted(rank for rank, count in seen.items() if count > 1)
    if duplicates:
        violations.append(f"duplicate ranks: {duplicates}")

    return violations
