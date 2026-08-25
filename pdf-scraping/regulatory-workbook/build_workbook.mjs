import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "../..");
const [dataPath = path.join(root, "tmp/regulatory_workbook/regulatory_dataset.json"), outputPath = path.join(root, "processed-data/illinois-data-center-regulatory-inventory.xlsx")] = process.argv.slice(2);
const outputDir = path.dirname(outputPath);
const previewDir = path.join(root, "tmp/regulatory_workbook/previews");
const data = JSON.parse(await fs.readFile(dataPath, "utf8"));

const workbook = Workbook.create();

function dateValue(value) {
  if (!value) return null;
  return new Date(`${value}T00:00:00Z`);
}

function shortText(value, length = 240) {
  if (value === null || value === undefined) return null;
  const text = String(value).replace(/\s+/g, " ").trim();
  return text.length > length ? `${text.slice(0, length - 1)}...` : text;
}

function columnName(index) {
  let value = index + 1;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
}

function addSheet({ name, tableName, headers, rows, widths, wrapColumns = [], dateColumns = [], numberFormats = {}, freezeColumns = 1 }) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const lastColumn = columnName(headers.length - 1);
  const lastRow = rows.length + 1;
  sheet.getRange(`A1:${lastColumn}${lastRow}`).values = [headers, ...rows];
  const header = sheet.getRange(`A1:${lastColumn}1`);
  header.format = {
    fill: "#155E75",
    font: { bold: true, color: "#FFFFFF", size: 10 },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: "#0E4F61" },
  };
  header.format.rowHeightPx = 34;
  if (rows.length) {
    const body = sheet.getRange(`A2:${lastColumn}${lastRow}`);
    body.format.font = { name: "Arial", size: 9, color: "#17202A" };
    body.format.verticalAlignment = "top";
    body.format.rowHeightPx = 42;
  }
  widths.forEach((width, index) => {
    sheet.getRange(`${columnName(index)}1:${columnName(index)}${lastRow}`).format.columnWidth = width;
  });
  wrapColumns.forEach((index) => {
    sheet.getRange(`${columnName(index)}1:${columnName(index)}${lastRow}`).format.wrapText = true;
  });
  dateColumns.forEach((index) => {
    if (rows.length) sheet.getRange(`${columnName(index)}2:${columnName(index)}${lastRow}`).format.numberFormat = "yyyy-mm-dd";
  });
  for (const [indexText, format] of Object.entries(numberFormats)) {
    const index = Number(indexText);
    if (rows.length) sheet.getRange(`${columnName(index)}2:${columnName(index)}${lastRow}`).format.numberFormat = format;
  }
  if (rows.length) {
    const table = sheet.tables.add(`A1:${lastColumn}${lastRow}`, true, tableName);
    table.style = "TableStyleMedium2";
    table.showFilterButton = true;
  }
  sheet.freezePanes.freezeRows(1);
  if (freezeColumns) sheet.freezePanes.freezeColumns(freezeColumns);
  return { sheet, lastRow, lastColumn };
}

const selectedGenerators = data.generators.filter((row) => row.selected_for_workbook);

function linkedToFacility(row, facilityId) {
  return String(row.facility_ids ?? "").split(";").map((value) => value.trim()).includes(facilityId);
}

function facilitySummary(facilityId) {
  const linkedDocuments = data.documents.filter((row) => linkedToFacility(row, facilityId));
  const linkedGenerators = selectedGenerators.filter((row) => linkedToFacility(row, facilityId));
  return {
    documentCount: linkedDocuments.length,
    airPermitCount: linkedDocuments.filter((row) => row.document_type === "Air Permit - Final").length,
    complianceCount: linkedDocuments.filter((row) => row.document_type === "Compliance").length,
    generatorGroupRecords: linkedGenerators.length,
    selectedGeneratorCount: linkedGenerators.reduce((total, row) => total + (Number(row.quantity) || 0), 0),
    selectedCapacityKw: linkedGenerators.reduce(
      (total, row) => total + (Number(row.quantity) || 0) * (Number(row.rated_kw_each) || 0),
      0,
    ),
  };
}

const facilityHeaders = [
  "Facility ID", "Agency ID", "Organization Name", "Site Name", "Street", "City", "County", "State", "ZIP",
  "Latitude", "Longitude", "Document Explorer URL", "Document Count", "Air Permit Count", "Compliance Count",
  "Generator Group Records", "Selected Generator Count", "Selected Capacity (kW)", "Manifest Facility Name",
  "Manifest Address", "Data Quality Notes",
];
const facilityRows = data.facilities.map((row) => {
  const summary = facilitySummary(row.facility_id);
  return [
    row.facility_id, row.agency_id, row.organization_name, row.site_name, row.street, row.city, row.county, row.state, row.zip,
    row.latitude, row.longitude, row.document_explorer_url, summary.documentCount, summary.airPermitCount,
    summary.complianceCount, summary.generatorGroupRecords, summary.selectedGeneratorCount, summary.selectedCapacityKw,
    row.manifest_facility_name, row.manifest_address, row.data_quality_notes,
  ];
});
const facilities = addSheet({
  name: "Facilities", tableName: "FacilitiesTable", headers: facilityHeaders, rows: facilityRows,
  widths: [14, 18, 27, 28, 24, 18, 16, 8, 10, 12, 12, 48, 12, 12, 12, 14, 14, 17, 28, 38, 34],
  wrapColumns: [2, 3, 4, 11, 18, 19, 20], numberFormats: { 1: "0", 9: "0.000000", 10: "0.000000", 12: "#,##0", 13: "#,##0", 14: "#,##0", 15: "#,##0", 16: "#,##0", 17: "#,##0" },
  freezeColumns: 2,
});

const documentHeaders = [
  "Document ID", "Facility IDs", "Agency ID as Indexed", "Indexed Source ID", "Actual Source ID", "Indexed Facility Name",
  "Document Type", "Document Date", "Application or Log Number", "Page Count", "Document Explorer URL", "Local PDF Path",
  "OCR Text Path", "OCR Status", "OCR Mean Line Confidence", "SHA-256", "Index Match Status", "Notes",
];
const documentRows = data.documents.map((row) => [
  row.document_id, row.facility_ids, row.agency_id_as_indexed, row.indexed_source_id, row.actual_source_id,
  row.indexed_facility_name, row.document_type, dateValue(row.document_date), row.application_or_log_number, row.page_count,
  row.document_explorer_url, row.local_pdf_path, row.ocr_text_path, row.ocr_status, row.ocr_mean_line_confidence,
  row.sha256, row.index_match_status, shortText(row.notes, 300),
]);
const documents = addSheet({
  name: "Documents", tableName: "DocumentsTable", headers: documentHeaders, rows: documentRows,
  widths: [31, 18, 20, 18, 18, 29, 23, 13, 20, 11, 48, 48, 48, 27, 16, 30, 19, 48],
  wrapColumns: [5, 6, 10, 11, 12, 13, 17], dateColumns: [7], numberFormats: { 2: "0", 9: "#,##0", 14: "0.0%" }, freezeColumns: 2,
});

const generatorHeaders = [
  "Generator Record ID", "Facility IDs", "Agency ID", "Document ID", "Permit Date", "Permit Type", "Evidence Role",
  "Unit IDs", "Quantity", "Rated kW Each", "Group Capacity (kW)", "Rated HP Each", "Fuel", "Manufacturer / Model",
  "Control Equipment", "Equipment Status", "Source Page", "Extraction Method", "Review Status", "Confidence", "Evidence Text",
];
const generatorRows = selectedGenerators.map((row) => [
  row.generator_record_id, row.facility_ids, row.agency_id, row.document_id, dateValue(row.permit_date), row.permit_type,
  row.evidence_role, row.unit_ids, row.quantity, row.rated_kw_each, null, row.rated_hp_each, row.fuel,
  row.manufacturer_model, row.control_equipment, row.equipment_status, row.source_page, row.extraction_method,
  row.review_status, row.confidence, shortText(row.evidence_text, 260),
]);
const generators = addSheet({
  name: "Generators", tableName: "GeneratorsTable", headers: generatorHeaders, rows: generatorRows,
  widths: [34, 17, 17, 31, 13, 25, 34, 20, 10, 14, 18, 14, 26, 24, 25, 21, 11, 23, 31, 12, 60],
  wrapColumns: [5, 6, 7, 12, 13, 14, 15, 17, 18, 20], dateColumns: [4],
  numberFormats: { 2: "0", 8: "#,##0", 9: "#,##0", 10: "#,##0", 11: "#,##0", 16: "#,##0" }, freezeColumns: 2,
});
if (selectedGenerators.length) {
  generators.sheet.getRange("K2").formulas = [["=IF(OR(I2=\"\",J2=\"\"),\"\",I2*J2)"]];
  generators.sheet.getRange(`K2:K${generators.lastRow}`).fillDown();
}

const permitHeaders = [
  "Record ID", "Facility IDs", "Agency ID", "Document ID", "Permit or Source ID", "Application Number", "Permit Date",
  "Permit Type", "Action", "Subject", "Limit Type", "Equipment Scope", "Pollutant", "Value", "Unit", "Averaging Period",
  "Effective From", "Effective To", "Source Page", "Extraction Method", "Review Status", "Evidence Text", "Notes",
];
const permitRows = data.permits_limits.map((row) => [
  row.record_id, row.facility_ids, row.agency_id, row.document_id, row.permit_or_source_id, row.application_number,
  dateValue(row.permit_date), row.permit_type, row.action, shortText(row.subject, 180), row.limit_type,
  shortText(row.equipment_scope, 220), row.pollutant, row.value, row.unit, row.averaging_period,
  dateValue(row.effective_from), dateValue(row.effective_to), row.source_page, row.extraction_method, row.review_status,
  shortText(row.evidence_text, 260), shortText(row.notes, 260),
]);
const permits = addSheet({
  name: "Permits and Limits", tableName: "PermitsLimitsTable", headers: permitHeaders, rows: permitRows,
  widths: [34, 17, 17, 31, 19, 20, 13, 25, 17, 34, 25, 50, 14, 14, 22, 17, 13, 13, 11, 24, 31, 60, 45],
  wrapColumns: [7, 8, 9, 10, 11, 14, 15, 19, 20, 21, 22], dateColumns: [6, 16, 17], numberFormats: { 2: "0", 13: "#,##0.00", 18: "#,##0" }, freezeColumns: 2,
});

const complianceHeaders = [
  "Compliance ID", "Facility IDs", "Agency ID", "Document ID", "Event Type", "Notice Number", "Event Date", "Pollutant",
  "Equipment Scope", "Allegation or Finding", "Description", "Corrective Action", "Resolution Status", "Penalty Amount",
  "Source Page", "Extraction Method", "Review Status", "Notes",
];
const complianceRows = data.compliance.map((row) => [
  row.compliance_id, row.facility_ids, row.agency_id, row.document_id, row.event_type, row.notice_number,
  dateValue(row.event_date), row.pollutant, row.equipment_scope, row.allegation_or_finding,
  shortText(row.description, 420), shortText(row.corrective_action, 320), row.resolution_status, row.penalty_amount,
  row.source_page, row.extraction_method, row.review_status, shortText(row.notes, 260),
]);
const compliance = addSheet({
  name: "Compliance", tableName: "ComplianceTable", headers: complianceHeaders, rows: complianceRows,
  widths: [17, 17, 17, 31, 33, 18, 13, 13, 18, 21, 65, 55, 34, 16, 11, 23, 20, 48],
  wrapColumns: [4, 9, 10, 11, 12, 15, 16, 17], dateColumns: [6], numberFormats: { 2: "0", 13: '"$"#,##0', 14: "#,##0" }, freezeColumns: 2,
});

documents.sheet.getRange(`Q2:Q${documents.lastRow}`).conditionalFormats.add("containsText", { text: "Confirmed mismatch", format: { fill: "#FECACA", font: { color: "#991B1B", bold: true } } });
documents.sheet.getRange(`Q2:Q${documents.lastRow}`).conditionalFormats.add("containsText", { text: "Possible mismatch", format: { fill: "#FEF3C7", font: { color: "#92400E" } } });
generators.sheet.getRange(`G2:G${generators.lastRow}`).conditionalFormats.add("containsText", { text: "Latest operating", format: { fill: "#D1FAE5", font: { color: "#065F46" } } });
generators.sheet.getRange(`S2:S${generators.lastRow}`).conditionalFormats.add("containsText", { text: "review recommended", format: { fill: "#FEF3C7", font: { color: "#92400E" } } });
permits.sheet.getRange(`U2:U${permits.lastRow}`).conditionalFormats.add("containsText", { text: "review recommended", format: { fill: "#FEF3C7", font: { color: "#92400E" } } });

generators.sheet.getRange(`S2:S${generators.lastRow}`).dataValidation = { rule: { type: "list", values: ["OCR extracted - review recommended", "Reviewed", "Rejected"] } };
permits.sheet.getRange(`U2:U${permits.lastRow}`).dataValidation = { rule: { type: "list", values: ["OCR extracted - review recommended", "Reviewed", "Rejected"] } };
documents.sheet.getRange(`Q2:Q${documents.lastRow}`).dataValidation = { rule: { type: "list", values: ["Consistent", "Unreviewed", "Possible mismatch", "Confirmed mismatch"] } };

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["Facilities", "Documents", "Generators", "Permits and Limits", "Compliance"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.85, format: "png" });
  await fs.writeFile(`${previewDir}/${sheetName.replaceAll(" ", "_")}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const summary = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 9000, tableMaxRows: 5, tableMaxCols: 10, tableMaxCellChars: 90 });
console.log(summary.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan" });
console.log(errors.ndjson);
console.log(JSON.stringify({ outputPath, previewDir, selectedGeneratorRows: selectedGenerators.length }));
