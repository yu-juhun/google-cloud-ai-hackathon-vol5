"""Which persona attributes may influence the avatar's appearance, and
how strongly (see the v3 design spec's "トラックB"). Keeping this as an
explicit allowlist means a domain like `background` (religion, origin,
nationality) never reaches the image-edit prompt and risks the model
inventing a stereotyped appearance on its own — add a domain here only
as a deliberate decision.
"""
from schemas import Attribute, Domain, Persona

VISUALIZABLE_DOMAINS: set[Domain] = {"mobility"}


def select_visual_attributes(persona: Persona) -> list[Attribute]:
    attrs = [
        a
        for a in persona.attributes
        if a.domain in VISUALIZABLE_DOMAINS and a.confidence != "low"
    ]
    return sorted(attrs, key=lambda a: a.rank)


def build_edit_instructions(attrs: list[Attribute]) -> str:
    if not attrs:
        return ""

    lines = []
    for i, a in enumerate(attrs):
        weight = "必ず反映してください" if i == 0 else "可能なら反映してください"
        lines.append(f"- {a.category}: {a.description}({weight})")

    return "\n".join(lines)
