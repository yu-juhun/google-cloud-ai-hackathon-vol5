#!/usr/bin/env python3
"""OKF bundle linter for docs/wiki/.

Checks (per docs/wiki/schema.md):
- every concept page (anything except index.md / log.md) has frontmatter with `type`
- `status` (if present) is one of draft/stable/deprecated
- `sources[]` entries (if present) each have `resource`
- exactly one page has `type: steering`
- a `type: steering` page never has `status: deprecated`
"""
import sys
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

BUNDLE = Path("docs/wiki")
SPECIAL_FILES = {"index.md", "log.md", "schema.md"}
VALID_STATUS = {"draft", "stable", "deprecated"}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def load_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    return yaml.safe_load(m.group(1)) or {}


def main() -> int:
    errors = []
    steering_pages = []

    if not BUNDLE.exists():
        print(f"No bundle found at {BUNDLE}, skipping.")
        return 0

    for path in sorted(BUNDLE.rglob("*.md")):
        rel = path.relative_to(BUNDLE)
        if path.name in SPECIAL_FILES and path.parent == BUNDLE:
            continue  # index.md / log.md are exempt from `type` requirement

        fm = load_frontmatter(path)
        if fm is None:
            errors.append(f"{rel}: missing frontmatter (required field: type)")
            continue

        if "type" not in fm:
            errors.append(f"{rel}: missing required field `type`")

        status = fm.get("status")
        if status is not None and status not in VALID_STATUS:
            errors.append(f"{rel}: invalid status `{status}` (expected one of {sorted(VALID_STATUS)})")

        for i, src in enumerate(fm.get("sources") or []):
            if not isinstance(src, dict) or "resource" not in src:
                errors.append(f"{rel}: sources[{i}] missing required field `resource`")

        if fm.get("type") == "steering":
            steering_pages.append((rel, status))

    if len(steering_pages) == 0:
        errors.append("no page with `type: steering` found (schema.md requires exactly one)")
    elif len(steering_pages) > 1:
        names = ", ".join(str(r) for r, _ in steering_pages)
        errors.append(f"more than one `type: steering` page found: {names} (schema.md requires exactly one)")

    for rel, status in steering_pages:
        if status == "deprecated":
            errors.append(f"{rel}: steering page must not be `status: deprecated`")

    if errors:
        print("OKF lint failed:\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OKF lint passed ({len(list(BUNDLE.rglob('*.md')))} files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
