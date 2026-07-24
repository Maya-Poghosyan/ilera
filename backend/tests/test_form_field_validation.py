"""Guards for form-field discovery and the curated-schema overlay.

The application autofill relies on ``form_schemas/*.json`` keys being *exact* AcroForm
field names. If a curated key drifts from the real PDF, pypdf silently fails to fill it.
These tests turn that silent failure into a loud one, and check that discovery drops
non-data fields (signatures / accessibility artifacts).

Runs against the in-memory store (no services). Run directly or via pytest.
"""
import os
import sys

os.environ.pop("REDIS_URL", None)  # force the in-memory store fallback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import applications  # noqa: E402
from app.forms import filler  # noqa: E402
from app.forms.discovery import discover_fields  # noqa: E402
from app.forms.extract import extract_fields  # noqa: E402
from app.models import CareRecipient, CaseProfile  # noqa: E402


def _schema_ids_with_pdf() -> list[str]:
    ids: list[str] = []
    for fname in sorted(os.listdir(filler.SCHEMA_DIR)):
        if not fname.endswith(".json"):
            continue
        form_id = fname[:-5]
        schema = filler.load_schema(form_id)
        if not schema.get("fields"):
            continue
        if filler._get_pdf_path(form_id):
            ids.append(form_id)
    return ids


def test_curated_keys_exist_in_real_pdf():
    """Every curated schema key must be a real AcroForm field name in the PDF."""
    checked = 0
    for form_id in _schema_ids_with_pdf():
        schema = filler.load_schema(form_id)
        curated = set(schema["fields"].keys())
        real = {f["name"] for f in extract_fields(filler._get_pdf_path(form_id))}
        orphans = sorted(curated - real)
        assert not orphans, (
            f"{form_id}: curated keys absent from the PDF (would silently fail to "
            f"fill): {orphans}"
        )
        checked += 1
    assert checked > 0, "expected at least one mapped schema with a PDF to validate"


def test_discovery_drops_signature_and_junk_fields():
    fields = discover_fields("soc-295")
    assert fields, "expected SOC-295 to yield discoverable fields"
    assert all(f.pdf_type != "signature" for f in fields)
    for f in fields:
        tt = f.tooltip.lower()
        assert "forms mode" not in tt
        assert "created to be accessible" not in tt


def test_discovery_maps_checkbox_to_boolean():
    types = {f.name: f.intake_type for f in discover_fields("soc-295")}
    # SOC-295 is checkbox-heavy; at least one field must map to a boolean control.
    assert "boolean" in types.values()


def test_start_application_questions_use_real_field_types():
    profile = CaseProfile(
        id="case-forms-1",
        care_recipient=CareRecipient(name="Test Recipient"),
    )
    result = applications.start_application("case-forms-1", "IHSS", profile)
    assert result["total_fields"] > 0
    # Denominator should reflect the real AcroForm inventory, not the sparse schema.
    assert result["total_fields"] >= 150
    for q in result["questions"]:
        assert q["field_id"]
        assert q["type"] in (
            "short_text",
            "long_text",
            "boolean",
            "single_select",
            "multi_select",
            "number",
            "date",
        )
        assert q["fields"] == [q["field_id"]]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
