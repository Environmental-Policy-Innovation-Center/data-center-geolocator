# Illinois data-center regulatory pipeline

This directory contains the code used to download, OCR, and structure Illinois
EPA records for the facilities in the colleague-provided **Clean Permit Data**
worksheet. Generated PDFs, OCR text, temporary JSON, previews, and logs are
ignored by Git. The reviewed workbook and report are kept in `processed-data/`
and `reports/`.

## 1. Download the documents

`download_iepa_docuware.py` downloads all documents exposed by the Illinois
EPA Document Explorer for exactly one facility per invocation. It stops at
downloading and validating PDFs; it does not OCR or extract document text.

Requirements:

- Python 3.10 or newer
- Google Chrome (the default path is the standard macOS installation)
- Network access to `webapps.illinois.gov` and `docuware7.illinois.gov`

Example:

```bash
python3 pdf-scraping/download_iepa_docuware.py 170000063561
```

To process the unique agency IDs in the workbook's **Clean Permit Data** sheet:

```bash
python3 pdf-scraping/download_clean_permit_data.py \
  --workbook "/path/to/IL Data Centers.xlsx"
```

The batch command reads the workbook directly, removes duplicate agency IDs,
skips facilities whose existing manifests and SHA-256 hashes verify, continues
after per-facility failures, and writes
`iepa_pdfs/clean_permit_data_batch_manifest.json`. Each new facility is first
downloaded into a temporary directory and moved into place only after its
facility manifest is complete.

Use `--output-dir` to change the destination and `--chrome` (or
`CHROME_PATH`) when Chrome is installed elsewhere.

For each category, the downloader opens its short-lived DocuWare integration
link in a temporary headless-Chrome profile, selects each result row, and uses
DocuWare's **Download as PDF without annotations** command. The temporary
profile and authorization state are deleted when the run ends. Integration
URLs and authorization parameters are deliberately excluded from the output
manifest.

The output is organized as:

```text
iepa_pdfs/<agency-id>/
  manifest.json
  <category>/
    001_<docuware-filename>.pdf
    002_<docuware-filename>.pdf
```

The manifest records facility/category metadata, the visible result-row
values, byte sizes, and SHA-256 hashes. Result-row values follow the viewer's
column order: Type, Bureau ID, Site Name, Item Date, Permit ID, Doc Log,
Comment, and the trailing action column.

## 2. OCR air and compliance records

The OCR step is macOS-specific. It uses Poppler to render pages and Apple's
Vision framework to recognize text. The Python wrapper compiles
`vision_ocr.swift` on first use, so the compiled binary remains a disposable
file under `tmp/`.

Requirements: macOS, Xcode command-line tools, and `pdftoppm` on `PATH`.

```bash
python3 pdf-scraping/ocr_iepa_regulatory.py
```

Only the `Air_Permit_-_Final` and `Compliance` categories are OCR'd. Text and
per-document OCR metadata are written beneath `pdf-scraping/iepa_ocr_text/`.

## 3. Build the structured dataset

Install the Python dependencies:

```bash
python3 -m pip install -r pdf-scraping/requirements-regulatory.txt
```

First export the source facility rows, then assemble the provenance-first JSON:

```bash
python3 pdf-scraping/export_clean_permit_data.py \
  "/path/to/IL Data Centers.xlsx"

python3 pdf-scraping/build_regulatory_dataset.py
```

`build_regulatory_dataset.py` combines the facility rows, download manifests,
PDF page counts, and OCR evidence. It also contains the small number of
explicitly documented manual-review corrections used in the current result.
The generated JSON lives under `tmp/regulatory_workbook/`.

## 4. Build the workbook and report

The report builder is a normal Python script:

```bash
python3 reports/build_illinois_data_center_report.py
```

`pdf-scraping/regulatory-workbook/build_workbook.mjs` is the
workbook-generation source. It uses `@oai/artifact-tool`, which is supplied by
the Codex spreadsheet runtime rather than published as this repository's npm
dependency; invoke it through that runtime to rebuild the XLSX.

The default outputs are:

- `processed-data/illinois-data-center-regulatory-inventory.xlsx`
- `reports/illinois-data-center-backup-power-report.docx`

The committed PDF report is a rendered copy of the DOCX. PDF rendering and
visual QA are not automated by the repository scripts.

## Reproducibility boundary

Downloading, OCR, facility-row export, JSON assembly, and DOCX report
generation are ordinary repository scripts. Workbook generation uses the
Codex-provided spreadsheet runtime, and PDF rendering/visual QA used Codex
document tooling. Exact DocuWare results can also change over time as Illinois
EPA adds or re-indexes documents.
