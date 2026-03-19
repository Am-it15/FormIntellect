import os
from collections import Counter
from datetime import datetime

try:
    import openpyxl
    from openpyxl import load_workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

import pandas as pd


NAVY       = "1F3864"
BLUE       = "2E75B6"
LIGHT_BLUE = "DEEAF1"
WHITE      = "FFFFFF"


def generate_analysis_sheet(file_path: str, submitted_count: int = 0) -> dict:
    """
    Read file_path, generate an Analysis sheet with frequency tables and charts.
    Returns {"success": bool, "error": str | None, "file_path": str}
    """
    if not OPENPYXL_AVAILABLE:
        return {"success": False, "error": "openpyxl not installed. Run: pip install openpyxl"}

    lower = file_path.lower()
    if not (lower.endswith(".xlsx") or lower.endswith(".xls")):
        return {"success": False, "error": "Analysis sheet only supported for .xlsx / .xls files."}

    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        return {"success": False, "error": f"Could not read file: {e}"}

    try:
        wb = load_workbook(file_path)
        if "Analysis" in wb.sheetnames:
            del wb["Analysis"]
        ws = wb.create_sheet("Analysis")

        _write_analysis(ws, df, submitted_count)
        wb.save(file_path)
        return {"success": True, "error": None, "file_path": file_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def analyze_dataframe(df: pd.DataFrame) -> dict:
    """
    Return a summary dict for all columns — used by the sidebar live summary.
    """
    status_names = {"status", "submit", "submitted"}
    analysis_cols = [c for c in df.columns if c.lower() not in status_names]
    summary = {}

    for col_name in analysis_cols:
        series = df[col_name].dropna().astype(str).str.strip()
        series = series[series != ""]
        if series.empty:
            continue

        is_checkbox = series.str.contains(",").any()

        if is_checkbox:
            all_vals = []
            for v in series:
                all_vals.extend(x.strip() for x in v.split(",") if x.strip())
            freq = Counter(all_vals)
            total_respondents = len(series)
        else:
            freq = Counter(series.tolist())
            total_respondents = len(series)

        items = sorted(freq.items(), key=lambda x: -x[1])
        summary[col_name] = {
            "total_responses": total_respondents,
            "is_checkbox":     is_checkbox,
            "top_answers": [
                {
                    "answer": ans,
                    "count":  cnt,
                    "pct":    round(cnt / total_respondents * 100, 1) if total_respondents else 0,
                }
                for ans, cnt in items[:10]
            ],
        }
    return summary


# ── Internal: write styled analysis sheet ─────────────────────────────────────

def _solid(color):
    return PatternFill("solid", fgColor=color)

def _fnt(bold=False, color=WHITE, size=11):
    return Font(bold=bold, color=color, size=size)

def _write_analysis(ws, df, submitted_count):
    thin = Side(style="thin", color="CCCCCC")
    bdr  = Border(left=thin, right=thin, top=thin, bottom=thin)
    ctr  = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.merge_cells("A1:F1")
    ws["A1"] = "Response Analysis — FormIntellect"
    ws["A1"].fill      = _solid(NAVY)
    ws["A1"].font      = Font(bold=True, color=WHITE, size=14)
    ws["A1"].alignment = ctr
    ws.row_dimensions[1].height = 28

    ws["A2"] = f"Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}"
    ws["B2"] = f"Total rows: {len(df)}"
    ws["C2"] = f"Submitted: {submitted_count}"
    for cell in (ws["A2"], ws["B2"], ws["C2"]):
        cell.font = Font(color="444444", size=10, italic=True)

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 12

    status_names  = {"status", "submit", "submitted"}
    analysis_cols = [c for c in df.columns if c.lower() not in status_names]
    current_row   = 4

    for col_name in analysis_cols:
        series = df[col_name].dropna().astype(str).str.strip()
        series = series[series != ""]
        if series.empty:
            continue

        is_checkbox = series.str.contains(",").any()

        ws.merge_cells(
            start_row=current_row, start_column=1,
            end_row=current_row,   end_column=5
        )
        cell = ws.cell(row=current_row, column=1, value=col_name)
        cell.fill      = _solid(BLUE)
        cell.font      = Font(bold=True, color=WHITE, size=11)
        cell.alignment = ctr
        ws.row_dimensions[current_row].height = 20
        current_row += 1

        hdr_row = current_row
        for ci, h in enumerate(["#", "Answer", "Count", "% of Total"], 1):
            c = ws.cell(row=current_row, column=ci, value=h)
            c.fill      = _solid(BLUE)
            c.font      = Font(bold=True, color=WHITE, size=10)
            c.alignment = ctr
            c.border    = bdr
        current_row += 1

        if is_checkbox:
            all_vals = []
            for v in series:
                all_vals.extend(x.strip() for x in v.split(",") if x.strip())
            freq             = Counter(all_vals)
            total_respondents = len(series)
        else:
            freq             = Counter(series.tolist())
            total_respondents = len(series)

        items_sorted = sorted(freq.items(), key=lambda x: -x[1])
        total_count  = sum(freq.values())
        data_start   = current_row

        for ri, (answer, count) in enumerate(items_sorted, 1):
            pct      = (count / total_respondents * 100) if total_respondents else 0
            row_vals = [ri, answer, count, f"{pct:.1f}%"]
            for ci, val in enumerate(row_vals, 1):
                c = ws.cell(row=current_row, column=ci, value=val)
                c.fill      = _solid(LIGHT_BLUE if ri % 2 == 0 else WHITE)
                c.font      = Font(color="1F1F1F", size=10)
                c.alignment = ctr
                c.border    = bdr
            current_row += 1

        total_row_idx = current_row
        total_pct     = "100%" if not is_checkbox else "---"
        for ci, val in enumerate(["", "TOTAL", total_count, total_pct], 1):
            c = ws.cell(row=current_row, column=ci, value=val)
            c.fill      = _solid(NAVY)
            c.font      = Font(bold=True, color=WHITE, size=10)
            c.alignment = ctr
            c.border    = bdr
        current_row += 1

        if items_sorted:
            chart              = BarChart()
            chart.type         = "col"
            chart.grouping     = "clustered"
            chart.title        = str(col_name)[:30]
            chart.y_axis.title = "Count"
            chart.x_axis.title = "Answer"
            chart.style        = 10
            chart.width        = 18
            chart.height       = 12
            data_ref = Reference(
                ws, min_col=3, max_col=3,
                min_row=hdr_row, max_row=total_row_idx - 1
            )
            cats_ref = Reference(
                ws, min_col=2, max_col=2,
                min_row=data_start, max_row=total_row_idx - 1
            )
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats_ref)
            ws.add_chart(chart, f"{get_column_letter(7)}{data_start}")

        current_row += 2
