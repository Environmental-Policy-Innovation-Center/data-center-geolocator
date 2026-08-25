#!/usr/bin/env python3
"""Download IEPA documents for unique facilities in the Clean Permit Data sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from download_iepa_docuware import DEFAULT_CHROME, download_facility


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def normalize_agency_id(raw: str) -> str:
    value = raw.strip()
    if re.fullmatch(r"\d+", value):
        return value
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid agency ID value {raw!r}") from exc
    if decimal != decimal.to_integral_value():
        raise ValueError(f"Agency ID is not an integer: {raw!r}")
    return str(decimal.quantize(Decimal(1)))


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")) for item in root]


def worksheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = None
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.get("name") == sheet_name:
            relationship_id = sheet.get(f"{{{REL_NS}}}id")
            break
    if not relationship_id:
        raise ValueError(f"Worksheet {sheet_name!r} not found")

    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relation in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
        if relation.get("Id") == relationship_id:
            target = relation.get("Target", "")
            return "xl/" + target.lstrip("/")
    raise ValueError(f"Worksheet relationship for {sheet_name!r} not found")


def cell_text(cell: ET.Element, strings: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value = cell.findtext(f"{{{MAIN_NS}}}v", default="")
    if cell_type == "s" and value:
        return strings[int(value)]
    return value


def agency_ids_from_workbook(workbook_path: Path, sheet_name: str) -> list[str]:
    with zipfile.ZipFile(workbook_path) as archive:
        strings = shared_strings(archive)
        sheet = ET.fromstring(archive.read(worksheet_path(archive, sheet_name)))

    values: list[str] = []
    for row in sheet.findall(f".//{{{MAIN_NS}}}row"):
        if int(row.get("r", "0")) <= 1:
            continue
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            if re.fullmatch(r"B\d+", cell.get("r", "")):
                raw = cell_text(cell, strings)
                if raw.strip():
                    values.append(normalize_agency_id(raw))
                break
    if not values:
        raise ValueError(f"No agency IDs found in column B of {sheet_name!r}")
    return values


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_existing(facility_dir: Path) -> tuple[bool, str, int]:
    manifest_path = facility_dir / "manifest.json"
    if not manifest_path.is_file():
        return False, "manifest missing", 0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        documents = manifest["documents"]
        if manifest["document_count"] != len(documents):
            return False, "manifest count mismatch", 0
        for document in documents:
            path = facility_dir / document["saved_path"]
            if not path.is_file() or path.stat().st_size != document["byte_count"]:
                return False, f"missing or truncated file: {document['saved_path']}", 0
            if sha256(path) != document["sha256"]:
                return False, f"SHA-256 mismatch: {document['saved_path']}", 0
        return True, "verified", len(documents)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
        return False, f"invalid manifest: {exc}", 0


def write_batch_manifest(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_batch(args: argparse.Namespace) -> int:
    sheet_ids = agency_ids_from_workbook(args.workbook, args.sheet)
    unique_ids = list(dict.fromkeys(sheet_ids))
    duplicate_count = len(sheet_ids) - len(unique_ids)
    if args.limit is not None:
        unique_ids = unique_ids[: args.limit]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    batch_path = args.output_dir / "clean_permit_data_batch_manifest.json"
    batch: dict[str, Any] = {
        "source_workbook": str(args.workbook.resolve()),
        "source_sheet": args.sheet,
        "sheet_rows_with_agency_id": len(sheet_ids),
        "unique_agency_ids": len(dict.fromkeys(sheet_ids)),
        "duplicate_agency_ids_removed": duplicate_count,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "completed_at_utc": None,
        "facilities": [],
    }
    write_batch_manifest(batch_path, batch)
    print(
        f"Clean Permit Data: {len(sheet_ids)} rows, {len(dict.fromkeys(sheet_ids))} unique agency IDs "
        f"({duplicate_count} duplicate removed)",
        flush=True,
    )

    for position, agency_id in enumerate(unique_ids, start=1):
        facility_dir = args.output_dir / agency_id
        valid, reason, existing_count = validate_existing(facility_dir)
        if valid:
            result = {
                "agency_id": agency_id,
                "status": "skipped_verified",
                "document_count": existing_count,
                "message": reason,
            }
            batch["facilities"].append(result)
            write_batch_manifest(batch_path, batch)
            print(f"\n[{position}/{len(unique_ids)}] {agency_id}: verified existing download ({existing_count} documents)", flush=True)
            continue
        if facility_dir.exists():
            result = {
                "agency_id": agency_id,
                "status": "failed",
                "document_count": 0,
                "message": f"Existing directory is incomplete; refusing to overwrite it ({reason})",
            }
            batch["facilities"].append(result)
            write_batch_manifest(batch_path, batch)
            print(f"\n[{position}/{len(unique_ids)}] {agency_id}: FAILED - {result['message']}", flush=True)
            continue

        print(f"\n[{position}/{len(unique_ids)}] {agency_id}: downloading", flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix=f".{agency_id}-", dir=args.output_dir) as temporary:
                temporary_root = Path(temporary)
                manifest_path = download_facility(
                    agency_id,
                    temporary_root,
                    args.chrome,
                    args.timeout,
                    args.delay,
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                shutil.move(str(temporary_root / agency_id), facility_dir)
            result = {
                "agency_id": agency_id,
                "facility": manifest["facility"],
                "status": "downloaded",
                "document_count": manifest["document_count"],
                "message": "verified by facility downloader",
            }
            print(f"[{position}/{len(unique_ids)}] {agency_id}: complete ({result['document_count']} documents)", flush=True)
        except Exception as exc:
            result = {
                "agency_id": agency_id,
                "status": "failed",
                "document_count": 0,
                "message": str(exc),
            }
            print(f"[{position}/{len(unique_ids)}] {agency_id}: FAILED - {exc}", flush=True)
        batch["facilities"].append(result)
        write_batch_manifest(batch_path, batch)

    batch["completed_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    batch["summary"] = {
        "downloaded": sum(item["status"] == "downloaded" for item in batch["facilities"]),
        "skipped_verified": sum(item["status"] == "skipped_verified" for item in batch["facilities"]),
        "failed": sum(item["status"] == "failed" for item in batch["facilities"]),
        "documents": sum(item["document_count"] for item in batch["facilities"]),
    }
    write_batch_manifest(batch_path, batch)
    print(f"\nBatch manifest: {batch_path}", flush=True)
    print(json.dumps(batch["summary"], indent=2), flush=True)
    return 1 if batch["summary"]["failed"] else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True, help="Workbook containing the Clean Permit Data sheet")
    parser.add_argument("--sheet", default="Clean Permit Data")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "iepa_pdfs")
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH", DEFAULT_CHROME))
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int, help="Process only the first N unique IDs; useful for a smoke test")
    args = parser.parse_args()
    if not args.workbook.is_file():
        parser.error(f"Workbook not found: {args.workbook}")
    if not Path(args.chrome).is_file():
        parser.error(f"Google Chrome not found: {args.chrome}")
    if args.timeout <= 0 or args.delay < 0:
        parser.error("--timeout must be positive and --delay cannot be negative")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(run_batch(parse_args()))
