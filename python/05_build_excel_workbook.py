"""
05_build_excel_workbook.py  -  Excel analysis workbook
-------------------------------------------------------
Builds excel/Refinery_Analysis.xlsx from the clean model. All summary
numbers are live Excel formulas (SUMIFS, COUNTIFS, SUMPRODUCT, INDEX/MATCH,
RANK, IFERROR), so changing a spec limit or price on the Assumptions sheet
recalculates the whole workbook.

Run:  python python/05_build_excel_workbook.py
"""
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.comments import Comment
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parents[1]
PROC, RAW = ROOT / "data" / "processed", ROOT / "data" / "raw"
OUT = ROOT / "excel" / "Refinery_Analysis.xlsx"
OUT.parent.mkdir(exist_ok=True)

FONT = "Arial"
NAVY = "1F3A5F"
F_TITLE = Font(name=FONT, size=16, bold=True, color=NAVY)
F_SUB = Font(name=FONT, size=10, italic=True, color="52514E")
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_BODY = Font(name=FONT, size=10)
F_BOLD = Font(name=FONT, size=10, bold=True)
F_INPUT = Font(name=FONT, size=10, color="0000FF")
F_LINK = Font(name=FONT, size=10, color="008000")
FILL_HEAD = PatternFill("solid", fgColor=NAVY)
FILL_INPUT = PatternFill("solid", fgColor="FFFF00")
FILL_BAND = PatternFill("solid", fgColor="F2F5F9")
THIN = Side(style="thin", color="C3C2B7")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)

# ---------------------------------------------------------------- data -----
fb = pd.read_csv(PROC / "fact_batch.csv", parse_dates=["production_date"])
sup = pd.read_csv(PROC / "dim_supplier.csv")
dt = pd.read_csv(PROC / "fact_downtime.csv", parse_dates=["event_date"])
dq = pd.read_csv(PROC / "dq_log.csv")
px = pd.read_csv(PROC / "fact_market_price.csv")
raw = pd.read_csv(RAW / "batch_production.csv", dtype=str, keep_default_na=False).head(300)
fb = fb.merge(sup[["supplier_id", "supplier_name"]], on="supplier_id", how="left")
fb["year_month"] = fb.production_date.dt.strftime("%Y-%m")
fb = fb.sort_values(["production_date", "line_code", "shift"]).reset_index(drop=True)
N = len(fb)
LAST = N + 1  # last data row on the Data sheet

wb = Workbook()


def header(ws, row, cols, start_col=1):
    for i, c in enumerate(cols):
        cell = ws.cell(row=row, column=start_col + i, value=c)
        cell.font, cell.fill, cell.border = F_HEAD, FILL_HEAD, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def title(ws, text, sub):
    ws["A1"], ws["A2"] = text, sub
    ws["A1"].font, ws["A2"].font = F_TITLE, F_SUB
    ws.sheet_view.showGridLines = False


def widths(ws, w):
    for i, v in enumerate(w, start=1):
        ws.column_dimensions[get_column_letter(i)].width = v


def style_range(ws, r1, r2, c1, c2, fmt=None, font=F_BODY):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=c)
            cell.font, cell.border = font, BOX
            if fmt:
                cell.number_format = fmt


def finish_chart(ch):
    ch.roundedCorners = False
    if ch.legend is not None:
        ch.legend.overlay = False
    if ch.title is not None:
        ch.title.overlay = False
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    return ch


# ===================================================================== Cover
ws = wb.active
ws.title = "Cover"
title(ws, "Palm Oil Refinery Operations Analysis",
      "Excel analysis layer of the refinery analytics portfolio project. Synthetic data, Jan 2024 - Jun 2025.")
rows = [
    ("Sheet", "What it shows", "Excel skills demonstrated"),
    ("Assumptions", "Product spec limits, prices and targets (editable inputs)", "Input cells, named assumptions, documented sources"),
    ("Raw_Sample", "First 300 rows of the raw shift log, exactly as received", "Data profiling - spot the problems"),
    ("Cleaning_Log", "Every cleaning rule applied in SQL and rows affected", "Data-quality audit trail"),
    ("Data", f"{N:,} clean batches (Excel Table 'tblBatch')", "Structured table, calculated columns (yield, off-spec flag)"),
    ("Monthly_Summary", "Monthly KPI trend with chart", "SUMIFS, COUNTIFS, SUMPRODUCT weighted averages, line chart"),
    ("Supplier_Scorecard", "Mill ranking and value of supplier quality", "RANK, MAX, INDEX/MATCH, colour scales, data bars"),
    ("Line_Shift_Matrix", "Off-spec rate heat map by line and shift", "2-D COUNTIFS matrix, colour scale"),
    ("FFA_Band_Analysis", "Yield by crude FFA band (data mining in Excel)", "Banding with COUNTIFS/SUMIFS ranges, SLOPE, RSQ"),
    ("Downtime_Pareto", "Downtime events and 80/20 Pareto", "SUMIFS, running cumulative %, bar chart"),
    ("Data_Dictionary", "Definition and unit of every column", "Documentation"),
]
for i, r in enumerate(rows):
    for j, v in enumerate(r):
        c = ws.cell(row=4 + i, column=1 + j, value=v)
        c.font, c.border = (F_HEAD if i == 0 else F_BODY), BOX
        if i == 0:
            c.fill = FILL_HEAD
        c.alignment = Alignment(wrap_text=True, vertical="top")
ws["A17"], ws["A17"].font = "Colour legend", F_BOLD
ws["A18"], ws["B18"] = "1.00", "Blue text on yellow = input you can change (Assumptions sheet)"
ws["A18"].font, ws["A18"].fill = F_INPUT, FILL_INPUT
ws["A19"], ws["B19"] = "1.00", "Green text = pulled from another sheet"
ws["A19"].font = F_LINK
ws["A20"], ws["B20"] = "1.00", "Black text = formula or source data"
ws["A20"].font = F_BODY
ws["A22"] = "Tip: try changing the RBDPO FFA spec on the Assumptions sheet from 0.10 to 0.08 and watch every off-spec KPI update."
ws["A22"].font = F_SUB
widths(ws, [22, 58, 52])

# =============================================================== Assumptions
wa = wb.create_sheet("Assumptions")
title(wa, "Assumptions & Inputs", "Change the yellow cells - every summary sheet recalculates.")
header(wa, 4, ["Parameter", "Unit", "Value", "Source / note"])
avg_rbdpo = round(px.rbdpo_price_myr_mt.mean(), 0)
inputs = [
    ("RBDPO FFA spec (max)", "% as oleic", 0.10, "Typical PORAM RBD palm oil spec: FFA 0.1 % max"),
    ("RBDPO colour spec (max)", "Lovibond Red (5.25\" cell)", 3.0, "Typical PORAM RBD palm oil spec: 3 Red max"),
    ("RBDPO moisture & impurities spec (max)", "%", 0.10, "Typical PORAM RBD palm oil spec: 0.1 % max"),
    ("Average RBDPO price", "MYR / tonne", avg_rbdpo, "Mean of fact_market_price (synthetic) - used to value yield gaps"),
    ("Target refining yield", "%", 0.95, "Illustrative internal target"),
    ("Target off-spec rate", "%", 0.05, "Illustrative internal target"),
]
for i, (p, u, v, s) in enumerate(inputs):
    r = 5 + i
    wa.cell(row=r, column=1, value=p).font = F_BODY
    wa.cell(row=r, column=2, value=u).font = F_BODY
    c = wa.cell(row=r, column=3, value=v)
    c.font, c.fill = F_INPUT, FILL_INPUT
    c.number_format = "0.0%" if u == "%" and v < 1 else ("#,##0" if v > 100 else "0.00")
    wa.cell(row=r, column=4, value=s).font = F_SUB
    for col in range(1, 5):
        wa.cell(row=r, column=col).border = BOX
widths(wa, [38, 26, 12, 64])
SPEC_FFA, SPEC_COL, SPEC_MOIST = "Assumptions!$C$5", "Assumptions!$C$6", "Assumptions!$C$7"
PRICE, TGT_Y, TGT_OS = "Assumptions!$C$8", "Assumptions!$C$9", "Assumptions!$C$10"

# ================================================================ Raw_Sample
wr = wb.create_sheet("Raw_Sample")
wr["A1"], wr["A1"].font = "Raw shift log - first 300 rows exactly as exported (note mixed dates, labels, blanks, N/A)", F_BOLD
header(wr, 2, list(raw.columns))
for i, row in enumerate(raw.itertuples(index=False), start=3):
    for j, v in enumerate(row, start=1):
        wr.cell(row=i, column=j, value=v).font = F_BODY
widths(wr, [13, 13, 11, 9, 26] + [12] * 11)
wr.freeze_panes = "A3"

# ============================================================== Cleaning_Log
wc = wb.create_sheet("Cleaning_Log")
title(wc, "Data Cleaning Log", "Generated by sql/02_clean_transform.sql - one row per cleaning rule.")
header(wc, 4, ["Step", "Source table", "Issue found", "Action taken", "Rows affected"])
for i, r in enumerate(dq.itertuples(index=False), start=5):
    for j, v in enumerate([r.step_no, r.source_table, r.rule, r.action, r.rows_affected], start=1):
        c = wc.cell(row=i, column=j, value=v)
        c.font, c.border = F_BODY, BOX
        if j == 5:
            c.number_format = "#,##0"
end = 4 + len(dq)
wc.cell(row=end + 1, column=4, value="Total rule applications").font = F_BOLD
c = wc.cell(row=end + 1, column=5, value=f"=SUM(E5:E{end})")
c.font, c.number_format = F_BOLD, "#,##0"
wc.conditional_formatting.add(f"E5:E{end}", DataBarRule(start_type="min", end_type="max", color="6DA7EC"))
widths(wc, [7, 22, 52, 44, 14])

# ====================================================================== Data
wd = wb.create_sheet("Data")
cols = ["batch_id", "production_date", "year_month", "shift", "line_code", "supplier_name",
        "cpo_input_mt", "cpo_ffa_pct", "cpo_dobi", "bleaching_earth_pct", "deo_temp_c", "deo_vacuum_mbar",
        "rbdpo_output_mt", "pfad_output_mt", "yield_pct", "rbdpo_ffa_pct", "color_red", "rbdpo_moisture_pct",
        "has_lab_result", "is_off_spec", "steam_mt", "electricity_kwh", "dq_flags"]
header(wd, 1, cols)
src = [c for c in cols if c not in ("yield_pct", "is_off_spec")]
fmt = {"production_date": "yyyy-mm-dd", "cpo_input_mt": "#,##0.00", "rbdpo_output_mt": "#,##0.00",
       "pfad_output_mt": "#,##0.00", "yield_pct": "0.00%", "rbdpo_ffa_pct": "0.000", "electricity_kwh": "#,##0"}
col_idx = {c: i + 1 for i, c in enumerate(cols)}
for r, rec in enumerate(fb[src].itertuples(index=False), start=2):
    for c, v in zip(src, rec):
        if pd.isna(v):
            v = None
        elif c == "production_date":
            v = v.to_pydatetime()
        elif c == "dq_flags" and v == "":
            v = None
        wd.cell(row=r, column=col_idx[c], value=v)
    # calculated columns
    wd.cell(row=r, column=col_idx["yield_pct"], value=f"=IFERROR(M{r}/G{r},\"\")")
    wd.cell(row=r, column=col_idx["is_off_spec"],
            value=f"=IF(S{r}=0,\"\",IF(OR(P{r}>{SPEC_FFA},Q{r}>{SPEC_COL},R{r}>{SPEC_MOIST}),1,0))")
for c, f in fmt.items():
    L = get_column_letter(col_idx[c])
    for r in range(2, LAST + 1):
        wd[f"{L}{r}"].number_format = f
tab = Table(displayName="tblBatch", ref=f"A1:{get_column_letter(len(cols))}{LAST}")
tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
wd.add_table(tab)
wd.freeze_panes = "B2"
widths(wd, [13, 12, 10, 9, 7, 26] + [11] * 16 + [24])
wd["O1"].comment = Comment("Calculated column: RBDPO output / CPO input", "Analyst")
wd["T1"].comment = Comment("Calculated column: 1 if any lab result breaks a spec limit on the Assumptions sheet", "Analyst")


def rng(col):
    return f"Data!${col}$2:${col}${LAST}"


D = {k: rng(get_column_letter(v)) for k, v in col_idx.items()}

# =========================================================== Monthly_Summary
wm = wb.create_sheet("Monthly_Summary")
title(wm, "Monthly KPI Summary", "All values are SUMIFS / COUNTIFS / SUMPRODUCT formulas on the Data sheet.")
hdr = ["Month", "Batches", "CPO processed (t)", "RBDPO produced (t)", "Refining yield",
       "Wtd CPO FFA (%)", "Off-spec rate", "Steam (t/t CPO)", "vs yield target"]
header(wm, 4, hdr)
months = sorted(fb.year_month.unique())
for i, m in enumerate(months):
    r = 5 + i
    wm.cell(row=r, column=1, value=m)
    wm.cell(row=r, column=2, value=f"=COUNTIFS({D['year_month']},A{r})")
    wm.cell(row=r, column=3, value=f"=SUMIFS({D['cpo_input_mt']},{D['year_month']},A{r})")
    wm.cell(row=r, column=4, value=f"=SUMIFS({D['rbdpo_output_mt']},{D['year_month']},A{r})")
    wm.cell(row=r, column=5, value=f"=IFERROR(D{r}/C{r},0)")
    wm.cell(row=r, column=6, value=f"=IFERROR(SUMPRODUCT(({D['year_month']}=A{r})*{D['cpo_input_mt']}*{D['cpo_ffa_pct']})/C{r},0)")
    wm.cell(row=r, column=7, value=f"=IFERROR(SUMIFS({D['is_off_spec']},{D['year_month']},A{r})/COUNTIFS({D['year_month']},A{r},{D['has_lab_result']},1),0)")
    wm.cell(row=r, column=8, value=f"=IFERROR(SUMIFS({D['steam_mt']},{D['year_month']},A{r})/C{r},0)")
    wm.cell(row=r, column=9, value=f"=E{r}-{TGT_Y}")
last_m = 4 + len(months)
tr = last_m + 1
wm.cell(row=tr, column=1, value="Total / overall")
wm.cell(row=tr, column=2, value=f"=SUM(B5:B{last_m})")
wm.cell(row=tr, column=3, value=f"=SUM(C5:C{last_m})")
wm.cell(row=tr, column=4, value=f"=SUM(D5:D{last_m})")
wm.cell(row=tr, column=5, value=f"=IFERROR(D{tr}/C{tr},0)")
wm.cell(row=tr, column=6, value=f"=IFERROR(SUMPRODUCT({D['cpo_input_mt']},{D['cpo_ffa_pct']})/C{tr},0)")
wm.cell(row=tr, column=7, value=f"=IFERROR(SUM({D['is_off_spec']})/COUNTIFS({D['has_lab_result']},1),0)")
wm.cell(row=tr, column=8, value=f"=IFERROR(SUM({D['steam_mt']})/C{tr},0)")
wm.cell(row=tr, column=9, value=f"=E{tr}-{TGT_Y}")
fmts = [None, "#,##0", "#,##0", "#,##0", "0.00%", "0.00", "0.0%", "0.0000", "+0.00%;-0.00%;0.00%"]
for c, f in enumerate(fmts, start=1):
    style_range(wm, 5, tr, c, c, f)
    wm.cell(row=tr, column=c).font = F_BOLD
wm.conditional_formatting.add(f"G5:G{last_m}", ColorScaleRule(start_type="min", start_color="FFFFFF",
                                                              end_type="max", end_color="EC835A"))
widths(wm, [16, 10, 18, 18, 14, 15, 13, 15, 15])
ch = LineChart()
ch.title, ch.y_axis.title, ch.height, ch.width = "Monthly refining yield", "Yield", 7.5, 22
ch.add_data(Reference(wm, min_col=5, min_row=4, max_row=last_m), titles_from_data=True)
ch.set_categories(Reference(wm, min_col=1, min_row=5, max_row=last_m))
ch.y_axis.number_format, ch.y_axis.scaling.min, ch.y_axis.scaling.max = "0.0%", 0.94, 0.952
ch.series[0].graphicalProperties.line.solidFill = "2A78D6"
ch.legend = None
wm.add_chart(finish_chart(ch), f"A{tr + 3}")

# ======================================================== Supplier_Scorecard
wsu = wb.create_sheet("Supplier_Scorecard")
title(wsu, "Supplier (Mill) Scorecard", "Which mills send the best crude oil - and what is the gap worth?")
hdr = ["Supplier", "Batches", "CPO supplied (t)", "Wtd CPO FFA (%)", "Avg DOBI", "Avg bleaching earth (%)",
       "Refining yield", "Off-spec rate", "Yield rank", "Yield gap vs best", "RBDPO lost (t)", "Opportunity (MYR)"]
header(wsu, 4, hdr)
sups = sup.supplier_name.tolist()
for i, s in enumerate(sups):
    r = 5 + i
    wsu.cell(row=r, column=1, value=s)
    wsu.cell(row=r, column=2, value=f"=COUNTIFS({D['supplier_name']},A{r})")
    wsu.cell(row=r, column=3, value=f"=SUMIFS({D['cpo_input_mt']},{D['supplier_name']},A{r})")
    wsu.cell(row=r, column=4, value=f"=IFERROR(SUMPRODUCT(({D['supplier_name']}=A{r})*{D['cpo_input_mt']}*{D['cpo_ffa_pct']})/C{r},0)")
    wsu.cell(row=r, column=5, value=f"=IFERROR(AVERAGEIFS({D['cpo_dobi']},{D['supplier_name']},A{r}),0)")
    wsu.cell(row=r, column=6, value=f"=IFERROR(AVERAGEIFS({D['bleaching_earth_pct']},{D['supplier_name']},A{r}),0)")
    wsu.cell(row=r, column=7, value=f"=IFERROR(SUMIFS({D['rbdpo_output_mt']},{D['supplier_name']},A{r})/C{r},0)")
    wsu.cell(row=r, column=8, value=f"=IFERROR(SUMIFS({D['is_off_spec']},{D['supplier_name']},A{r})/COUNTIFS({D['supplier_name']},A{r},{D['has_lab_result']},1),0)")
    last_s = 4 + len(sups)
    wsu.cell(row=r, column=9, value=f"=RANK(G{r},$G$5:$G${last_s},0)")
    wsu.cell(row=r, column=10, value=f"=MAX($G$5:$G${last_s})-G{r}")
    wsu.cell(row=r, column=11, value=f"=J{r}*C{r}")
    wsu.cell(row=r, column=12, value=f"=K{r}*{PRICE}")
tr = last_s + 1
wsu.cell(row=tr, column=1, value="Total")
for col, f in [(2, "SUM"), (3, "SUM"), (11, "SUM"), (12, "SUM")]:
    L = get_column_letter(col)
    wsu.cell(row=tr, column=col, value=f"={f}({L}5:{L}{last_s})")
fmts = [None, "#,##0", "#,##0", "0.00", "0.00", "0.00", "0.00%", "0.0%", "0", "0.00%", "#,##0", "#,##0"]
for c, f in enumerate(fmts, start=1):
    style_range(wsu, 5, tr, c, c, f)
    wsu.cell(row=tr, column=c).font = F_BOLD
wsu.conditional_formatting.add(f"G5:G{last_s}", ColorScaleRule(start_type="min", start_color="F8D3C4",
                                                               end_type="max", end_color="B7D3F6"))
wsu.conditional_formatting.add(f"L5:L{last_s}", DataBarRule(start_type="num", start_value=0, end_type="max", color="EB6834"))
best = tr + 2
wsu.cell(row=best, column=1, value="Best mill by yield:").font = F_BOLD
wsu.cell(row=best, column=2, value=f"=INDEX($A$5:$A${last_s},MATCH(1,$I$5:$I${last_s},0))").font = F_BOLD
wsu.cell(row=best + 1, column=1, value="Opportunity uses the Average RBDPO price on the Assumptions sheet.").font = F_SUB
widths(wsu, [28, 9, 15, 13, 10, 14, 12, 11, 9, 13, 12, 16])
ch = BarChart()
ch.type, ch.title, ch.height, ch.width = "bar", "Refining yield by supplier", 7.5, 18
ch.add_data(Reference(wsu, min_col=7, min_row=4, max_row=last_s), titles_from_data=True)
ch.set_categories(Reference(wsu, min_col=1, min_row=5, max_row=last_s))
ch.x_axis.number_format = "0%"
ch.y_axis.number_format, ch.y_axis.scaling.min, ch.y_axis.scaling.max = "0.0%", 0.93, 0.955
ch.series[0].graphicalProperties.solidFill = "2A78D6"
ch.legend = None
wsu.add_chart(finish_chart(ch), f"A{best + 3}")

# ========================================================= Line_Shift_Matrix
wl = wb.create_sheet("Line_Shift_Matrix")
title(wl, "Off-spec Rate: Line x Shift", "Share of lab-tested batches breaking any spec limit.")
header(wl, 4, ["Line", "Morning", "Evening", "Night", "All shifts", "Off-spec batches"])
for i, ln in enumerate("ABC"):
    r = 5 + i
    wl.cell(row=r, column=1, value=ln)
    for j, sh in enumerate(["Morning", "Evening", "Night"]):
        L = get_column_letter(2 + j)
        wl[f"{L}4"] = sh
        wl.cell(row=r, column=2 + j,
                value=f"=IFERROR(SUMIFS({D['is_off_spec']},{D['line_code']},$A{r},{D['shift']},{L}$4)"
                      f"/COUNTIFS({D['line_code']},$A{r},{D['shift']},{L}$4,{D['has_lab_result']},1),0)")
    wl.cell(row=r, column=5, value=f"=IFERROR(SUMIFS({D['is_off_spec']},{D['line_code']},$A{r})/COUNTIFS({D['line_code']},$A{r},{D['has_lab_result']},1),0)")
    wl.cell(row=r, column=6, value=f"=SUMIFS({D['is_off_spec']},{D['line_code']},$A{r})")
style_range(wl, 5, 7, 1, 1)
style_range(wl, 5, 7, 2, 5, "0.0%")
style_range(wl, 5, 7, 6, 6, "#,##0")
wl.conditional_formatting.add("B5:D7", ColorScaleRule(start_type="min", start_color="FFFFFF",
                                                      end_type="max", end_color="D03B3B"))
wl["A9"] = "Reading: Line C (commissioned 2005) runs a lower deodorizer temperature and weaker vacuum - see FFA_Band and the Power BI dashboard."
wl["A9"].font = F_SUB
widths(wl, [10, 12, 12, 12, 12, 16])

# ========================================================= FFA_Band_Analysis
wf = wb.create_sheet("FFA_Band_Analysis")
title(wf, "Yield vs Crude FFA Band", "Data mining in Excel: band the driver, aggregate the outcome, fit a trend.")
header(wf, 4, ["Band from (%)", "Band to (%)", "Band label", "Batches", "CPO (t)", "Refining yield", "PFAD yield", "Band mid-point"])
bands = [(2.0, 3.0), (3.0, 3.5), (3.5, 4.0), (4.0, 4.5), (4.5, 5.0), (5.0, 7.0)]
for i, (lo, hi) in enumerate(bands):
    r = 5 + i
    for col, v in [(1, lo), (2, hi)]:
        c = wf.cell(row=r, column=col, value=v)
        c.font, c.fill = F_INPUT, FILL_INPUT
    wf.cell(row=r, column=3, value=f'=TEXT(A{r},"0.0")&" - "&TEXT(B{r},"0.0")&" %"')
    crit = f'{D["cpo_ffa_pct"]},">="&A{r},{D["cpo_ffa_pct"]},"<"&B{r}'
    wf.cell(row=r, column=4, value=f"=COUNTIFS({crit})")
    wf.cell(row=r, column=5, value=f"=SUMIFS({D['cpo_input_mt']},{crit})")
    wf.cell(row=r, column=6, value=f"=IFERROR(SUMIFS({D['rbdpo_output_mt']},{crit})/E{r},0)")
    wf.cell(row=r, column=7, value=f"=IFERROR(SUMIFS({D['pfad_output_mt']},{crit})/E{r},0)")
    wf.cell(row=r, column=8, value=f"=(A{r}+B{r})/2")
lb = 4 + len(bands)
for c, f in enumerate(["0.0", "0.0", None, "#,##0", "#,##0", "0.00%", "0.00%", "0.00"], start=1):
    style_range(wf, 5, lb, c, c, f, font=F_INPUT if c <= 2 else F_BODY)
wf.cell(row=lb + 2, column=1, value="Batch-level linear fit (all batches)").font = F_BOLD
wf.cell(row=lb + 3, column=1, value="Slope: yield change per +1 % FFA")
c = wf.cell(row=lb + 3, column=6, value=f"=SLOPE({D['yield_pct']},{D['cpo_ffa_pct']})")
c.number_format = "0.00%"
wf.cell(row=lb + 4, column=1, value="R squared")
c = wf.cell(row=lb + 4, column=6, value=f"=RSQ({D['yield_pct']},{D['cpo_ffa_pct']})")
c.number_format = "0.000"
wf.cell(row=lb + 5, column=1, value="Value of 1 % lower FFA on 100,000 t CPO (MYR)")
c = wf.cell(row=lb + 5, column=6, value=f"=-F{lb + 3}*100000*{PRICE}")
c.number_format = "#,##0"
for r in range(lb + 3, lb + 6):
    wf.cell(row=r, column=1).font = F_BODY
    wf.cell(row=r, column=6).font = F_BOLD
wf.cell(row=lb + 6, column=1, value="Band edges (yellow) are inputs - try narrower bands.").font = F_SUB
widths(wf, [14, 12, 16, 10, 12, 14, 12, 14])
ch = BarChart()
ch.title, ch.height, ch.width = "Refining yield by crude FFA band", 7.5, 18
ch.add_data(Reference(wf, min_col=6, min_row=4, max_row=lb), titles_from_data=True)
ch.set_categories(Reference(wf, min_col=3, min_row=5, max_row=lb))
ch.y_axis.number_format, ch.y_axis.scaling.min, ch.y_axis.scaling.max = "0.0%", 0.92, 0.96
ch.series[0].graphicalProperties.solidFill = "2A78D6"
ch.legend = None
wf.add_chart(finish_chart(ch), f"A{lb + 8}")

# =========================================================== Downtime_Pareto
wdp = wb.create_sheet("Downtime_Pareto")
title(wdp, "Downtime Pareto", "Events from the CMMS log (left) summarised into an 80/20 Pareto (right).")
ev_cols = ["event_id", "line_code", "event_date", "shift", "category", "description", "duration_min", "is_planned"]
header(wdp, 4, ev_cols)
dts = dt.sort_values("event_date")
for i, rec in enumerate(dts[ev_cols].itertuples(index=False), start=5):
    for j, v in enumerate(rec, start=1):
        if isinstance(v, pd.Timestamp):
            v = v.to_pydatetime()
        c = wdp.cell(row=i, column=j, value=v)
        c.font = F_BODY
        if j == 3:
            c.number_format = "yyyy-mm-dd"
le = 4 + len(dts)
EV = lambda L: f"${L}$5:${L}${le}"
header(wdp, 4, ["Category", "Events", "Hours", "% of total", "Cumulative %"], start_col=10)
order = dt.groupby("category").duration_min.sum().sort_values(ascending=False).index.tolist()
for i, cat in enumerate(order):
    r = 5 + i
    wdp.cell(row=r, column=10, value=cat)
    wdp.cell(row=r, column=11, value=f"=COUNTIFS({EV('E')},J{r})")
    wdp.cell(row=r, column=12, value=f"=SUMIFS({EV('G')},{EV('E')},J{r})/60")
    lp = 4 + len(order)
    wdp.cell(row=r, column=13, value=f"=L{r}/SUM($L$5:$L${lp})")
    wdp.cell(row=r, column=14, value=f"=SUM($L$5:L{r})/SUM($L$5:$L${lp})")
for c, f in zip(range(10, 15), [None, "#,##0", "#,##0.0", "0.0%", "0.0%"]):
    style_range(wdp, 5, lp, c, c, f)
widths(wdp, [10, 6, 12, 9, 20, 34, 12, 10, 3, 22, 9, 10, 11, 13])
wdp.freeze_panes = "A5"
ch = BarChart()
ch.title, ch.height, ch.width = "Downtime hours by cause", 7.5, 16
ch.add_data(Reference(wdp, min_col=12, min_row=4, max_row=lp), titles_from_data=True)
ch.set_categories(Reference(wdp, min_col=10, min_row=5, max_row=lp))
ch.series[0].graphicalProperties.solidFill = "2A78D6"
ch.legend = None
wdp.add_chart(finish_chart(ch), "J14")

# =========================================================== Data_Dictionary
wdd = wb.create_sheet("Data_Dictionary")
title(wdd, "Data Dictionary", "Columns on the Data sheet.")
header(wdd, 4, ["Column", "Description", "Unit"])
dd = [
    ("batch_id", "Unique batch: B + yymmdd - line + shift number", ""),
    ("production_date", "Production day (07:00 to 07:00)", "date"),
    ("year_month", "Calendar month of production", "yyyy-mm"),
    ("shift", "Morning 07-15, Evening 15-23, Night 23-07", ""),
    ("line_code", "Refining line A (2012), B (2016), C (2005)", ""),
    ("supplier_name", "Palm oil mill that supplied the crude oil (fictional)", ""),
    ("cpo_input_mt", "Crude palm oil fed to the refinery", "tonnes"),
    ("cpo_ffa_pct", "Free fatty acid content of the crude oil", "% as palmitic"),
    ("cpo_dobi", "Deterioration of Bleachability Index - higher is easier to bleach", "index"),
    ("bleaching_earth_pct", "Bleaching earth dose", "% of CPO"),
    ("deo_temp_c", "Deodorizer temperature", "deg C"),
    ("deo_vacuum_mbar", "Deodorizer absolute pressure - lower is better", "mbar"),
    ("rbdpo_output_mt", "Refined, bleached & deodorized palm oil produced", "tonnes"),
    ("pfad_output_mt", "Palm fatty acid distillate by-product", "tonnes"),
    ("yield_pct", "Calculated: RBDPO / CPO", "%"),
    ("rbdpo_ffa_pct", "FFA in finished RBDPO (spec <= 0.10 %)", "%"),
    ("color_red", "Lovibond red colour of RBDPO (spec <= 3.0)", "R"),
    ("rbdpo_moisture_pct", "Moisture & impurities of RBDPO (spec <= 0.10 %)", "%"),
    ("has_lab_result", "1 if the batch has a LIMS result", "flag"),
    ("is_off_spec", "Calculated: 1 if any spec on the Assumptions sheet is broken", "flag"),
    ("steam_mt", "Steam consumed by the batch", "tonnes"),
    ("electricity_kwh", "Electricity consumed by the batch (MWh rows converted)", "kWh"),
    ("dq_flags", "Cleaning rules applied to the row (audit trail)", "text"),
]
for i, r in enumerate(dd, start=5):
    for j, v in enumerate(r, start=1):
        c = wdd.cell(row=i, column=j, value=v)
        c.font, c.border = F_BODY, BOX
widths(wdd, [22, 70, 16])

wb.save(OUT)
print(f"Saved {OUT.relative_to(ROOT)}  ({N:,} data rows)")
