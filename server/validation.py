"""Server-side validation helpers wrapping the Pydantic models.

Beyond schema/range validation, every manifest is run through the
build-budget calculator (``server.balance``). A manifest that schema-validates
but exceeds the budget is rejected here, so unfair characters never reach
the arena.

The success payload is a 2-tuple ``(model, report)``. The report is a plain
dict suitable for JSON serialization back to the student so they can see the
cost breakdown and warnings.
"""

from __future__ import annotations

from typing import Tuple

from pydantic import ValidationError

from .balance import build_report
from .models import CharacterManifest, JoinRequest


def validate_manifest(data: dict) -> Tuple[bool, object]:
    try:
        m = CharacterManifest.model_validate(data)
    except ValidationError as e:
        return False, _format_error(e)
    report = build_report(m)
    if not report["ok"]:
        return False, (
            f"Over budget: {report['total']}/{report['budget']} pts. "
            f"Trim {-report['remaining']:.1f} pts (lower a power or a stat)."
        )
    return True, (m, report)


def validate_join(data: dict) -> Tuple[bool, object]:
    try:
        j = JoinRequest.model_validate(data)
    except ValidationError as e:
        return False, _format_error(e)
    report = build_report(j.manifest)
    if not report["ok"]:
        return False, (
            f"Over budget: {report['total']}/{report['budget']} pts."
        )
    return True, (j, report)


def _format_error(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"])
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
