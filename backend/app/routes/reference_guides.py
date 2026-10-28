"""Public reference PDFs, separated from application templates and case documents."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, Response

from ..reference_guides.store import get_guide_bytes

router = APIRouter()
CATALOG = json.loads((Path(__file__).resolve().parents[2] / 'data/reference_guides/catalog.json').read_text())


@router.get('/api/reference-guides/{guide_id}')
def reference_guide(guide_id: str):
    guide = CATALOG.get(guide_id)
    if guide is None:
        raise HTTPException(404, 'Reference guide not found')
    # Fixed catalog keys only: this endpoint cannot retrieve arbitrary private blobs.
    content = get_guide_bytes(guide['blob_key'])
    if content is None:
        return RedirectResponse(guide['source_url'], status_code=307)
    return Response(content, media_type=guide.get('media_type', 'application/pdf'), headers={
        'Content-Disposition': f'inline; filename="{guide["filename"]}"',
        'Cache-Control': 'public, max-age=3600',
        'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    })
