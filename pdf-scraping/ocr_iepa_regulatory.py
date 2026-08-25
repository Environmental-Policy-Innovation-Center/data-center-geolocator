#!/usr/bin/env python3
"""OCR IEPA air-permit and compliance PDFs into page-delimited text."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_ROOT = ROOT / "pdf-scraping" / "iepa_pdfs"
OUTPUT_ROOT = ROOT / "pdf-scraping" / "iepa_ocr_text"
TMP_ROOT = ROOT / "tmp" / "pdfs" / "iepa_regulatory_ocr"
VISION_BINARY = ROOT / "tmp" / "pdfs" / "iepa_regulatory_ocr" / "vision_ocr"
VISION_SOURCE = Path(__file__).resolve().with_name("vision_ocr.swift")
RELEVANT_CATEGORIES = {"Air_Permit_-_Final", "Compliance"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ordered_text(page: dict) -> tuple[str, float | None]:
    observations = sorted(
        page.get("observations", []),
        key=lambda item: (-(item["y"] + item["height"]), item["x"]),
    )
    text = "\n".join(item["text"] for item in observations)
    confidences = [float(item["confidence"]) for item in observations]
    return text, (sum(confidences) / len(confidences) if confidences else None)


def ocr_pdf(source: Path, *, dpi: int, force: bool) -> dict:
    relative = source.relative_to(PDF_ROOT)
    text_path = (OUTPUT_ROOT / relative).with_suffix(".txt")
    metadata_path = (OUTPUT_ROOT / relative).with_suffix(".ocr.json")
    source_hash = sha256(source)
    if not force and text_path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_sha256") == source_hash:
            return {"status": "skipped", **metadata}

    text_path.parent.mkdir(parents=True, exist_ok=True)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pages_", dir=TMP_ROOT) as temporary:
        temporary_path = Path(temporary)
        prefix = temporary_path / "page"
        subprocess.run(
            [str(PDFTOPPM), "-r", str(dpi), "-gray", "-png", str(source), str(prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        jsonl_path = temporary_path / "ocr.jsonl"
        subprocess.run([str(VISION_BINARY), str(temporary_path), str(jsonl_path)], check=True)
        pages = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]

    sections: list[str] = []
    page_confidences: list[float] = []
    character_count = 0
    for page_number, page in enumerate(pages, start=1):
        text, confidence = ordered_text(page)
        character_count += len(text)
        if confidence is not None:
            page_confidences.append(confidence)
        sections.append(f"===== PAGE {page_number} =====\n{text}\n")
    text_path.write_text("\n".join(sections), encoding="utf-8")

    metadata = {
        "source_pdf": str(relative),
        "source_sha256": source_hash,
        "ocr_text": str(text_path.relative_to(ROOT)),
        "ocr_method": "macOS Vision VNRecognizeTextRequest accurate",
        "dpi": dpi,
        "page_count": len(pages),
        "character_count": character_count,
        "mean_line_confidence": (
            sum(page_confidences) / len(page_confidences) if page_confidences else None
        ),
        "ocr_completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {"status": "ocr", **metadata}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise SystemExit("pdftoppm not found on PATH; install Poppler first")
    if not VISION_BINARY.exists():
        swiftc = shutil.which("swiftc")
        if not swiftc:
            raise SystemExit("swiftc not found; this OCR workflow requires macOS with Xcode command-line tools")
        VISION_BINARY.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([swiftc, str(VISION_SOURCE), "-o", str(VISION_BINARY)], check=True)

    global PDFTOPPM
    PDFTOPPM = Path(pdftoppm)

    sources = sorted(
        path
        for path in PDF_ROOT.glob("*/*/*.pdf")
        if path.parent.name in RELEVANT_CATEGORIES
    )
    if args.limit is not None:
        sources = sources[: args.limit]
    for index, source in enumerate(sources, start=1):
        result = ocr_pdf(source, dpi=args.dpi, force=args.force)
        print(
            f"[{index}/{len(sources)}] {result['status']} {result['source_pdf']} "
            f"({result['page_count']} pages, {result['character_count']} chars)",
            flush=True,
        )


if __name__ == "__main__":
    main()
