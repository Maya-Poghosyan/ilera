"""Fetch and upload a catalogued public PDF into the dedicated private reference-guides container.

Run from the repository root with Azure CLI already signed in:
backend/.venv/bin/python backend/scripts/upload_reference_guide.py \
    edd-multistate-employment --account-name YOUR_EXISTING_ACCOUNT
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('guide_id')
parser.add_argument('--account-name', required=True)
parser.add_argument('--container', default='reference-guides')
parser.add_argument('--file', type=Path, help='Use a locally downloaded copy instead of downloading the source')
args = parser.parse_args()
catalog = json.loads((Path(__file__).resolve().parents[1] / 'data/reference_guides/catalog.json').read_text())
if args.guide_id not in catalog:
    parser.error('Unknown reference guide')
guide = catalog[args.guide_id]
media_type = guide.get('media_type', 'application/pdf')
max_bytes = 10 * 1024 * 1024
actual_source = guide['source_url']


def valid_content(content):
    if not content or len(content) > max_bytes:
        return False
    if media_type == 'text/html':
        return content.lstrip().lower().startswith(b'<!doctype html>')
    if media_type != 'application/pdf' or b'%PDF-' not in content[:1024]:
        return False
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content), strict=False)
        return not reader.is_encrypted and len(reader.pages) > 0
    except Exception:
        return False


if args.file:
    pdf = args.file.read_bytes()
elif guide.get('source_file'):
    pdf = (Path(__file__).resolve().parents[1] / 'data/reference_guides' / guide['source_file']).read_bytes()
else:
    pdf = b''
    for source in [guide['source_url'], *guide.get('fallback_source_urls', [])]:
        try:
            request = Request(source, headers={'User-Agent': 'Mozilla/5.0 (compatible; IleraReferenceGuideDownloader/1.0)', 'Accept': 'application/pdf'})
            with urlopen(request, timeout=60) as response:
                candidate = response.read(max_bytes + 1)
                content_type = response.headers.get('Content-Type', 'unknown')
            if valid_content(candidate):
                pdf = candidate
                actual_source = source
                break
            print(f'Source did not return a usable PDF ({content_type}, {len(candidate)} bytes): {source}')
        except Exception as exc:
            print(f'Source download failed ({type(exc).__name__}): {source}')
if not valid_content(pdf):
    raise SystemExit('No valid guide obtained; nothing uploaded. You can download the PDF in your browser and retry with --file /path/to/file.pdf.')
sha = hashlib.sha256(pdf).hexdigest()
with tempfile.TemporaryDirectory(prefix='ilera-reference-guide-') as temp:
    file = Path(temp) / guide['filename']
    file.write_bytes(pdf)
    command_env = {**os.environ, 'AZURE_LOGGING_ENABLE_LOG_FILE': 'false', 'AZURE_CORE_COLLECT_TELEMETRY': 'false'}
    subprocess.run(['az', 'storage', 'container', 'create', '--auth-mode', 'login',
                    '--account-name', args.account_name, '--name', args.container,
                    '--public-access', 'off', '--only-show-errors', '--output', 'none'],
                   env=command_env, check=True)
    subprocess.run(['az', 'storage', 'blob', 'upload', '--auth-mode', 'login',
                    '--account-name', args.account_name, '--container-name', args.container,
                    '--name', guide['blob_key'], '--file', str(file),
                    '--content-type', media_type, '--content-disposition', f'inline; filename="{guide["filename"]}"',
                    '--metadata', f'sha256={sha}', f'source_url={actual_source}',
                    '--overwrite', 'false', '--only-show-errors', '--output', 'none'],
                   env=command_env, check=True)
print(f'Uploaded {guide["blob_key"]} ({len(pdf)} bytes; sha256 {sha})')
