"""Draft a form's field map with an LLM, page by page.

`form_schemas/<form_id>.json` says what each AcroForm field *means* in CaseProfile
terms. Authoring that by hand is the bottleneck (17 of 20 forms are still empty), and
the two halves of the answer live in different layers of the PDF: the exact field name
is in the AcroForm, while the question it stands under is only in the page text. This
pairs them per page and asks a model to align them.

Generation is offline and reviewed, never part of serving an application:

    pip install -r requirements-band.txt           # pydantic-ai; not needed to serve
    python -m app.forms.generate soc-426a          # write data/form_schemas/soc-426a.json
    python -m app.forms.generate soc-426a --dry-run

Correctness rests on the validator, not on the prompt. `_validate` runs inside
pydantic-ai's output-validation loop, so a violation is fed back to the model as a
retry rather than reaching the file: field names must be ones this page actually has,
`profile_path`s must come from `profile_paths()`, and `value_map` values must be exact
`/Opt` members. What it cannot catch is a confident, well-formed, wrong mapping — hence
`confidence` on every field, and human review of the committed diff.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..config import get_settings
from .discovery import is_junk
from .extract import extract_fields, extract_pages
from .filler import SCHEMA_DIR, _get_pdf_path, load_schema
from .profile_paths import describe_profile_paths
from .validate import validate_fields


SYSTEM_PROMPT = """\
You map the fillable fields of a US government benefits form onto a caregiving app's \
stored profile, so the app can autofill the form and only ask the applicant for what \
it doesn't already know.

You are given one page at a time: the page's printed text, and the exact AcroForm field \
names on that page with their widget types and, for radios/dropdowns, their export \
values.

Rules:
- Return an entry for every field name given to you, and never a name you were not given.
- `label` is the question as printed on the page, in plain language, so a person could \
answer it out of context. Do not copy a tooltip that contradicts the printed text; \
tooltips on some forms are wrong or belong to a neighbouring field.
- Set `profile_path` only when the printed question asks for exactly what that profile \
field holds, and only to a path from the supplied list. Anything else is `null` with \
`needs_user_input: true` — an unmapped field gets asked, a wrongly mapped one prints \
wrong data onto a government form.
- The form is about the care recipient (the applicant) and their caregiver/provider. \
Read the section heading to tell whose name or address a field wants.
- For a radio or dropdown you map, give `value_map` from the profile value to the exact \
export value shown for that field.
- For a checkbox that should be ticked when a profile value equals something specific, \
give `check_when` with that value.
- `confidence` is `high` only when the printed text names the datum unambiguously.
"""


class FieldMapping(BaseModel):
    """One AcroForm field's meaning, in the shape `form_schemas/*.json` stores."""

    pdf_field: str = Field(description="Exact AcroForm field name, copied verbatim")
    label: str = Field(description="The question as printed on the page")
    profile_path: Optional[str] = Field(
        default=None, description="Dotted CaseProfile path, or null to ask the user"
    )
    needs_user_input: bool = Field(
        default=False, description="True when the applicant must supply this"
    )
    value_map: Optional[dict[str, str]] = Field(
        default=None, description="Profile value -> exact PDF export value"
    )
    check_when: Optional[str] = Field(
        default=None, description="Tick this checkbox when the profile value equals this"
    )
    confidence: Literal["high", "medium", "low"] = "medium"


class PageMap(BaseModel):
    fields: list[FieldMapping] = Field(default_factory=list)


def _model() -> Any:
    """A pydantic-ai model for the configured provider (OpenAI/Azure or Anthropic)."""
    s = get_settings()
    provider = (s.llm_provider or "").lower()
    if provider in ("openai", "azure") or (not provider and s.openai_api_key):
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        client = AsyncOpenAI(
            api_key=s.openai_api_key,
            base_url=s.openai_base_url or None,
            max_retries=6,
            timeout=180.0,
        )
        return OpenAIChatModel(s.openai_model, provider=OpenAIProvider(openai_client=client))

    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    return AnthropicModel(
        s.anthropic_model, provider=AnthropicProvider(api_key=s.anthropic_api_key)
    )


def _describe_field(field: dict) -> str:
    line = f'- "{field["name"]}" ({field["type"]})'
    if field.get("options"):
        line += " export values: " + ", ".join(f'"{o}"' for o in field["options"])
    if field.get("tooltip"):
        line += f' tooltip: "{field["tooltip"]}"'
    return line


def _page_prompt(form_id: str, page: dict, fields: list[dict]) -> str:
    return (
        f"Form: {form_id.upper()}  (page {page['page']})\n\n"
        f"--- printed page text ---\n{page['text'].strip()}\n\n"
        f"--- fillable fields on this page ---\n"
        + "\n".join(_describe_field(f) for f in fields)
        + "\n\n--- profile paths you may use ---\n"
        + describe_profile_paths()
        + "\n\nMap every field listed above."
    )


def _validate(mappings: list[FieldMapping], fields: list[dict]) -> list[str]:
    """Reasons the draft is unusable, phrased for the model to correct.

    Checked in the shape it will be written in, by the same validator the committed
    schemas are held to, so the model can't satisfy the retry loop with something the
    test suite later rejects.
    """
    by_name = {f["name"]: f for f in fields}
    errors: list[str] = []
    drafted: dict[str, dict] = {}

    for m in mappings:
        if m.pdf_field in drafted:
            errors.append(f'"{m.pdf_field}" appears more than once')
        field = by_name.get(m.pdf_field)
        # An unknown name has no widget type to render the spec against; validate_fields
        # reports it from the key alone.
        drafted[m.pdf_field] = _to_spec(m, field) if field else {"profile_path": None}

    return errors + validate_fields(drafted, fields, require_complete=True)


def _to_spec(m: FieldMapping, field: dict) -> dict:
    """A FieldMapping in the on-disk `form_schemas` shape."""
    spec: dict[str, Any] = {"profile_path": m.profile_path, "label": m.label}
    if field["type"] != "text":
        spec["type"] = field["type"]
    if m.value_map:
        spec["value_map"] = m.value_map
    if m.check_when is not None:
        spec["check_when"] = m.check_when
    if m.needs_user_input or m.profile_path is None:
        spec["needs_user_input"] = True
    if m.confidence != "high":
        spec["confidence"] = m.confidence
    return spec


async def generate_form_map(form_id: str, only_pages: Optional[list[int]] = None) -> dict:
    """Draft `fields` for one form, one page per model call."""
    from pydantic_ai import Agent, ModelRetry

    pdf_path = _get_pdf_path(form_id)
    if not pdf_path:
        raise FileNotFoundError(f"No PDF on disk for form {form_id}")

    # Signatures and screen-reader artifacts are dropped by the same rule the question
    # builder uses, so the map never introduces a "field" the applicant would be asked
    # about but that discovery refuses to show.
    fields_by_name = {
        f["name"]: f for f in extract_fields(pdf_path) if not is_junk(f)
    }
    pages = extract_pages(pdf_path)

    agent = Agent(_model(), output_type=PageMap, system_prompt=SYSTEM_PROMPT, retries=3)
    # The validator belongs to the agent, not to a run, so it reads the page being
    # processed from here rather than being re-registered (and stacked up) per page.
    current_fields: list[dict] = []

    @agent.output_validator
    def check(output: PageMap) -> PageMap:
        errors = _validate(output.fields, current_fields)
        if errors:
            raise ModelRetry(
                "Fix these and return the whole page again:\n- " + "\n- ".join(errors)
            )
        return output

    drafted: dict[str, dict] = {}
    for page in pages:
        if only_pages and page["page"] not in only_pages:
            continue
        page_fields = [fields_by_name[n] for n in page["fields"] if n in fields_by_name]
        if not page_fields:
            continue
        current_fields = page_fields

        result = await agent.run(_page_prompt(form_id, page, page_fields))
        for m in result.output.fields:
            drafted[m.pdf_field] = _to_spec(m, fields_by_name[m.pdf_field])
        print(
            f"  page {page['page']}: {len(page_fields)} fields, "
            f"{sum(1 for m in result.output.fields if m.profile_path)} mapped",
            file=sys.stderr,
        )

    # Keep the PDF's own field order so the JSON reads top-to-bottom like the form.
    ordered = {name: drafted[name] for name in fields_by_name if name in drafted}
    return ordered


def merge_form_map(form_id: str, drafted: dict, *, replace: bool = False) -> dict:
    """Drafted fields, with reviewed autofill decisions from the existing file kept.

    An entry that already carries a `profile_path` was either written or approved by a
    person, and is worth more than a fresh draft; regenerating a form shouldn't quietly
    undo that. `replace` throws the existing map away instead.
    """
    if replace:
        return drafted
    existing = load_schema(form_id).get("fields") or {}
    merged = dict(drafted)
    for name, spec in existing.items():
        if isinstance(spec, dict) and spec.get("profile_path") and name in merged:
            merged[name] = spec
    return merged


def write_form_map(form_id: str, fields: dict) -> str:
    """Write the field map into the schema file, keeping `_meta`."""
    schema = load_schema(form_id)
    schema.setdefault("_meta", {})
    schema["fields"] = fields
    path = os.path.join(SCHEMA_DIR, f"{form_id.lower()}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("form_id")
    parser.add_argument("--pages", help="Comma-separated page numbers (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Print instead of writing")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Discard existing mappings instead of keeping reviewed ones",
    )
    args = parser.parse_args()

    only = [int(p) for p in args.pages.split(",")] if args.pages else None
    drafted = asyncio.run(generate_form_map(args.form_id, only))
    fields = merge_form_map(args.form_id, drafted, replace=args.replace)
    mapped = sum(1 for f in fields.values() if f.get("profile_path"))
    print(f"{args.form_id}: {len(fields)} fields, {mapped} autofilled", file=sys.stderr)

    if args.dry_run:
        print(json.dumps(fields, indent=2, ensure_ascii=False))
        return
    print(f"wrote {write_form_map(args.form_id, fields)}", file=sys.stderr)


if __name__ == "__main__":
    main()
