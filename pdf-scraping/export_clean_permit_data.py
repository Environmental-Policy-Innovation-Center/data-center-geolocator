#!/usr/bin/env python3
"""Export rows from an XLSX worksheet to JSON using only the standard library."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from download_clean_permit_data import (
    MAIN_NS,
    cell_text,
    normalize_agency_id,
    shared_strings,
    worksheet_path,
)


def records_from_workbook(workbook_path: Path, sheet_name: str) -> list[dict]:
    with zipfile.ZipFile(workbook_path) as archive:
        strings = shared_strings(archive)
        sheet = ET.fromstring(archive.read(worksheet_path(archive, sheet_name)))

    rows: list[dict[int, str]] = []
    for row in sheet.findall(f".//{{{MAIN_NS}}}row"):
        values: dict[int, str] = {}
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            match = re.match(r"([A-Z]+)", cell.get("r", ""))
            if not match:
                continue
            index = 0
            for character in match.group(1):
                index = index * 26 + ord(character) - ord("A") + 1
            values[index - 1] = cell_text(cell, strings)
        rows.append(values)

    if not rows:
        raise ValueError(f"Worksheet {sheet_name!r} is empty")
    last_column = max(rows[0], default=-1)
    headers = [rows[0].get(index, f"column_{index + 1}") for index in range(last_column + 1)]
    records = [
        {header: row.get(index) or None for index, header in enumerate(headers)}
        for row in rows[1:]
        if row.get(0)
    ]
    for record in records:
        if record.get("Agency ID"):
            record["Agency ID"] = int(normalize_agency_id(record["Agency ID"]))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--sheet", default="Clean Permit Data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/regulatory_workbook/source_facilities.json"),
    )
    args = parser.parse_args()
    if not args.workbook.is_file():
        parser.error(f"Workbook not found: {args.workbook}")
    records = records_from_workbook(args.workbook, args.sheet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} facility rows to {args.output}")


if __name__ == "__main__":
    main()
