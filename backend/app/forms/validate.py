"""Checks a form's field map against the PDF and the profile it draws on.

Every failure mode here is silent at runtime: `filler.resolve_fields` treats a bad
`profile_path` and an empty one identically (the field is reported `missing`, never
asked, and prints blank), and pypdf ignores a value written to a field name the PDF
doesn't have. This turns all of that into a list of strings.

Used in two places: inside the generator's retry loop, where the messages are fed back
to the model, and in `tests/test_form_maps.py` over the committed schemas.
"""

import re
from typing import Any

from .profile_paths import profile_paths, profile_values

# Boxes about somebody the profile does not describe, or that a person must sign
# themselves. Filling these from the profile puts a name on a legal document that
# nobody agreed to put there.
_NOT_OURS = re.compile(
    r"authorized representative|legal guardian|power of attorney|witness"
    r"|signature|\bsign(ed|ature)? (of|here|below)\b",
    re.I,
)


def validate_fields(
    fields: dict[str, Any],
    pdf_fields: list[dict],
    *,
    require_complete: bool = False,
) -> list[str]:
    """Problems with a `fields` map, phrased so a model or a human can act on them.

    `require_complete` also demands an entry for every fillable field in the PDF, which
    is what a freshly generated map should satisfy; hand-written maps are allowed to
    cover only part of a form.
    """
    allowed_paths = set(profile_paths())
    known_values = profile_values()
    by_name = {f["name"]: f for f in pdf_fields}
    problems: list[str] = []

    for name, spec in fields.items():
        if name not in by_name:
            problems.append(f'"{name}" is not a field in this PDF; it can never be filled')
            continue
        if isinstance(spec, str):
            problems.append(f'"{name}" uses the legacy bare-string form; expected an object')
            continue

        path = spec.get("profile_path")
        if path is not None and path not in allowed_paths:
            problems.append(
                f'"{name}": profile_path "{path}" is not a profile field intake fills, '
                "so it would print blank and never be asked"
            )
        if path is not None and _NOT_OURS.search(str(spec.get("label") or "")):
            problems.append(
                f'"{name}": "{spec.get("label")}" is about someone the applicant has '
                "to name, or a box they have to sign; it takes profile_path: null"
            )
        if path is None and not spec.get("needs_user_input"):
            problems.append(
                f'"{name}": has no profile_path, so it must set needs_user_input: true '
                "or it will print blank and never be asked"
            )

        options = by_name[name].get("options") or []
        value_map = spec.get("value_map") or {}
        if value_map and options:
            bad = [v for v in value_map.values() if v not in options]
            if bad:
                problems.append(
                    f'"{name}": value_map values {bad} are not export values of that '
                    f"field ({options})"
                )

        # Comparison is on the string form: `check_when` arrives as JSON true/false for
        # boolean paths, while the value sets are spelled out as text.
        expected = known_values.get(path or "")
        if expected:
            check_when = spec.get("check_when")
            if check_when is not None and str(check_when) not in expected:
                problems.append(
                    f'"{name}": check_when {check_when!r} is never a value of {path}; '
                    f"it is one of {expected}"
                )
            bad_keys = [k for k in value_map if str(k) not in expected]
            if bad_keys:
                problems.append(
                    f'"{name}": value_map keys {bad_keys} are never values of {path}; '
                    f"it is one of {expected}"
                )

    if require_complete:
        missing = [name for name in by_name if name not in fields]
        if missing:
            problems.append(f"no entry for: {missing}")

    return problems
