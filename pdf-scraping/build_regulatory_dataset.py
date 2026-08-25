#!/usr/bin/env python3
"""Build a provenance-first JSON dataset from IEPA manifests and OCR text."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PDF_ROOT = ROOT / "pdf-scraping" / "iepa_pdfs"
OCR_ROOT = ROOT / "pdf-scraping" / "iepa_ocr_text"
DEFAULT_FACILITY_SOURCE = ROOT / "tmp" / "regulatory_workbook" / "source_facilities.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "regulatory_workbook" / "regulatory_dataset.json"

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-one": 21, "twenty-two": 22,
    "twenty-three": 23, "twenty-four": 24, "twenty-five": 25,
    "twenty-six": 26, "twenty-seven": 27, "twenty-eight": 28,
    "twenty-nine": 29, "thirty": 30, "thirty-two": 32, "sixty-four": 64,
}
WORD_PATTERN = "|".join(sorted((re.escape(word) for word in NUMBER_WORDS), key=len, reverse=True))


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ;,.\n\t")


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = clean_space(str(value))
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def split_pages(text: str) -> list[str]:
    chunks = re.split(r"===== PAGE \d+ =====\n?", text)
    return [chunk for chunk in chunks[1:]]


def page_for_position(text: str, position: int) -> int:
    return len(re.findall(r"===== PAGE \d+ =====", text[:position])) or 1


def permit_type(text: str) -> tuple[str, str]:
    first = "\n".join(split_pages(text)[:5]).upper()
    if "FEDERALLY ENFORCEABLE STATE OPERATING PERMIT" in first or re.search(r"\bTO\s+OPERATE\b", first):
        kind = "FESOP / operating permit"
    elif "CLEAN AIR ACT PERMIT PROGRAM" in first or "CAAPP PERMIT" in first:
        kind = "CAAPP operating permit"
    elif "CONSTRUCTION PERMIT" in first or re.search(r"\bTO\s+CONSTRUCT\b", first):
        kind = "Construction permit"
    else:
        kind = "Air permit / application record"
    action = "Revised" if "REVISED" in first else "Initial or unspecified"
    return kind, action


def extract_subject(text: str) -> tuple[str | None, int | None]:
    pages = split_pages(text)
    for page_number, page in enumerate(pages[:5], start=1):
        match = re.search(r"Subject\s*:\s*([^\n]{3,160})", page, re.I)
        if match:
            return clean_space(match.group(1)), page_number
    return None, None


def generator_candidates(text: str) -> list[dict]:
    pages = split_pages(text)
    segments: list[tuple[int, str, bool]] = []
    for page_number, page in enumerate(pages[:5], start=1):
        for marker in re.finditer(r"consisting\s+of", page, re.I):
            start = max(0, marker.start() - 100)
            tail = page[marker.end():]
            ending = re.search(r"pursuant\s+to|This\s+permit\s+is\s+subject|standard\s+conditions", tail, re.I)
            end = marker.end() + (ending.start() if ending else min(len(tail), 1600))
            segments.append((page_number, page[start:end], True))
        for marker in re.finditer(r"Description of emission units? to be operated", page, re.I):
            segments.append((page_number, page[marker.start():marker.start() + 900], False))
    if not segments:
        segments = [(page_number, page, False) for page_number, page in enumerate(pages[:5], start=1)]
    patterns = [
        re.compile(
            rf"(?:(?P<word>{WORD_PATTERN})\s*)?\(\s*(?P<count>\d{{1,3}})\s*\)"
            rf"(?P<middle>.{{0,90}}?)(?P<kw>[\d, ]{{3,8}})\s*k[WwNn]"
            rf"(?:e)?(?:\s*\(\s*(?P<hp>[\d, ]{{3,8}})\s*(?:engine\s*)?[Hh][Pp]\s*\))?"
            rf"(?P<tail>.{{0,150}}?(?:generator|genset)(?:s|\s+sets?)?)",
            re.I | re.S,
        ),
        re.compile(
            rf"(?P<word>{WORD_PATTERN})\s+(?P<kw>[\d, ]{{3,8}})\s*k[WwNn]"
            rf"(?:e)?(?:\s*\(\s*(?P<hp>[\d, ]{{3,8}})\s*(?:engine\s*)?[Hh][Pp]\s*\))?"
            rf"(?P<tail>.{{0,150}}?(?:generator|genset)(?:s|\s+sets?)?)",
            re.I | re.S,
        ),
        re.compile(
            rf"(?:(?P<word>{WORD_PATTERN})\s*)?\(\s*(?P<count>\d{{1,3}})\s*\)"
            rf"(?P<middle>.{{0,70}}?)(?P<hp>[\d,]{{3,6}})\s*-?\s*(?:engine\s*)?[Hh][Pp]"
            rf"(?P<tail>.{{0,150}}?(?:generator|genset)(?:s|\s+sets?)?)",
            re.I | re.S,
        ),
        re.compile(
            rf"(?P<kw>[\d, ]{{3,8}})\s*k[WwNn](?:e)?"
            rf"(?:\s*\(\s*(?P<hp>[\d, ]{{3,8}})\s*(?:engine\s*)?[Hh][Pp]\s*\))?"
            rf"(?P<tail>.{{0,120}}?(?:emergency|standby|backup).{{0,80}}?(?:generator|genset))",
            re.I | re.S,
        ),
    ]
    found: list[dict] = []
    for page, search_text, is_inventory in segments:
      search_text = unicodedata.normalize("NFKD", search_text).encode("ascii", "ignore").decode("ascii")
      for pattern in patterns:
        for match in pattern.finditer(search_text):
            count_value = match.groupdict().get("count")
            word_value = match.groupdict().get("word")
            count = int(count_value or (NUMBER_WORDS[word_value.lower()] if word_value else 1))
            kw_raw = match.groupdict().get("kw")
            hp_raw = match.groupdict().get("hp")
            kw = int(re.sub(r"[^0-9]", "", kw_raw)) if kw_raw else None
            hp = int(re.sub(r"[^0-9]", "", hp_raw)) if hp_raw else None
            middle = match.groupdict().get("middle") or ""
            if hp is None:
                middle_hp = re.search(r"([\d, ]{3,8})\s*(?:BHP|HP\s*Engine)", middle, re.I)
                hp = int(re.sub(r"[^0-9]", "", middle_hp.group(1))) if middle_hp else None
            if count < 1 or count > 200 or (kw is not None and not 100 <= kw <= 10000) or (hp is not None and not 100 <= hp <= 20000):
                continue
            start = max(0, match.start() - 100)
            end = min(len(search_text), match.end() + 100)
            evidence = clean_space(search_text[start:end].replace("=====", ""))
            if not re.search(r"emergency|standby|backup", evidence, re.I):
                continue
            unit_search = clean_space(search_text[match.start():min(len(search_text), match.end() + 180)])
            unit_match = re.search(
                r"\bG[- ]?\d+(?:\s*(?:thru|through|to|-)\s*G?[- ]?\d+)?\b|"
                r"\bGenerator\s*#?\s*\d+(?:\s*(?:thru|through|to|-)\s*#?\s*\d+)?\b",
                unit_search,
                re.I,
            )
            unit_ids = clean_space(unit_match.group(0)) if unit_match else None
            control = None
            if re.search(r"diesel particulate filter|\bDPF\b", evidence, re.I):
                control = "Diesel particulate filter"
            elif re.search(r"selective catalytic reduction|\bSCR\b", evidence, re.I):
                control = "Selective catalytic reduction"
            elif re.search(r"oxidation catalyst", evidence, re.I):
                control = "Oxidation catalyst"
            manufacturer_match = re.search(
                r"\b(Caterpillar|Cummins|MTU|Kohler|Generac|Rolls[- ]Royce)(?:\s+(?:Model\s+)?([A-Z0-9.-]+))?",
                evidence,
                re.I,
            )
            manufacturer_model = clean_space(manufacturer_match.group(0)) if manufacturer_match else None
            found.append({
                "explicit_count": bool(count_value or word_value),
                "quantity": count,
                "rated_kw_each": kw,
                "rated_hp_each": hp,
                "unit_ids": unit_ids,
                "fuel": "Diesel / distillate fuel oil",
                "manufacturer_model": manufacturer_model,
                "control_equipment": control,
                "source_page": page,
                "confidence": "High" if is_inventory else "Medium",
                "evidence_text": evidence[:500],
            })
    # Remove redundant HP-only matches and exact repeats from the same inventory statement.
    deduped: list[dict] = []
    seen: set[tuple] = set()
    for candidate in sorted(found, key=lambda item: (item["source_page"], item["rated_kw_each"] is None)):
        if not candidate["explicit_count"] and candidate["quantity"] == 1 and any(
            other["source_page"] == candidate["source_page"]
            and other["quantity"] > 1
            and other["rated_kw_each"] == candidate["rated_kw_each"]
            and (other["rated_hp_each"] == candidate["rated_hp_each"] or candidate["rated_hp_each"] is None)
            for other in found
        ):
            continue
        if candidate["rated_kw_each"] is None and any(
            other["source_page"] == candidate["source_page"]
            and other["quantity"] == candidate["quantity"]
            and other["rated_hp_each"] == candidate["rated_hp_each"]
            and other["rated_kw_each"] is not None
            for other in found
        ):
            continue
        key = (
            candidate["source_page"], candidate["quantity"], candidate["rated_kw_each"],
            candidate["rated_hp_each"], candidate["unit_ids"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def latest_group_context(page: str, position: int) -> str:
    context = page[max(0, position - 900):position]
    matches = list(re.finditer(
        rf"(?:(?:{WORD_PATTERN})\s*)?\(\s*\d{{1,3}}\s*\).{{0,100}}?[\d,]{{3,6}}\s*k[WwNn].{{0,160}}?(?:generator|genset)",
        context,
        re.I | re.S,
    ))
    return clean_space(matches[-1].group(0)) if matches else clean_space(context[-300:])


def runtime_limits(text: str) -> list[dict]:
    results: list[dict] = []
    for page_number, page in enumerate(split_pages(text), start=1):
        lines = page.splitlines()
        offsets: list[int] = []
        running = 0
        for line in lines:
            offsets.append(running)
            running += len(line) + 1
        for line_index, line in enumerate(lines):
            if not re.search(r"Hours\s+of\s+Operation", line, re.I):
                continue
            window = " ".join(lines[max(0, line_index - 2):min(len(lines), line_index + 4)])
            values = [int(value.replace(",", "")) for value in re.findall(r"([\d,]+)\s*hours?/year", window, re.I)]
            if not values:
                continue
            context = latest_group_context(page, offsets[line_index])
            each_value = values[0]
            results.append({
                "limit_type": "Runtime - individual",
                "equipment_scope": context,
                "value": each_value,
                "unit": "hours/year per generator",
                "averaging_period": "Annual",
                "source_page": page_number,
                "evidence_text": clean_space(window),
            })
            if len(values) > 1:
                results.append({
                    "limit_type": "Runtime - aggregate",
                    "equipment_scope": context,
                    "value": values[1],
                    "unit": "hours/year total",
                    "averaging_period": "Annual",
                    "source_page": page_number,
                    "evidence_text": clean_space(window),
                })
        for match in re.finditer(
            r"Total diesel fuel burned shall not exceed\s*([\d,]+)\s*gallons/month\s*and\s*([\d,]+)\s*gallons/year",
            page,
            re.I | re.S,
        ):
            context = latest_group_context(page, match.start())
            for value, unit, period in (
                (match.group(1), "gallons/month", "Monthly"),
                (match.group(2), "gallons/year", "Annual"),
            ):
                results.append({
                    "limit_type": "Diesel fuel consumption",
                    "equipment_scope": context,
                    "value": int(value.replace(",", "")),
                    "unit": unit,
                    "averaging_period": period,
                    "source_page": page_number,
                    "evidence_text": clean_space(match.group(0)),
                })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-source", type=Path, default=DEFAULT_FACILITY_SOURCE)
    parser.add_argument("--pdf-root", type=Path, default=PDF_ROOT)
    parser.add_argument("--ocr-root", type=Path, default=OCR_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.facility_source.is_file():
        parser.error(f"Facility source JSON not found: {args.facility_source}")
    if not args.pdf_root.is_dir():
        parser.error(f"Downloaded PDF directory not found: {args.pdf_root}")

    facility_source = json.loads(args.facility_source.read_text(encoding="utf-8"))
    facility_ids_by_agency: dict[str, list[str]] = defaultdict(list)
    for record in facility_source:
        facility_ids_by_agency[str(int(record["Agency ID"]))].append(record["wa"])

    manifests = {}
    for path in args.pdf_root.glob("*/manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifests[str(manifest["agency_id"])] = manifest

    facilities = []
    for record in facility_source:
        agency_id = str(int(record["Agency ID"]))
        manifest = manifests.get(agency_id, {})
        facilities.append({
            "facility_id": record["wa"],
            "agency_id": agency_id,
            "organization_name": record.get("Organization Name"),
            "site_name": record.get("Site Name") or record.get("Organization Name"),
            "street": record.get("Street"),
            "city": None,
            "county": None,
            "state": "IL",
            "zip": None,
            "latitude": None,
            "longitude": None,
            "document_explorer_url": record.get("Doc Link"),
            "manifest_facility_name": manifest.get("facility"),
            "manifest_address": manifest.get("address"),
            "data_quality_notes": "Shared Document Explorer record" if len(facility_ids_by_agency[agency_id]) > 1 else None,
        })

    documents = []
    permits_limits = []
    generators = []
    document_lookup = {}
    air_document_details = []
    for agency_id, manifest in sorted(manifests.items()):
        for document in manifest.get("documents", []):
            relative_pdf = Path(agency_id) / document["saved_path"]
            pdf_path = args.pdf_root / relative_pdf
            category_slug = pdf_path.parent.name
            category_code = {
                "Air_Permit_-_Final": "AIR",
                "Compliance": "COMP",
                "NPDES_Permit": "NPDES",
                "Site_Remediation_-_Technical": "SR",
            }.get(category_slug, "DOC")
            document_id = f"DOC-{agency_id}-{category_code}-{document['row_index'] + 1:03d}"
            ocr_text_path = (args.ocr_root / relative_pdf).with_suffix(".txt")
            ocr_meta_path = (args.ocr_root / relative_pdf).with_suffix(".ocr.json")
            ocr_text = ocr_text_path.read_text(encoding="utf-8") if ocr_text_path.exists() else ""
            ocr_metadata = json.loads(ocr_meta_path.read_text(encoding="utf-8")) if ocr_meta_path.exists() else {}
            pages = ocr_metadata.get("page_count")
            if pages is None:
                pages = len(PdfReader(pdf_path).pages)
            row_text = document.get("row_text") or []
            indexed_source_id = row_text[1] if len(row_text) > 1 else None
            indexed_name = row_text[2] if len(row_text) > 2 else None
            document_date = parse_date(row_text[3] if len(row_text) > 3 else None)
            application_number = row_text[4] if len(row_text) > 4 else None
            linked_facilities = facility_ids_by_agency.get(agency_id, [])
            actual_source_id = indexed_source_id
            identity_status = "Unreviewed"
            identity_notes = None
            source_ids_found = sorted(set(re.findall(r"\b\d{6}[A-Z]{3}\b", "\n".join(split_pages(ocr_text)[:4])))) if ocr_text else []
            if indexed_source_id and source_ids_found:
                if indexed_source_id in source_ids_found and len(source_ids_found) == 1:
                    identity_status = "Consistent"
                elif any(source_id != indexed_source_id for source_id in source_ids_found):
                    identity_status = "Possible mismatch"
                    identity_notes = f"OCR found source IDs: {', '.join(source_ids_found)}"
            if str(relative_pdf) == "170000063561/Air_Permit_-_Final/005_031600GNA.pdf":
                actual_source_id = "031440AVZ"
                linked_facilities = ["IL_N_18"]
                identity_status = "Confirmed mismatch"
                identity_notes = "DocuWare cover is 031600GNA; permit body is Equinix CH-5, 2001 Lunt Ave, source 031440AVZ, application 23080013."
            if str(relative_pdf) == "170002394647/Compliance/001_043407ACW.pdf":
                actual_source_id = "089407ALK"
                linked_facilities = []
                identity_status = "Confirmed mismatch"
                identity_notes = "Compliance agreement is for CyrusOne Aurora Facility, 2905 Diehl Rd, source 089407ALK; it is indexed under 043407ACW."
            document_record = {
                "document_id": document_id,
                "facility_ids": "; ".join(linked_facilities),
                "agency_id_as_indexed": agency_id,
                "indexed_source_id": indexed_source_id,
                "actual_source_id": actual_source_id,
                "indexed_facility_name": indexed_name,
                "document_type": document.get("category"),
                "document_date": document_date,
                "application_or_log_number": application_number,
                "page_count": pages,
                "document_explorer_url": manifest.get("source_url"),
                "local_pdf_path": str((Path("pdf-scraping") / "iepa_pdfs" / relative_pdf)),
                "ocr_text_path": (
                    str(ocr_text_path.resolve().relative_to(ROOT.resolve()))
                    if ocr_text_path.exists() and ocr_text_path.resolve().is_relative_to(ROOT.resolve())
                    else (str(ocr_text_path.resolve()) if ocr_text_path.exists() else None)
                ),
                "ocr_status": "OCR complete" if ocr_text_path.exists() else "Not OCR'd - outside generator scope",
                "ocr_mean_line_confidence": ocr_metadata.get("mean_line_confidence"),
                "sha256": document.get("sha256"),
                "index_match_status": identity_status,
                "notes": identity_notes,
            }
            documents.append(document_record)
            document_lookup[document_id] = document_record

            if category_slug != "Air_Permit_-_Final" or not ocr_text:
                continue
            ptype, action = permit_type(ocr_text)
            subject, subject_page = extract_subject(ocr_text)
            permit_record_id = f"PERMIT-{document_id}"
            permit_row = {
                "record_id": permit_record_id,
                "facility_ids": document_record["facility_ids"],
                "agency_id": agency_id,
                "document_id": document_id,
                "permit_or_source_id": actual_source_id,
                "application_number": application_number,
                "permit_date": document_date,
                "permit_type": ptype,
                "action": action,
                "subject": subject,
                "limit_type": "Permit metadata",
                "equipment_scope": None,
                "pollutant": None,
                "value": None,
                "unit": None,
                "averaging_period": None,
                "effective_from": document_date,
                "effective_to": None,
                "source_page": subject_page,
                "extraction_method": "Manifest metadata + OCR",
                "review_status": "OCR extracted - review recommended",
                "evidence_text": subject,
                "notes": identity_notes,
            }
            permits_limits.append(permit_row)
            air_document_details.append({"agency_id": agency_id, "document_id": document_id, "date": document_date, "permit_type": ptype})
            for index, candidate in enumerate(generator_candidates(ocr_text), start=1):
                generators.append({
                    "generator_record_id": f"GEN-{document_id}-{index:02d}",
                    "facility_ids": document_record["facility_ids"],
                    "agency_id": agency_id,
                    "document_id": document_id,
                    "permit_date": document_date,
                    "permit_type": ptype,
                    "evidence_role": None,
                    "unit_ids": candidate["unit_ids"],
                    "quantity": candidate["quantity"],
                    "rated_kw_each": candidate["rated_kw_each"],
                    "rated_hp_each": candidate["rated_hp_each"],
                    "fuel": candidate["fuel"],
                    "manufacturer_model": candidate["manufacturer_model"],
                    "control_equipment": candidate["control_equipment"],
                    "equipment_status": "Permitted / described",
                    "source_page": candidate["source_page"],
                    "extraction_method": "OCR pattern extraction",
                    "review_status": "OCR extracted - review recommended",
                    "confidence": candidate["confidence"],
                    "evidence_text": candidate["evidence_text"],
                })
            for index, limit in enumerate(runtime_limits(ocr_text), start=1):
                permits_limits.append({
                    "record_id": f"LIMIT-{document_id}-{index:03d}",
                    "facility_ids": document_record["facility_ids"],
                    "agency_id": agency_id,
                    "document_id": document_id,
                    "permit_or_source_id": actual_source_id,
                    "application_number": application_number,
                    "permit_date": document_date,
                    "permit_type": ptype,
                    "action": action,
                    "subject": subject,
                    "limit_type": limit["limit_type"],
                    "equipment_scope": limit["equipment_scope"],
                    "pollutant": None,
                    "value": limit["value"],
                    "unit": limit["unit"],
                    "averaging_period": limit["averaging_period"],
                    "effective_from": document_date,
                    "effective_to": None,
                    "source_page": limit["source_page"],
                    "extraction_method": "OCR pattern extraction",
                    "review_status": "OCR extracted - review recommended",
                    "evidence_text": limit["evidence_text"],
                    "notes": None,
                })

    latest_operating_by_agency: dict[str, str] = {}
    for detail in air_document_details:
        if "operating" not in detail["permit_type"].lower() or not detail["date"]:
            continue
        previous = latest_operating_by_agency.get(detail["agency_id"])
        if previous is None or detail["date"] > document_lookup[previous]["document_date"]:
            latest_operating_by_agency[detail["agency_id"]] = detail["document_id"]
    for generator in generators:
        latest = latest_operating_by_agency.get(generator["agency_id"])
        if generator["document_id"] == latest:
            generator["evidence_role"] = "Latest operating-permit inventory"
        elif "construction" in generator["permit_type"].lower():
            baseline_date = document_lookup[latest]["document_date"] if latest else None
            generator["evidence_role"] = (
                "Post-baseline construction addition"
                if baseline_date and generator["permit_date"] and generator["permit_date"] > baseline_date
                else "Construction-permit equipment"
            )
        elif "operating" in generator["permit_type"].lower():
            generator["evidence_role"] = "Historical operating-permit inventory"
        else:
            generator["evidence_role"] = "Other permit/application evidence"

    selected_documents_by_agency: dict[str, set[str]] = defaultdict(set)
    for agency_id in manifests:
        latest = latest_operating_by_agency.get(agency_id)
        agency_generators = [row for row in generators if row["agency_id"] == agency_id]
        if latest and any(row["document_id"] == latest for row in agency_generators):
            selected_documents_by_agency[agency_id].add(latest)
            baseline_date = document_lookup[latest]["document_date"]
            for row in agency_generators:
                if (
                    "construction" in row["permit_type"].lower()
                    and baseline_date and row["permit_date"] and row["permit_date"] > baseline_date
                ):
                    selected_documents_by_agency[agency_id].add(row["document_id"])
        elif agency_generators:
            latest_date = max((row["permit_date"] or "0000-00-00") for row in agency_generators)
            selected_documents_by_agency[agency_id].update(
                row["document_id"] for row in agency_generators if (row["permit_date"] or "0000-00-00") == latest_date
            )
            for row in agency_generators:
                if row["document_id"] in selected_documents_by_agency[agency_id]:
                    row["evidence_role"] = "Most recent permit with extractable inventory"
    for generator in generators:
        generator["selected_for_workbook"] = generator["document_id"] in selected_documents_by_agency[generator["agency_id"]]

    # Do not treat a permit that was filed under the wrong DocuWare index as a
    # second current inventory when the same facility has its own index.
    for generator in generators:
        if generator["document_id"] == "DOC-170000063561-AIR-005":
            generator["selected_for_workbook"] = False
            generator["evidence_role"] = "Misfiled duplicate - retained in document catalog"

    # OCR patterns can extract the same clause twice: once from the kW phrase
    # and once from the parenthetical HP phrase.  Remove only highly-overlapping
    # lower-information duplicates from the selected inventory.
    def evidence_tokens(value: str | None) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", (value or "").lower()))

    selected = [row for row in generators if row["selected_for_workbook"]]
    for row in selected:
        row_tokens = evidence_tokens(row.get("evidence_text"))
        for other in selected:
            if row is other or row["document_id"] != other["document_id"]:
                continue
            other_tokens = evidence_tokens(other.get("evidence_text"))
            union = row_tokens | other_tokens
            overlap = len(row_tokens & other_tokens) / len(union) if union else 0
            same_rating = row.get("rated_kw_each") == other.get("rated_kw_each") and row.get("quantity") == other.get("quantity")
            hp_only_duplicate = row.get("rated_kw_each") is None and other.get("rated_kw_each") is not None and overlap >= 0.72
            poorer_exact_duplicate = same_rating and overlap >= 0.72 and row.get("rated_hp_each") is None and other.get("rated_hp_each") is not None
            if hp_only_duplicate or poorer_exact_duplicate:
                row["selected_for_workbook"] = False
                row["evidence_role"] = "Overlapping OCR extraction - excluded from current inventory"
                break

    # The HCSC permit's page layout places the quantities after the kW values,
    # which caused the generic OCR matcher to pair them incorrectly.  These two
    # groups were checked directly against the permit description on page 2.
    for row in generators:
        if row["document_id"] != "DOC-170002049806-AIR-002" or not row["selected_for_workbook"]:
            continue
        if row.get("rated_hp_each") == 2012:
            row["quantity"], row["rated_kw_each"], row["unit_ids"] = 4, 1500, "EGEN1-EGEN4"
        elif row.get("rated_hp_each") == 2682:
            row["quantity"], row["rated_kw_each"], row["unit_ids"] = 1, 2000, "EGEN5"
        row["extraction_method"] = "OCR + manual verification"
        row["review_status"] = "Reviewed"
        row["confidence"] = "High"

    # Manually reviewed compliance records. The workbook retains the CCA's allegation language.
    compliance = []
    compliance_id = 1
    for document in documents:
        if document["document_type"] != "Compliance":
            continue
        text_path = Path(document["ocr_text_path"]) if document["ocr_text_path"] else None
        if text_path and not text_path.is_absolute():
            text_path = ROOT / text_path
        text = text_path.read_text(encoding="utf-8") if text_path and text_path.exists() else ""
        first_pages = "\n".join(split_pages(text)[:3])
        notice_match = re.search(r"\bA-\d{4}-\d{5}\b", first_pages)
        notice = notice_match.group(0) if notice_match else document["application_or_log_number"]
        summaries = []
        if document["document_id"] == "DOC-170000063561-COMP-001":
            summaries = [{"page": 1, "type": "Reporting violation allegation", "pollutant": None, "equipment": None, "description": "Illinois EPA alleged that Equinix failed to submit its 2016 Annual Emissions Report by the May 1, 2017 deadline.", "corrective": "CCA states that the 2016 Annual Emissions Report was submitted on July 17, 2017.", "status": "Executed compliance commitment agreement"}]
        elif document["document_id"] == "DOC-170000063561-COMP-002":
            summaries = [
                {"page": 1, "type": "Emission-limit exceedance allegation", "pollutant": "CO", "equipment": "G7-G10", "description": "Illinois EPA alleged exceedance of the 3.45 lb/hour CO limit for emergency generators G7-G10.", "corrective": "Submit monthly and annual CO/VOM calculations from 2016 onward and a compliance plan.", "status": "Executed compliance commitment agreement"},
                {"page": 1, "type": "Emission-limit exceedance allegation", "pollutant": "VOM", "equipment": "G7-G10", "description": "Illinois EPA alleged exceedance of the 0.76 lb/hour VOM limit for emergency generators G7-G10.", "corrective": "Submit monthly and annual CO/VOM calculations from 2016 onward and a compliance plan.", "status": "Executed compliance commitment agreement"},
                {"page": 2, "type": "Deviation-reporting violation allegation", "pollutant": None, "equipment": None, "description": "Illinois EPA alleged failure to notify the Compliance Section within 30 days of permit deviations.", "corrective": "Submit an internal policy for complete, accurate, and timely deviation reports.", "status": "Executed compliance commitment agreement"},
            ]
        elif document["document_id"] == "DOC-170002394647-COMP-001":
            summaries = [{"page": 1, "type": "Reporting violation allegation", "pollutant": None, "equipment": None, "description": "Illinois EPA alleged that CyrusOne Aurora Facility failed to submit its 2017 Annual Emissions Report by the May 1, 2018 deadline.", "corrective": "CCA states that the 2017 Annual Emissions Report was submitted on July 26, 2018.", "status": "Executed compliance commitment agreement"}]
        elif document["document_id"] == "DOC-170002409427-COMP-001":
            summaries = [{"page": 1, "type": "Reporting violation allegation", "pollutant": None, "equipment": None, "description": "Illinois EPA alleged that Ensono Data Center failed to submit its 2020 Annual Emissions Report by the May 1, 2021 deadline.", "corrective": "CCA states that the 2020 Annual Emissions Report was received on August 23, 2021.", "status": "Executed compliance commitment agreement"}]
        elif document["document_id"] == "DOC-170002516267-COMP-001":
            summaries = [{"page": 1, "type": "Construction-permit violation allegation", "pollutant": None, "equipment": "Four emergency generators", "description": "Illinois EPA alleged that SDC CHI II Busse may have constructed four generators without first obtaining an air construction permit.", "corrective": "Provide a complete emission-unit inventory with construction and operation dates and confirm the June 13, 2022 operating-permit application was complete and accurate; both items were recorded as received August 10, 2022.", "status": "Executed compliance commitment agreement"}]
        else:
            allegation = re.search(r"(?:Allegation|Allegations) of Violations(.{0,1800})", first_pages, re.I | re.S)
            summary_text = clean_space(allegation.group(1))[:900] if allegation else clean_space(first_pages)[:900]
            summaries = [{"page": 1, "type": "Compliance record - review needed", "pollutant": None, "equipment": None, "description": summary_text, "corrective": None, "status": "OCR extracted - review recommended"}]
        for summary in summaries:
            compliance.append({
                "compliance_id": f"COMP-{compliance_id:03d}",
                "facility_ids": document["facility_ids"],
                "agency_id": document["agency_id_as_indexed"],
                "document_id": document["document_id"],
                "event_type": summary["type"],
                "notice_number": notice,
                "event_date": document["document_date"],
                "pollutant": summary["pollutant"],
                "equipment_scope": summary["equipment"],
                "allegation_or_finding": "Allegation" if "alleg" in summary["type"].lower() else "Unclassified",
                "description": summary["description"],
                "corrective_action": summary["corrective"],
                "resolution_status": summary["status"],
                "penalty_amount": None,
                "source_page": summary["page"],
                "extraction_method": "Manual review" if document["document_id"] in {"DOC-170000063561-COMP-001", "DOC-170000063561-COMP-002", "DOC-170002394647-COMP-001", "DOC-170002409427-COMP-001", "DOC-170002516267-COMP-001"} else "OCR summary extraction",
                "review_status": "Reviewed" if document["document_id"] in {"DOC-170000063561-COMP-001", "DOC-170000063561-COMP-002", "DOC-170002394647-COMP-001", "DOC-170002409427-COMP-001", "DOC-170002516267-COMP-001"} else "Review recommended",
                "notes": "CCA provides allegations and agreed actions; underlying calculations may not be included.",
            })
            compliance_id += 1

    dataset = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "facilities": facilities,
        "documents": documents,
        "generators": generators,
        "permits_limits": permits_limits,
        "compliance": compliance,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: len(value) for key, value in dataset.items() if isinstance(value, list)}, indent=2))


if __name__ == "__main__":
    main()
