import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/jordan/Code/orcaset/orcaset-oc-bench/paper-lbo/codex-cli/outputs/paper-lbo-case-study";
const outputPath = `${outputDir}/Paper_LBO_Case_Study_Model.xlsx`;
const previewDir = `${outputDir}/previews`;

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const assumptions = workbook.worksheets.add("Assumptions");
const schedules = workbook.worksheets.add("Schedules");
const sensitivity = workbook.worksheets.add("Sensitivity");

for (const sheet of [summary, assumptions, schedules, sensitivity]) {
  sheet.showGridLines = false;
}

const colors = {
  navy: "#17365D",
  blue: "#0000FF",
  green: "#008000",
  black: "#000000",
  white: "#FFFFFF",
  lightBlue: "#D9EAF7",
  lightYellow: "#FFF2CC",
  lightGray: "#F2F2F2",
  border: "#B7C9D6",
  ok: "#E2F0D9",
  error: "#FCE4D6",
};

const moneyFmt = '"$"#,##0.0;[Red]("$"#,##0.0);-';
const moneyWholeFmt = '"$"#,##0;[Red]("$"#,##0);-';
const percentFmt = "0.0%;[Red](0.0%);-";
const multipleFmt = "0.0x;[Red](0.0x);-";
const numberFmt = "#,##0.0;[Red](#,##0.0);-";
const integerFmt = "#,##0;[Red](#,##0);-";
const dateFmt = 'yyyy"E"';

function setTitle(sheet, range, text) {
  sheet.getRange(range).merge();
  sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 14 },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 24;
}

function setSection(sheet, range, text) {
  sheet.getRange(range).merge();
  sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
}

function setHeader(sheet, range) {
  sheet.getRange(range).format = {
    fill: colors.lightBlue,
    font: { bold: true, color: colors.black },
    borders: { preset: "bottom", style: "thin", color: colors.border },
  };
}

function setTotal(sheet, range) {
  sheet.getRange(range).format = {
    font: { bold: true, color: colors.black },
    borders: { top: { style: "thin", color: colors.border } },
  };
}

function styleInputs(sheet, range) {
  sheet.getRange(range).format = {
    fill: colors.lightYellow,
    font: { color: colors.blue },
  };
}

function styleLinked(sheet, range) {
  sheet.getRange(range).format.font = { color: colors.green };
}

function styleFormulas(sheet, range) {
  sheet.getRange(range).format.font = { color: colors.black };
}

function setWidths(sheet, widths) {
  for (const [col, width] of Object.entries(widths)) {
    sheet.getRange(`${col}:${col}`).format.columnWidth = width;
  }
}

// Assumptions
setTitle(assumptions, "A1:D1", "Paper LBO Case Study — Assumptions");
assumptions.getRange("A2:D2").values = [["All values are in $mm unless otherwise noted.", null, null, "Source"]];
assumptions.getRange("A2:D2").format.font = { italic: true, color: "#666666" };

setSection(assumptions, "A4:D4", "Transaction & Financing");
assumptions.getRange("A5:D10").values = [
  ["Close", new Date(2022, 11, 31), "date", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Entry multiple (NTM EBITDA)", 5.0, "x", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Debt / equity — debt", 0.60, "%", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Debt / equity — equity", 0.40, "%", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Interest rate", 0.10, "%", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Transaction fees", 0.0, "$mm", "Assumed no transaction fees per case"],
];

setSection(assumptions, "A12:D12", "Operating Case");
assumptions.getRange("A13:D19").values = [
  ["2023 revenue", 100.0, "$mm", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Annual revenue growth", 0.10, "%", "Paper_LBO_Case_Study_One_Pager.md"],
  ["EBITDA margin", 0.40, "%", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Annual D&A", 20.0, "$mm", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Tax rate", 0.40, "%", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Capex as % of revenue", 0.15, "%", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Increase in operating NWC", 5.0, "$mm p.a.", "Paper_LBO_Case_Study_One_Pager.md"],
];

setSection(assumptions, "A21:D21", "Exit");
assumptions.getRange("A22:D25").values = [
  ["Hold period", 5, "years", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Exit multiple (NTM EBITDA)", 5.0, "x", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Cash sweep", "100% of annual FCF", "text", "Paper_LBO_Case_Study_One_Pager.md"],
  ["Other items", "No fees, cash, or other debt", "text", "Paper_LBO_Case_Study_One_Pager.md"],
];

assumptions.getRange("A5:A10").format.font = { color: colors.black };
assumptions.getRange("A13:A19").format.font = { color: colors.black };
assumptions.getRange("A22:A25").format.font = { color: colors.black };
styleInputs(assumptions, "B5:B10");
styleInputs(assumptions, "B13:B19");
styleInputs(assumptions, "B22:B25");
assumptions.getRange("B5").format.numberFormat = "yyyy-mm-dd";
assumptions.getRange("B6").format.numberFormat = multipleFmt;
assumptions.getRange("B7:B9").format.numberFormat = percentFmt;
assumptions.getRange("B10").format.numberFormat = moneyFmt;
assumptions.getRange("B13").format.numberFormat = moneyFmt;
assumptions.getRange("B14:B15").format.numberFormat = percentFmt;
assumptions.getRange("B16").format.numberFormat = moneyFmt;
assumptions.getRange("B17:B18").format.numberFormat = percentFmt;
assumptions.getRange("B19").format.numberFormat = moneyFmt;
assumptions.getRange("B22").format.numberFormat = integerFmt;
assumptions.getRange("B23").format.numberFormat = multipleFmt;
assumptions.getRange("A5:D10").format.borders = { insideHorizontal: { style: "thin", color: colors.border } };
assumptions.getRange("A13:D19").format.borders = { insideHorizontal: { style: "thin", color: colors.border } };
assumptions.getRange("A22:D25").format.borders = { insideHorizontal: { style: "thin", color: colors.border } };
setWidths(assumptions, { A: 32, B: 30, C: 15, D: 38 });
assumptions.freezePanes.freezeRows(4);

// Schedules
setTitle(schedules, "A1:G1", "Paper LBO Case Study — Schedules");
schedules.getRange("A2:G2").values = [["$mm unless otherwise noted", null, null, null, null, null, "Exit support"]];
schedules.getRange("A2:G2").format.font = { italic: true, color: "#666666" };

setSection(schedules, "A4:B4", "Purchase Price / Sources & Uses");
schedules.getRange("A5:B15").values = [
  ["2023 NTM EBITDA", null],
  ["Entry multiple", null],
  ["Purchase price", null],
  ["Debt %", null],
  ["Debt financing", null],
  ["Equity %", null],
  ["Sponsor equity", null],
  ["Total sources", null],
  ["Total uses", null],
  ["Sources less uses check", null],
  ["", null],
];
schedules.getRange("B5:B14").formulas = [
  ["=B22"],
  ["='Assumptions'!B6"],
  ["=B5*B6"],
  ["='Assumptions'!B7"],
  ["=B7*B8"],
  ["='Assumptions'!B8"],
  ["=B7*B10"],
  ["=SUM(B9,B11)"],
  ["=B7+'Assumptions'!B10"],
  ["=B12-B13"],
];
styleLinked(schedules, "B6:B6");
styleLinked(schedules, "B8:B8");
styleLinked(schedules, "B10:B10");
styleFormulas(schedules, "B5:B5");
schedules.getRange("B5:B5").format.font = { color: colors.black };
schedules.getRange("B7:B7").format.font = { color: colors.black };
schedules.getRange("B9:B9").format.font = { color: colors.black };
schedules.getRange("B11:B14").format.font = { color: colors.black };
schedules.getRange("B5:B5").format.numberFormat = moneyFmt;
schedules.getRange("B6").format.numberFormat = multipleFmt;
schedules.getRange("B7:B7").format.numberFormat = moneyFmt;
schedules.getRange("B8").format.numberFormat = percentFmt;
schedules.getRange("B9").format.numberFormat = moneyFmt;
schedules.getRange("B10").format.numberFormat = percentFmt;
schedules.getRange("B11:B14").format.numberFormat = moneyFmt;
setTotal(schedules, "A13:B14");
schedules.getRange("A15:B15").format.font = { color: colors.black };

setSection(schedules, "A17:G17", "Operating Model & Free Cash Flow");
schedules.getRange("A18:G18").values = [["Fiscal year", new Date(2023, 11, 31), new Date(2024, 11, 31), new Date(2025, 11, 31), new Date(2026, 11, 31), new Date(2027, 11, 31), new Date(2028, 11, 31)]];
setHeader(schedules, "A18:G18");
schedules.getRange("B18:G18").format.numberFormat = dateFmt;
schedules.getRange("A19:G34").values = [
  ["Revenue", null, null, null, null, null, null],
  ["Revenue growth", null, null, null, null, null, null],
  ["EBITDA margin", null, null, null, null, null, null],
  ["EBITDA", null, null, null, null, null, null],
  ["D&A", null, null, null, null, null, null],
  ["EBIT", null, null, null, null, null, null],
  ["Cash interest", null, null, null, null, null, null],
  ["EBT", null, null, null, null, null, null],
  ["Taxes", null, null, null, null, null, null],
  ["Capex", null, null, null, null, null, null],
  ["Increase in operating NWC", null, null, null, null, null, null],
  ["FCF before cash interest", null, null, null, null, null, null],
  ["Free cash flow", null, null, null, null, null, null],
  ["Calculated FCF sweep / paydown", null, null, null, null, null, null],
  ["FCF to sweep check", null, null, null, null, null, null],
  ["", null, null, null, null, null, null],
];
schedules.getRange("B19:G19").formulas = [["='Assumptions'!B13", "=B19*(1+'Assumptions'!B14)", "=C19*(1+'Assumptions'!B14)", "=D19*(1+'Assumptions'!B14)", "=E19*(1+'Assumptions'!B14)", "=F19*(1+'Assumptions'!B14)"]];
schedules.getRange("B20:G20").formulas = [["=B19/'Assumptions'!B13-1", "=C19/B19-1", "=D19/C19-1", "=E19/D19-1", "=F19/E19-1", "=G19/F19-1"]];
schedules.getRange("B21:G21").formulas = [["='Assumptions'!B15", "='Assumptions'!B15", "='Assumptions'!B15", "='Assumptions'!B15", "='Assumptions'!B15", "='Assumptions'!B15"]];
schedules.getRange("B22:G22").formulas = [["=B19*B21", "=C19*C21", "=D19*D21", "=E19*E21", "=F19*F21", "=G19*G21"]];
schedules.getRange("B23:G23").formulas = [["=-'Assumptions'!B16", "=-'Assumptions'!B16", "=-'Assumptions'!B16", "=-'Assumptions'!B16", "=-'Assumptions'!B16", "=-'Assumptions'!B16"]];
schedules.getRange("B24:G24").formulas = [["=SUM(B22:B23)", "=SUM(C22:C23)", "=SUM(D22:D23)", "=SUM(E22:E23)", "=SUM(F22:F23)", "=SUM(G22:G23)"]];
schedules.getRange("B25:F25").formulas = [["=-'Assumptions'!B9*B44", "=-'Assumptions'!B9*C44", "=-'Assumptions'!B9*D44", "=-'Assumptions'!B9*E44", "=-'Assumptions'!B9*F44"]];
schedules.getRange("G25").formulas = [["=0"]];
schedules.getRange("B26:G26").formulas = [["=SUM(B24:B25)", "=SUM(C24:C25)", "=SUM(D24:D25)", "=SUM(E24:E25)", "=SUM(F24:F25)", "=SUM(G24:G25)"]];
schedules.getRange("B27:F27").formulas = [["=-MAX(0,B26*'Assumptions'!B17)", "=-MAX(0,C26*'Assumptions'!B17)", "=-MAX(0,D26*'Assumptions'!B17)", "=-MAX(0,E26*'Assumptions'!B17)", "=-MAX(0,F26*'Assumptions'!B17)"]];
schedules.getRange("G27").formulas = [["=0"]];
schedules.getRange("B28:G28").formulas = [["=-B19*'Assumptions'!B18", "=-C19*'Assumptions'!B18", "=-D19*'Assumptions'!B18", "=-E19*'Assumptions'!B18", "=-F19*'Assumptions'!B18", "=-G19*'Assumptions'!B18"]];
schedules.getRange("B29:G29").formulas = [["=-'Assumptions'!B19", "=-'Assumptions'!B19", "=-'Assumptions'!B19", "=-'Assumptions'!B19", "=-'Assumptions'!B19", "=-'Assumptions'!B19"]];
schedules.getRange("B30:F30").formulas = [["=B22-MAX(0,B24*'Assumptions'!B17)+B28+B29", "=C22-MAX(0,C24*'Assumptions'!B17)+C28+C29", "=D22-MAX(0,D24*'Assumptions'!B17)+D28+D29", "=E22-MAX(0,E24*'Assumptions'!B17)+E28+E29", "=F22-MAX(0,F24*'Assumptions'!B17)+F28+F29"]];
schedules.getRange("G30").formulas = [["=0"]];
schedules.getRange("B31:F31").formulas = [["=B22+B25+B27+B28+B29", "=C22+C25+C27+C28+C29", "=D22+D25+D27+D28+D29", "=E22+E25+E27+E28+E29", "=F22+F25+F27+F28+F29"]];
schedules.getRange("G31").formulas = [["=0"]];
schedules.getRange("B32:F32").formulas = [["=MIN(B39,MAX(0,(B30-(1-'Assumptions'!B17)*'Assumptions'!B9*B39)/(1-(1-'Assumptions'!B17)*'Assumptions'!B9/2)))", "=MIN(C39,MAX(0,(C30-(1-'Assumptions'!B17)*'Assumptions'!B9*C39)/(1-(1-'Assumptions'!B17)*'Assumptions'!B9/2)))", "=MIN(D39,MAX(0,(D30-(1-'Assumptions'!B17)*'Assumptions'!B9*D39)/(1-(1-'Assumptions'!B17)*'Assumptions'!B9/2)))", "=MIN(E39,MAX(0,(E30-(1-'Assumptions'!B17)*'Assumptions'!B9*E39)/(1-(1-'Assumptions'!B17)*'Assumptions'!B9/2)))", "=MIN(F39,MAX(0,(F30-(1-'Assumptions'!B17)*'Assumptions'!B9*F39)/(1-(1-'Assumptions'!B17)*'Assumptions'!B9/2)))"]];
schedules.getRange("G32").formulas = [["=0"]];
schedules.getRange("B33:F33").formulas = [["=B31-B32", "=C31-C32", "=D31-D32", "=E31-E32", "=F31-F32"]];
schedules.getRange("G33").formulas = [["=0"]];
schedules.getRange("B34:G34").clear({ applyTo: "contents" });
schedules.getRange("A31:G34").format.borders = { top: { style: "thin", color: colors.border } };
setTotal(schedules, "A22:G22");
setTotal(schedules, "A31:G33");
styleLinked(schedules, "B19:B19");
styleLinked(schedules, "B21:G21");
styleLinked(schedules, "B23:G23");
styleLinked(schedules, "B25:F25");
styleLinked(schedules, "B27:F27");
styleLinked(schedules, "B28:G29");
styleLinked(schedules, "B32:F32");
schedules.getRange("B19:G19").format.numberFormat = moneyFmt;
schedules.getRange("B20:G21").format.numberFormat = percentFmt;
schedules.getRange("B22:G34").format.numberFormat = moneyFmt;

setSection(schedules, "A37:G37", "Debt Schedule");
schedules.getRange("A38:G44").values = [
  ["Fiscal year", new Date(2023, 11, 31), new Date(2024, 11, 31), new Date(2025, 11, 31), new Date(2026, 11, 31), new Date(2027, 11, 31), new Date(2028, 11, 31)],
  ["Beginning debt", null, null, null, null, null, null],
  ["Debt paydown", null, null, null, null, null, null],
  ["Ending debt", null, null, null, null, null, null],
  ["Paydown / FCF sweep check", null, null, null, null, null, null],
  ["", null, null, null, null, null, null],
  ["Average debt balance", null, null, null, null, null, null],
];
setHeader(schedules, "A38:G38");
schedules.getRange("B38:G38").format.numberFormat = dateFmt;
schedules.getRange("B39:F39").formulas = [["=B9", "=B41", "=C41", "=D41", "=E41"]];
schedules.getRange("G39").formulas = [["=0"]];
schedules.getRange("B40:F40").formulas = [["=-B32", "=-C32", "=-D32", "=-E32", "=-F32"]];
schedules.getRange("G40").formulas = [["=0"]];
schedules.getRange("B41:G41").formulas = [["=SUM(B39:B40)", "=SUM(C39:C40)", "=SUM(D39:D40)", "=SUM(E39:E40)", "=SUM(F39:F40)", "=0"]];
schedules.getRange("B42:F42").formulas = [["=-B40-B32", "=-C40-C32", "=-D40-D32", "=-E40-E32", "=-F40-F32"]];
schedules.getRange("G42").formulas = [["=0"]];
schedules.getRange("B44:F44").formulas = [["=AVERAGE(B39,B41)", "=AVERAGE(C39,C41)", "=AVERAGE(D39,D41)", "=AVERAGE(E39,E41)", "=AVERAGE(F39,F41)"]];
schedules.getRange("G44").formulas = [["=0"]];
setTotal(schedules, "A41:G41");
schedules.getRange("B39:G44").format.numberFormat = moneyFmt;
styleFormulas(schedules, "B39:G44");

setSection(schedules, "A47:B47", "Exit / Returns");
schedules.getRange("A48:B59").values = [
  ["Exit year", null],
  ["Exit NTM EBITDA", null],
  ["Exit multiple", null],
  ["Exit enterprise value", null],
  ["Less: ending debt", null],
  ["Exit equity value", null],
  ["Sponsor entry equity", null],
  ["MoM", null],
  ["IRR", null],
  ["", null],
  ["Sponsor cash flows", null],
  ["Cash flow dates", null],
];
schedules.getRange("B48:B56").formulas = [
  ["=F38"],
  ["=G22"],
  ["='Assumptions'!B23"],
  ["=B49*B50"],
  ["=-F41"],
  ["=SUM(B51:B52)"],
  ["=-B11"],
  ["=B53/-B54"],
  ["=IRR(B58:G58)"],
];
schedules.getRange("B58:G58").formulas = [["=B54", "=0", "=0", "=0", "=0", "=B53"]];
schedules.getRange("B59:G59").values = [[new Date(2022, 11, 31), new Date(2023, 11, 31), new Date(2024, 11, 31), new Date(2025, 11, 31), new Date(2026, 11, 31), new Date(2027, 11, 31)]];
setTotal(schedules, "A53:B53");
setTotal(schedules, "A55:B56");
schedules.getRange("B48").format.numberFormat = dateFmt;
schedules.getRange("B49:B49").format.numberFormat = moneyFmt;
schedules.getRange("B50").format.numberFormat = multipleFmt;
schedules.getRange("B51:B54").format.numberFormat = moneyFmt;
schedules.getRange("B55").format.numberFormat = multipleFmt;
schedules.getRange("B56").format.numberFormat = percentFmt;
schedules.getRange("B58:G58").format.numberFormat = moneyFmt;
schedules.getRange("B59:G59").format.numberFormat = "yyyy-mm-dd";
styleLinked(schedules, "B50");
styleFormulas(schedules, "B48:B56");

setWidths(schedules, { A: 32, B: 15, C: 15, D: 15, E: 15, F: 15, G: 15 });
schedules.freezePanes.freezeRows(18);
schedules.freezePanes.freezeColumns(1);

// Summary
setTitle(summary, "A1:E1", "Paper LBO Case Study — Summary");
summary.getRange("A2:E2").values = [["Five-year LBO return model | $mm unless otherwise noted", null, null, null, null]];
summary.getRange("A2:E2").format.font = { italic: true, color: "#666666" };

setSection(summary, "A4:B4", "Key Outputs");
summary.getRange("A5:B11").values = [
  ["Entry purchase price", null],
  ["Sponsor equity", null],
  ["Exit enterprise value", null],
  ["Exit equity value", null],
  ["Ending debt", null],
  ["MoM", null],
  ["IRR", null],
];
summary.getRange("B5:B11").formulas = [["='Schedules'!B7"], ["='Schedules'!B11"], ["='Schedules'!B51"], ["='Schedules'!B53"], ["='Schedules'!F41"], ["='Schedules'!B55"], ["='Schedules'!B56"]];
styleLinked(summary, "B5:B11");
summary.getRange("B5:B9").format.numberFormat = moneyFmt;
summary.getRange("B10").format.numberFormat = multipleFmt;
summary.getRange("B11").format.numberFormat = percentFmt;
setTotal(summary, "A8:B8");
setTotal(summary, "A10:B11");

setSection(summary, "D4:E4", "Model Status");
summary.getRange("D5:E7").values = [["Model status", null], ["Base exit multiple", null], ["Hold period", null]];
summary.getRange("E5:E7").formulas = [["=E28"], ["='Assumptions'!B23"], ["='Assumptions'!B22"]];
styleLinked(summary, "E6:E7");
summary.getRange("E6").format.numberFormat = multipleFmt;
summary.getRange("E7").format.numberFormat = integerFmt;
summary.getRange("E5").format.font = { bold: true, color: colors.black };

setSection(summary, "A14:E14", "Sources & Uses");
summary.getRange("A15:B19").values = [
  ["Sources", "Amount"],
  ["Debt financing", null],
  ["Sponsor equity", null],
  ["Total sources", null],
  ["Sources less uses check", null],
];
summary.getRange("D15:E19").values = [
  ["Uses", "Amount"],
  ["Purchase price", null],
  ["Transaction fees", null],
  ["Total uses", null],
  ["Uses less sources check", null],
];
setHeader(summary, "A15:B15");
setHeader(summary, "D15:E15");
summary.getRange("B16:B19").formulas = [["='Schedules'!B9"], ["='Schedules'!B11"], ["='Schedules'!B12"], ["='Schedules'!B14"]];
summary.getRange("E16:E19").formulas = [["='Schedules'!B7"], ["='Assumptions'!B10"], ["='Schedules'!B13"], ["=E18-B18"]];
styleLinked(summary, "B16:B19");
styleLinked(summary, "E16:E18");
styleFormulas(summary, "E19");
summary.getRange("B16:B19").format.numberFormat = moneyFmt;
summary.getRange("E16:E19").format.numberFormat = moneyFmt;
setTotal(summary, "A18:B19");
setTotal(summary, "D18:E19");

setSection(summary, "A22:E22", "Checks");
summary.getRange("A23:E27").values = [
  ["Check", "Actual", "Expected", "Difference", "Status"],
  ["Sources equal uses", null, null, null, null],
  ["Debt roll-forward", null, null, null, null],
  ["Annual FCF sweep", null, null, null, null],
  ["Exit equity bridge", null, null, null, null],
];
setHeader(summary, "A23:E23");
summary.getRange("B24:E27").formulas = [
  ["='Schedules'!B12", "='Schedules'!B13", "=B24-C24", '=IF(ABS(D24)<0.01,"OK","ERROR")'],
  ["='Schedules'!F41", "='Schedules'!F39+'Schedules'!F40", "=B25-C25", '=IF(ABS(D25)<0.01,"OK","ERROR")'],
  ["='Schedules'!F31", "='Schedules'!F32", "=B26-C26", '=IF(ABS(D26)<0.01,"OK","ERROR")'],
  ["='Schedules'!B53", "='Schedules'!B51+'Schedules'!B52", "=B27-C27", '=IF(ABS(D27)<0.01,"OK","ERROR")'],
];
summary.getRange("A28:E28").values = [["Model status", null, null, null, null]];
summary.getRange("E28").formulas = [['=IF(AND(E24="OK",E25="OK",E26="OK",E27="OK"),"OK","ERROR")']];
summary.getRange("B24:D27").format.numberFormat = moneyFmt;
summary.getRange("E24:E28").format.font = { bold: true, color: colors.black };
summary.getRange("E24:E28").conditionalFormats.add("cellIs", { operator: "equal", formula: '"OK"', format: { fill: colors.ok, font: { color: "#006100", bold: true } } });
summary.getRange("E24:E28").conditionalFormats.add("cellIs", { operator: "equal", formula: '"ERROR"', format: { fill: colors.error, font: { color: "#9C0006", bold: true } } });
setTotal(summary, "A28:E28");

summary.getRange("A31:E34").values = [
  ["Model conventions", null, null, null, null],
  ["Close", "12/31/2022", null, "Forecast", "2023E–2027E"],
  ["Exit valuation", "5.0x NTM EBITDA", null, "Cash sweep", "100% of annual FCF"],
  ["Interest", "10.0% of average debt", null, "Fees / cash", "None"],
];
summary.getRange("A31:E31").merge();
summary.getRange("A31:E31").format = { fill: colors.lightGray, font: { bold: true, color: colors.black } };
summary.getRange("A32:E34").format.borders = { insideHorizontal: { style: "thin", color: colors.border } };
setWidths(summary, { A: 28, B: 16, C: 16, D: 26, E: 18 });
summary.freezePanes.freezeRows(4);

// Sensitivity
setTitle(sensitivity, "A1:F1", "Paper LBO Case Study — IRR Sensitivity");
sensitivity.getRange("A2:F2").values = [["Rows: exit multiple | Columns: annual revenue growth | $mm unless otherwise noted", null, null, null, null, null]];
sensitivity.getRange("A2:F2").format.font = { italic: true, color: "#666666" };
setSection(sensitivity, "A4:F4", "IRR Sensitivity: Exit Multiple vs. Annual Revenue Growth");
sensitivity.getRange("A5:F10").values = [
  ["Exit multiple / Revenue growth", 0.06, 0.08, 0.10, 0.12, 0.14],
  [3.0, null, null, null, null, null],
  [4.0, null, null, null, null, null],
  [5.0, null, null, null, null, null],
  [6.0, null, null, null, null, null],
  [7.0, null, null, null, null, null],
];
setHeader(sensitivity, "A5:F5");
styleInputs(sensitivity, "B5:F5");
styleInputs(sensitivity, "A6:A10");
sensitivity.getRange("B5:F5").format.numberFormat = percentFmt;
sensitivity.getRange("A6:A10").format.numberFormat = multipleFmt;

setSection(sensitivity, "A13:F13", "Scenario Debt Paydown & Exit EBITDA");
sensitivity.getRange("A14:F47").values = [
  ["Annual revenue growth", null, null, null, null, null],
  ["2023 revenue", null, null, null, null, null],
  ["2024 revenue", null, null, null, null, null],
  ["2025 revenue", null, null, null, null, null],
  ["2026 revenue", null, null, null, null, null],
  ["2027 revenue", null, null, null, null, null],
  ["2028 revenue", null, null, null, null, null],
  ["2023 EBITDA", null, null, null, null, null],
  ["2024 EBITDA", null, null, null, null, null],
  ["2025 EBITDA", null, null, null, null, null],
  ["2026 EBITDA", null, null, null, null, null],
  ["2027 EBITDA", null, null, null, null, null],
  ["2028 EBITDA", null, null, null, null, null],
  ["Beginning debt 2023", null, null, null, null, null],
  ["FCF before interest 2023", null, null, null, null, null],
  ["Paydown 2023", null, null, null, null, null],
  ["Ending debt 2023", null, null, null, null, null],
  ["Beginning debt 2024", null, null, null, null, null],
  ["FCF before interest 2024", null, null, null, null, null],
  ["Paydown 2024", null, null, null, null, null],
  ["Ending debt 2024", null, null, null, null, null],
  ["Beginning debt 2025", null, null, null, null, null],
  ["FCF before interest 2025", null, null, null, null, null],
  ["Paydown 2025", null, null, null, null, null],
  ["Ending debt 2025", null, null, null, null, null],
  ["Beginning debt 2026", null, null, null, null, null],
  ["FCF before interest 2026", null, null, null, null, null],
  ["Paydown 2026", null, null, null, null, null],
  ["Ending debt 2026", null, null, null, null, null],
  ["Beginning debt 2027", null, null, null, null, null],
  ["FCF before interest 2027", null, null, null, null, null],
  ["Paydown 2027", null, null, null, null, null],
  ["Ending debt 2027", null, null, null, null, null],
  ["", null, null, null, null, null],
];
setHeader(sensitivity, "A14:F14");
sensitivity.getRange("B14:F14").formulas = [["=B5", "=C5", "=D5", "=E5", "=F5"]];
sensitivity.getRange("B14:F14").format.numberFormat = percentFmt;
sensitivity.getRange("B15:F15").formulas = [["='Assumptions'!B13", "='Assumptions'!B13", "='Assumptions'!B13", "='Assumptions'!B13", "='Assumptions'!B13"]];
sensitivity.getRange("B16:F16").formulas = [["=B15*(1+B$14)", "=C15*(1+C$14)", "=D15*(1+D$14)", "=E15*(1+E$14)", "=F15*(1+F$14)"]];
sensitivity.getRange("B17:F17").formulas = [["=B16*(1+B$14)", "=C16*(1+C$14)", "=D16*(1+D$14)", "=E16*(1+E$14)", "=F16*(1+F$14)"]];
sensitivity.getRange("B18:F18").formulas = [["=B17*(1+B$14)", "=C17*(1+C$14)", "=D17*(1+D$14)", "=E17*(1+E$14)", "=F17*(1+F$14)"]];
sensitivity.getRange("B19:F19").formulas = [["=B18*(1+B$14)", "=C18*(1+C$14)", "=D18*(1+D$14)", "=E18*(1+E$14)", "=F18*(1+F$14)"]];
sensitivity.getRange("B20:F20").formulas = [["=B19*(1+B$14)", "=C19*(1+C$14)", "=D19*(1+D$14)", "=E19*(1+E$14)", "=F19*(1+F$14)"]];
for (const [row, revRow, ebitdaRow] of [[21,15,21],[22,16,22],[23,17,23],[24,18,24],[25,19,25],[26,20,26]]) {
  sensitivity.getRange(`B${row}:F${row}`).formulas = [[
    `=B${revRow}*'Assumptions'!$B$15`, `=C${revRow}*'Assumptions'!$B$15`, `=D${revRow}*'Assumptions'!$B$15`, `=E${revRow}*'Assumptions'!$B$15`, `=F${revRow}*'Assumptions'!$B$15`,
  ]];
}
sensitivity.getRange("B27:F27").formulas = [["='Schedules'!B9", "='Schedules'!B9", "='Schedules'!B9", "='Schedules'!B9", "='Schedules'!B9"]];
const solverRows = [28, 32, 36, 40, 44];
const beginRows = [27, 31, 35, 39, 43];
const ebitdaRows = [21, 22, 23, 24, 25];
const revenueRows = [15, 16, 17, 18, 19];
for (let i = 0; i < 5; i += 1) {
  const row = solverRows[i];
  const begin = beginRows[i];
  const ebitda = ebitdaRows[i];
  const revenue = revenueRows[i];
  sensitivity.getRange(`B${row}:F${row}`).formulas = [[
    `=${String.fromCharCode(66)}${ebitda}-MAX(0,(${String.fromCharCode(66)}${ebitda}-'Assumptions'!$B$16)*'Assumptions'!$B$17)-${String.fromCharCode(66)}${revenue}*'Assumptions'!$B$18-'Assumptions'!$B$19`,
    `=${String.fromCharCode(67)}${ebitda}-MAX(0,(${String.fromCharCode(67)}${ebitda}-'Assumptions'!$B$16)*'Assumptions'!$B$17)-${String.fromCharCode(67)}${revenue}*'Assumptions'!$B$18-'Assumptions'!$B$19`,
    `=${String.fromCharCode(68)}${ebitda}-MAX(0,(${String.fromCharCode(68)}${ebitda}-'Assumptions'!$B$16)*'Assumptions'!$B$17)-${String.fromCharCode(68)}${revenue}*'Assumptions'!$B$18-'Assumptions'!$B$19`,
    `=${String.fromCharCode(69)}${ebitda}-MAX(0,(${String.fromCharCode(69)}${ebitda}-'Assumptions'!$B$16)*'Assumptions'!$B$17)-${String.fromCharCode(69)}${revenue}*'Assumptions'!$B$18-'Assumptions'!$B$19`,
    `=${String.fromCharCode(70)}${ebitda}-MAX(0,(${String.fromCharCode(70)}${ebitda}-'Assumptions'!$B$16)*'Assumptions'!$B$17)-${String.fromCharCode(70)}${revenue}*'Assumptions'!$B$18-'Assumptions'!$B$19`,
  ]];
  const paydownRow = row + 1;
  const endingRow = row + 2;
  sensitivity.getRange(`B${paydownRow}:F${paydownRow}`).formulas = [[
    `=MIN(B${begin},MAX(0,(B${row}-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9*B${begin})/(1-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9/2)))`,
    `=MIN(C${begin},MAX(0,(C${row}-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9*C${begin})/(1-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9/2)))`,
    `=MIN(D${begin},MAX(0,(D${row}-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9*D${begin})/(1-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9/2)))`,
    `=MIN(E${begin},MAX(0,(E${row}-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9*E${begin})/(1-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9/2)))`,
    `=MIN(F${begin},MAX(0,(F${row}-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9*F${begin})/(1-(1-'Assumptions'!$B$17)*'Assumptions'!$B$9/2)))`,
  ]];
  sensitivity.getRange(`B${endingRow}:F${endingRow}`).formulas = [[`=B${begin}-B${paydownRow}`, `=C${begin}-C${paydownRow}`, `=D${begin}-D${paydownRow}`, `=E${begin}-E${paydownRow}`, `=F${begin}-F${paydownRow}`]];
  if (i < 4) {
    const nextBeginRow = endingRow + 1;
    sensitivity.getRange(`B${nextBeginRow}:F${nextBeginRow}`).formulas = [[`=B${endingRow}`, `=C${endingRow}`, `=D${endingRow}`, `=E${endingRow}`, `=F${endingRow}`]];
  }
}

// The 2023–2027 scenario block ends at row 46; reset labels for clean structure.
sensitivity.getRange("A27:A47").values = [
  ["Beginning debt 2023"], ["FCF before interest 2023"], ["Paydown 2023"], ["Ending debt 2023"], ["Beginning debt 2024"], ["FCF before interest 2024"], ["Paydown 2024"], ["Ending debt 2024"], ["Beginning debt 2025"], ["FCF before interest 2025"], ["Paydown 2025"], ["Ending debt 2025"], ["Beginning debt 2026"], ["FCF before interest 2026"], ["Paydown 2026"], ["Ending debt 2026"], ["Beginning debt 2027"], ["FCF before interest 2027"], ["Paydown 2027"], ["Ending debt 2027"], [""]
];

sensitivity.getRange("B6:F10").formulas = [
  ["=((B$26*$A6-B$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((C$26*$A6-C$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((D$26*$A6-D$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((E$26*$A6-E$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((F$26*$A6-F$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1"],
  ["=((B$26*$A7-B$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((C$26*$A7-C$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((D$26*$A7-D$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((E$26*$A7-E$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((F$26*$A7-F$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1"],
  ["=((B$26*$A8-B$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((C$26*$A8-C$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((D$26*$A8-D$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((E$26*$A8-E$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((F$26*$A8-F$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1"],
  ["=((B$26*$A9-B$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((C$26*$A9-C$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((D$26*$A9-D$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((E$26*$A9-E$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((F$26*$A9-F$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1"],
  ["=((B$26*$A10-B$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((C$26*$A10-C$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((D$26*$A10-D$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((E$26*$A10-E$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1", "=((F$26*$A10-F$46)/'Schedules'!$B$11)^(1/'Assumptions'!$B$22)-1"],
];
sensitivity.getRange("B6:F10").format.numberFormat = percentFmt;
sensitivity.getRange("B15:F47").format.numberFormat = moneyFmt;
styleLinked(sensitivity, "B15:F15");
styleLinked(sensitivity, "B27:F27");
sensitivity.getRange("B6:F10").conditionalFormats.add("colorScale", { colors: ["#F4CCCC", "#FFF2CC", "#D9EAD3"] });
setTotal(sensitivity, "A8:F8");
setTotal(sensitivity, "A31:F31");
setTotal(sensitivity, "A35:F35");
setTotal(sensitivity, "A39:F39");
setTotal(sensitivity, "A43:F43");
setTotal(sensitivity, "A47:F47");
setWidths(sensitivity, { A: 32, B: 14, C: 14, D: 14, E: 14, F: 14 });
sensitivity.freezePanes.freezeRows(5);
sensitivity.freezePanes.freezeColumns(1);

// Compact notes / units
summary.getRange("A36:E36").merge();
summary.getRange("A36").values = [["Source: Paper_LBO_Case_Study_One_Pager.md (user-provided case assumptions)."]];
summary.getRange("A36:E36").format = { font: { italic: true, color: "#666666", size: 9 } };

// Render previews for visual QA.
for (const [sheetName, range] of [["Summary", "A1:E36"], ["Assumptions", "A1:D25"], ["Schedules", "A1:G59"], ["Sensitivity", "A1:F47"]]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${previewDir}/${sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const inspection = await workbook.inspect({
  kind: "table",
  range: "Summary!A1:E36",
  include: "values,formulas",
  tableMaxRows: 36,
  tableMaxCols: 5,
  maxChars: 12000,
});
console.log(inspection.ndjson);

const keySchedules = await workbook.inspect({
  kind: "table",
  range: "Schedules!A30:G33",
  include: "values,formulas",
  tableMaxRows: 4,
  tableMaxCols: 7,
  maxChars: 7000,
});
console.log(keySchedules.ndjson);

const keyReturns = await workbook.inspect({
  kind: "table",
  range: "Schedules!A48:B56",
  include: "values,formulas",
  tableMaxRows: 9,
  tableMaxCols: 2,
  maxChars: 5000,
});
console.log(keyReturns.ndjson);

const sensitivityCheck = await workbook.inspect({
  kind: "table",
  range: "Sensitivity!A5:F10",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 6,
  maxChars: 7000,
});
console.log(sensitivityCheck.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);
console.log(`EXPORTED ${outputPath}`);
