#!/usr/bin/env node
import fs from "node:fs/promises";
import { pathToFileURL } from "node:url";

const artifactTool = process.env.ATLAS_ARTIFACT_TOOL_MODULE
  ? await import(pathToFileURL(process.env.ATLAS_ARTIFACT_TOOL_MODULE).href)
  : await import("@oai/artifact-tool");
const { FileBlob, SpreadsheetFile, Workbook } = artifactTool;

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) throw new Error("usage: export_full_qa_xlsx.mjs report.json output.xlsx");
const report = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const font = "Arial";
const maxWidth = 42;

function serial(value) {
  if (value === null || value === undefined) return null;
  const rendered = typeof value === "object" ? JSON.stringify(value) : value;
  return typeof rendered === "string" && rendered.length > 1000 ? `${rendered.slice(0, 997)}...` : rendered;
}

function columnName(index) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

for (const [sheetName, rows] of Object.entries(report.sheets)) {
  const sheet = workbook.worksheets.add(sheetName);
  sheet.showGridLines = false;
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const effectiveColumns = columns.length ? columns : ["Status"];
  const matrix = [effectiveColumns, ...(rows.length ? rows.map(row => effectiveColumns.map(key => serial(row[key]))) : [["No records"]])];
  const range = sheet.getRangeByIndexes(0, 0, matrix.length, effectiveColumns.length);
  range.values = matrix;
  range.format.font = { name: font, size: 10, color: "#172033" };
  const header = sheet.getRangeByIndexes(0, 0, 1, effectiveColumns.length);
  header.format = { fill: "#19324D", font: { name: font, bold: true, color: "#FFFFFF" },
    verticalAlignment: "center", horizontalAlignment: "center", wrapText: true,
    borders: { preset: "inside", style: "thin", color: "#FFFFFF" } };
  header.format.rowHeight = 32;
  range.format.autofitColumns();
  range.format.autofitRows();
  for (let col = 0; col < effectiveColumns.length; col++) {
    const columnRange = sheet.getRangeByIndexes(0, col, matrix.length, 1);
    if (columnRange.format.columnWidth > maxWidth) columnRange.format.columnWidth = maxWidth;
    if (effectiveColumns[col].includes("margin_pct")) {
      if (matrix.length > 1) sheet.getRangeByIndexes(1, col, matrix.length - 1, 1).format.numberFormat = "0.0";
    } else if (effectiveColumns[col].endsWith("_pct") || ["wacc", "terminal_growth"].includes(effectiveColumns[col])) {
      if (matrix.length > 1) sheet.getRangeByIndexes(1, col, matrix.length - 1, 1).format.numberFormat = "0.0%";
    } else if (effectiveColumns[col].includes("timestamp") || effectiveColumns[col].endsWith("_date") || effectiveColumns[col].endsWith("_as_of")) {
      if (matrix.length > 1) sheet.getRangeByIndexes(1, col, matrix.length - 1, 1).format.numberFormat = "yyyy-mm-dd hh:mm";
    } else if (["current_price", "completed_close", "base_fv", "fair_value_low", "fair_value_high", "bear_case", "bull_case", "street_target", "street_target_low", "street_target_high", "entry_low", "entry_high", "stop", "technical_target", "sma50", "sma200", "support", "resistance", "value", "model_value", "calculated_per_share"].includes(effectiveColumns[col])) {
      if (matrix.length > 1) sheet.getRangeByIndexes(1, col, matrix.length - 1, 1).format.numberFormat = "$#,##0.00";
    } else if (["market_cap", "provider_market_cap", "calculated_market_cap", "revenue", "eps", "ebit", "ebitda", "ocf", "capex", "capex_raw", "capex_normalized", "fcf", "calculated_fcf", "provider_fcf", "cash", "debt", "net_debt", "equity", "assets", "shares", "enterprise_value", "equity_value"].includes(effectiveColumns[col])) {
      if (matrix.length > 1) sheet.getRangeByIndexes(1, col, matrix.length - 1, 1).format.numberFormat = "#,##0";
    }
  }
  if (matrix.length > 1) sheet.getRangeByIndexes(1, 0, matrix.length - 1, effectiveColumns.length).format.wrapText = true;
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(Math.min(2, effectiveColumns.length));
  if (rows.length) sheet.tables.add(sheet.getRangeByIndexes(0, 0, matrix.length, effectiveColumns.length).address, true, `${sheetName.replace(/[^A-Za-z0-9]/g, "")}Table`);
}

await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 4000, tableMaxRows: 2, tableMaxCols: 4 });
await fs.mkdir(outputPath.substring(0, outputPath.lastIndexOf("/")) || ".", { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const saved = await FileBlob.load(outputPath);
const verified = await SpreadsheetFile.importXlsx(saved);
const errors = await verified.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, maxChars: 8000 });
if (String(errors.ndjson || "").match(/#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/)) throw new Error("Workbook formula error detected");
if (process.env.ATLAS_QA_RENDER_DIR) {
  await fs.mkdir(process.env.ATLAS_QA_RENDER_DIR, { recursive: true });
  for (const [sheetName, rows] of Object.entries(report.sheets)) {
    const columns = [...new Set(rows.flatMap(row => Object.keys(row)))];
    const previewRange = `A1:${columnName(Math.min(Math.max(columns.length, 1), 26) - 1)}${Math.min(rows.length + 1, 50)}`;
    const preview = await verified.render({ sheetName, range: previewRange, scale: 0.8, format: "png" });
    await fs.writeFile(`${process.env.ATLAS_QA_RENDER_DIR}/${sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
  }
}
