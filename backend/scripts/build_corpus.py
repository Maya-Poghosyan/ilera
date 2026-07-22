"""Extract the eligibility knowledge library into a compact text corpus + manifest.

Usage:
    python scripts/build_corpus.py /path/to/eligibility_knowledge_library [out_dir]

The source directory is the unzipped `eligibility_knowledge_library` (containing a
`metadata.json` plus the downloaded PDFs/HTML/DOCX). Output defaults to
`backend/data/knowledge`, which is committed to the repo and consumed by the RAG index.
"""
import json
import os
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/ilera_pdfs/eligibility/eligibility_knowledge_library"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "data", "knowledge")

# agency/collection -> program tag used by specialist agents
PROGRAM_MAP = {
    "CDSS": "ihss",
    "DHCS": "medical",
    "Covered-California": "medical",
    "CMS": "medicare",
    "SSA": "ssi_ssdi",
    "VA": "va",
    "IRS": "tax",
    "California-EDD": "pfl",
    "US-DOL": "pfl",
    "California-CRD": "pfl",
    "ACL": "federal_routing",
}
EXT_PRIORITY = {".pdf": 0, ".docx": 1, ".txt": 2, ".html": 3}


def strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    return s.strip()


def extract(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = []
        for i, pg in enumerate(reader.pages):
            try:
                t = pg.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                pages.append(f"[page {i + 1}]\n{t.strip()}")
        return "\n\n".join(pages)
    if ext == ".docx":
        import docx
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs if p.text.strip())
    with open(path, encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    return strip_html(raw) if ext == ".html" else raw.strip()


def main() -> None:
    meta = json.load(open(os.path.join(SRC, "metadata.json")))
    by_docid = {r["document_id"]: r for r in meta["resources"]}

    # collect real files, group by document_id, pick best extension
    groups: dict[str, list[str]] = {}
    for root, _, files in os.walk(SRC):
        if "__MACOSX" in root:
            continue
        for fn in files:
            if fn.startswith(".") or fn == "metadata.json":
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXT_PRIORITY:
                continue
            docid = fn.split("_2026-")[0]
            groups.setdefault(docid, []).append(os.path.join(root, fn))

    manifest = []
    n_chars = 0
    for docid, paths in sorted(groups.items()):
        paths.sort(key=lambda p: EXT_PRIORITY[os.path.splitext(p)[1].lower()])
        chosen = paths[0]
        rel = os.path.relpath(chosen, SRC)
        parts = rel.split(os.sep)
        # externally_shareable/<agency>/<collection>/<file> or not_shareable/...
        distribution_dir, agency, collection = parts[0], parts[1], parts[2]
        program = PROGRAM_MAP.get(agency, "other")
        md = by_docid.get(docid, {})
        text = extract(chosen)
        if not text or len(text) < 40:
            print(f"  SKIP (no text): {docid} ({os.path.basename(chosen)})")
            continue
        out_dir = os.path.join(OUT, program)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{docid}.txt")
        with open(out_path, "w") as f:
            f.write(text)
        n_chars += len(text)
        manifest.append({
            "document_id": docid,
            "program": program,
            "agency": agency,
            "collection": collection,
            "title": md.get("title", docid),
            "source_url": md.get("resolved_url") or md.get("url", ""),
            "priority": md.get("priority", ""),
            "authority_level": md.get("authority_level", ""),
            "distribution": "not_shareable" if distribution_dir == "not_shareable" else "shareable",
            "tags": md.get("tags", []),
            "source_ext": os.path.splitext(chosen)[1].lower().lstrip("."),
            "text_path": os.path.relpath(out_path, OUT),
            "chars": len(text),
        })
        print(f"  {program:14} {docid:34} {len(text):>8} chars  [{manifest[-1]['source_ext']}]")

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump({"docs": manifest}, f, indent=2)
    from collections import Counter
    print("\nby program:", dict(Counter(d["program"] for d in manifest)))
    print(f"docs: {len(manifest)}  total chars: {n_chars:,}")


if __name__ == "__main__":
    main()
