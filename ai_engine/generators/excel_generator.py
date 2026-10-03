"""
Excel Report Generator - creates multi-sheet Excel (.xlsx) workbooks.

Consumes ExecutiveReportData enriched with real analysis results.
Sheets: Dashboard, Column Profiling, Statistics, Quality, Correlations,
Outliers, ML Models, Trends, Anomalies, Recommendations.

Single Responsibility: converts ExecutiveReportData into a styled Excel workbook.
"""

from __future__ import annotations

import os
from copy import copy
from typing import Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ai_engine.domain.entities import ExecutiveReportData


class ExcelGenerator:
    """Generates a professionally styled multi-sheet Excel workbook."""

    def __init__(self, data: ExecutiveReportData) -> None:
        self._data = data

    def generate(self, output_path: str) -> Optional[str]:
        try:
            wb = openpyxl.Workbook()
            if "Sheet" in wb.sheetnames:
                wb.remove(wb["Sheet"])

            ff = "Segoe UI"
            title_font = Font(name=ff, size=16, bold=True, color="0F172A")
            subtitle_font = Font(name=ff, size=10, italic=True, color="64748B")
            section_font = Font(name=ff, size=12, bold=True, color="1E293B")
            header_font = Font(name=ff, size=10, bold=True, color="FFFFFF")
            bold_font = Font(name=ff, size=10, bold=True, color="0F172A")
            normal_font = Font(name=ff, size=10, color="1E293B")
            val_font = Font(name=ff, size=18, bold=True, color="4F46E5")
            lbl_font = Font(name=ff, size=9, bold=True, color="64748B")

            hdr_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
            zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
            card_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
            high_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
            med_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
            low_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")

            thin = Side(border_style="thin", color="CBD5E1")
            grid = Border(left=thin, right=thin, top=thin, bottom=thin)
            ac = Alignment(horizontal="center", vertical="center", wrap_text=True)
            al = Alignment(horizontal="left", vertical="center", wrap_text=True)

            def write_headers(ws, row, headers):
                for c, h in enumerate(headers, 1):
                    cell = ws.cell(row=row, column=c, value=h)
                    cell.font = header_font
                    cell.fill = hdr_fill
                    cell.alignment = ac
                    cell.border = grid

            def write_row(ws, row, cells, zebra_idx=-1):
                for c, val in enumerate(cells, 1):
                    cell = ws.cell(row=row, column=c, value=val)
                    cell.font = normal_font
                    cell.border = grid
                    if zebra_idx >= 0 and zebra_idx % 2 == 1:
                        cell.fill = zebra

            def auto_width(ws, max_w=45):
                for col in ws.columns:
                    mx = 0
                    letter = get_column_letter(col[0].column)
                    for cell in col:
                        if cell.coordinate in ws.merged_cells:
                            continue
                        if cell.value:
                            lines = str(cell.value).split('\n')
                            mx = max(mx, max(len(l) for l in lines))
                    ws.column_dimensions[letter].width = min(max(mx + 3, 11), max_w)

            def finish_sheet(ws, freeze="A4", table_end=None, tab_color="4F46E5"):
                """Apply consistent usability and print formatting to every report tab."""
                ws.sheet_view.showGridLines = False
                ws.sheet_view.zoomScale = 90
                ws.freeze_panes = freeze
                ws.sheet_properties.tabColor = tab_color
                ws.print_title_rows = "1:3"
                ws.page_setup.orientation = "landscape"
                ws.page_setup.paperSize = ws.PAPERSIZE_A4
                ws.page_setup.fitToWidth = 1
                ws.page_setup.fitToHeight = 0
                ws.sheet_properties.pageSetUpPr.fitToPage = True
                ws.page_margins.left = 0.25
                ws.page_margins.right = 0.25
                ws.page_margins.top = 0.5
                ws.page_margins.bottom = 0.5
                ws.print_options.horizontalCentered = False
                ws.row_dimensions[1].height = 26
                if ws.max_row >= 3:
                    ws.row_dimensions[3].height = 24
                if table_end and table_end[0] >= 3 and table_end[1] >= 1:
                    ws.auto_filter.ref = f"A3:{get_column_letter(table_end[1])}{table_end[0]}"
                # Make table values readable and consistent in Excel.
                for row in ws.iter_rows():
                    for cell in row:
                        if cell.value is not None:
                            alignment = copy(cell.alignment)
                            alignment.vertical = "center"
                            cell.alignment = alignment
                            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                                cell.number_format = '#,##0.00;[Red]-#,##0.00'
                for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
                    if row and row[0].row != 3:
                        ws.row_dimensions[row[0].row].height = max(ws.row_dimensions[row[0].row].height or 15, 20)

            d = self._data

            # ======== SHEET 1: DASHBOARD ========
            ws1 = wb.create_sheet("Dashboard")
            ws1["A1"] = "Analytics Report Dashboard"
            ws1["A1"].font = title_font
            ws1["A2"] = f"Generated: {d.generated_at.strftime('%Y-%m-%d %H:%M:%S')}  |  Dataset: {d.dataset_name} ({d.dataset_shape[0]:,} rows x {d.dataset_shape[1]} cols)"
            ws1["A2"].font = subtitle_font

            # KPI Cards
            kpi_cards = [
                ("DATA QUALITY", f"{d.quality_score:.1f}/100"),
                ("TOTAL ROWS", f"{d.dataset_shape[0]:,}"),
                ("FEATURES", str(d.dataset_shape[1])),
                ("MISSING %", f"{d.missing_percentage:.2f}%"),
            ]
            for i, (lbl, val) in enumerate(kpi_cards):
                col = i * 2 + 1
                ws1.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col + 1)
                ws1.cell(row=4, column=col, value=lbl).font = lbl_font
                ws1.cell(row=4, column=col).fill = card_fill
                ws1.cell(row=4, column=col).alignment = ac
                ws1.merge_cells(start_row=5, start_column=col, end_row=5, end_column=col + 1)
                ws1.cell(row=5, column=col, value=val).font = val_font
                ws1.cell(row=5, column=col).fill = card_fill
                ws1.cell(row=5, column=col).alignment = ac

            # Executive Summary
            ws1.cell(row=7, column=1, value="Executive Summary").font = section_font
            ws1.merge_cells("A8:H10")
            ws1["A8"] = d.summary_paragraph or f"Analysis of {d.dataset_name}."
            ws1["A8"].font = normal_font
            ws1["A8"].alignment = Alignment(wrap_text=True, vertical="top")

            auto_width(ws1)
            finish_sheet(ws1, freeze="A4", tab_color="4F46E5")

            # ======== SHEET 2: STATISTICS ========
            ws2 = wb.create_sheet("Descriptive Statistics")
            ws2["A1"] = "Descriptive Statistics"
            ws2["A1"].font = title_font

            stats = d.statistics
            ns = stats.get("numeric_stats", [])
            if ns:
                write_headers(ws2, 3, ["Column", "Count", "Mean", "Std Dev", "Min", "Q1", "Median", "Q3", "Max", "IQR", "Skewness", "Kurtosis"])
                for r, s in enumerate(ns, 4):
                    write_row(ws2, r, [
                        s["column"], s["count"], round(s["mean"], 4), round(s["std"], 4),
                        round(s["min"], 4), round(s["q1"], 4), round(s["median"], 4),
                        round(s["q3"], 4), round(s["max"], 4), round(s["iqr"], 4),
                        round(s["skewness"], 4), round(s["kurtosis"], 4)
                    ], r - 4)

            cs = stats.get("categorical_stats", [])
            if cs:
                start = (4 + len(ns)) if ns else 3
                ws2.cell(row=start, column=1, value="Categorical Columns").font = section_font
                start += 1
                write_headers(ws2, start, ["Column", "Unique", "Top Value", "Top Count", "Top Frequency"])
                for r, c in enumerate(cs, start + 1):
                    top = c.get("top_values", [{}])[0] if c.get("top_values") else {}
                    write_row(ws2, r, [
                        c["column"], c.get("unique", 0),
                        str(top.get("value", "N/A"))[:50],
                        top.get("count", 0),
                        f"{top.get('frequency', 0):.1f}%"
                    ], r - start - 1)

            auto_width(ws2)
            finish_sheet(ws2, freeze="A4", table_end=((4 + len(ns)) if ns else 3, 12 if ns else 5), tab_color="0EA5E9")

            # ======== SHEET 3: QUALITY ========
            ws3 = wb.create_sheet("Data Quality")
            ws3["A1"] = "Data Quality Assessment"
            ws3["A1"].font = title_font

            qd = d.quality_detail
            if qd:
                ws3.cell(row=3, column=1, value=f"Quality Score: {qd.get('quality_score', d.quality_score):.1f}/100").font = bold_font
                ws3.cell(row=3, column=4, value=f"Duplicates: {qd.get('duplicate_rows', 0):,}").font = bold_font

                missing = qd.get("missing_per_column", [])
                if missing:
                    write_headers(ws3, 5, ["Column", "Missing Count", "Missing %"])
                    for r, m in enumerate(missing, 6):
                        write_row(ws3, r, [m["column"], m["missing_count"], f"{m['missing_pct']:.2f}%"], r - 6)

                type_issues = qd.get("type_issues", [])
                if type_issues:
                    ti_start = 7 + len(missing)
                    ws3.cell(row=ti_start, column=1, value="Type Issues").font = section_font
                    write_headers(ws3, ti_start + 1, ["Column", "Issue", "Detected Types"])
                    for r, ti in enumerate(type_issues, ti_start + 2):
                        write_row(ws3, r, [ti["column"], ti["issue"], ", ".join(ti.get("types", []))], r - ti_start - 2)

            auto_width(ws3)
            finish_sheet(ws3, freeze="A6", tab_color="10B981")

            # ======== SHEET 4: CORRELATIONS ========
            ws4 = wb.create_sheet("Correlations")
            ws4["A1"] = "Correlation Analysis"
            ws4["A1"].font = title_font

            pairs = d.correlations.get("top_pairs", []) if d.correlations else []
            if pairs:
                write_headers(ws4, 3, ["Feature A", "Feature B", "Correlation", "Strength"])
                for r, p in enumerate(pairs, 4):
                    rv = abs(p.get("correlation", 0))
                    strength = "Strong" if rv > 0.8 else ("Moderate" if rv > 0.6 else "Weak")
                    write_row(ws4, r, [p["col_a"], p["col_b"], round(p.get("correlation", 0), 4), strength], r - 4)
            else:
                ws4.cell(row=3, column=1, value="No strong correlations detected.").font = subtitle_font

            auto_width(ws4)
            finish_sheet(ws4, freeze="A4", table_end=(3 + len(pairs), 4) if pairs else None, tab_color="8B5CF6")

            # ======== SHEET 5: OUTLIERS ========
            ws5 = wb.create_sheet("Outliers")
            ws5["A1"] = "Outlier Detection"
            ws5["A1"].font = title_font

            iqr = d.outliers.get("iqr_outliers", []) if d.outliers else []
            if iqr:
                write_headers(ws5, 3, ["Column", "Outlier Count", "Outlier %", "Lower Bound", "Upper Bound"])
                for r, o in enumerate(iqr, 4):
                    write_row(ws5, r, [
                        o["column"], o.get("count", 0),
                        f"{o.get('percentage', 0):.1f}%",
                        round(o.get("lower_bound", 0), 4),
                        round(o.get("upper_bound", 0), 4)
                    ], r - 4)
            else:
                ws5.cell(row=3, column=1, value="No outliers detected.").font = subtitle_font

            auto_width(ws5)
            finish_sheet(ws5, freeze="A4", table_end=(3 + len(iqr), 5) if iqr else None, tab_color="F59E0B")

            # ======== SHEET 6: TRENDS & ANOMALIES ========
            ws6 = wb.create_sheet("Trends & Anomalies")
            ws6["A1"] = "AI Trend Analysis"
            ws6["A1"].font = title_font

            if d.trends:
                write_headers(ws6, 3, ["Column", "Direction", "R2 Score", "Slope", "Change %", "Mean", "Std Dev", "Summary"])
                for r, t in enumerate(d.trends, 4):
                    write_row(ws6, r, [
                        t.column, t.direction.value.upper(), round(t.r2_score, 4),
                        round(t.slope, 6), f"{t.pct_change:+.1f}%",
                        round(t.mean_val, 4), round(t.std_val, 4), t.summary_text[:80]
                    ], r - 4)

            if d.anomalies and d.anomalies.anomalous_rows_count > 0:
                a_start = 5 + len(d.trends)
                ws6.cell(row=a_start, column=1, value="Anomalous Observations").font = section_font
                write_headers(ws6, a_start + 1, ["Row", "Column", "Value", "Score", "Reason"])
                for r, item in enumerate(d.anomalies.detected_anomalies[:40], a_start + 2):
                    write_row(ws6, r, [
                        item.row_index, item.column, str(item.value)[:30],
                        round(item.score, 4), item.reason[:60]
                    ], r - a_start - 2)

            auto_width(ws6)
            finish_sheet(ws6, freeze="A4", tab_color="EC4899")

            # ======== SHEET 7: ML MODELS ========
            ws7 = wb.create_sheet("ML Models")
            ws7["A1"] = "ML Model Performance"
            ws7["A1"].font = title_font

            if d.ml_models:
                write_headers(ws7, 3, ["Model Name", "Algorithm", "Problem Type", "Metrics"])
                for r, m in enumerate(d.ml_models, 4):
                    metrics_str = " | ".join([f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}" for k, v in m.get("metrics", {}).items()])
                    write_row(ws7, r, [m["model_name"], m["algorithm"], m.get("problem_type", "N/A"), metrics_str], r - 4)
            else:
                ws7.cell(row=3, column=1, value="No trained models found for this dataset.").font = subtitle_font

            auto_width(ws7)
            finish_sheet(ws7, freeze="A4", table_end=(3 + len(d.ml_models), 4) if d.ml_models else None, tab_color="64748B")

            # ======== SHEET 8: RECOMMENDATIONS ========
            ws8 = wb.create_sheet("Recommendations")
            ws8["A1"] = "Strategic Recommendations"
            ws8["A1"].font = title_font

            if d.recommendations:
                write_headers(ws8, 3, ["#", "Impact", "Title", "Category", "Description", "Action Items"])
                for r, rec in enumerate(d.recommendations, 4):
                    ws8.cell(row=r, column=1, value=r - 3).font = bold_font
                    ws8.cell(row=r, column=1).alignment = ac

                    imp = rec.impact.value.upper()
                    imp_cell = ws8.cell(row=r, column=2, value=imp)
                    imp_cell.alignment = ac
                    if "HIGH" in imp:
                        imp_cell.fill = high_fill
                        imp_cell.font = Font(name=ff, bold=True, color="991B1B")
                    elif "MEDIUM" in imp:
                        imp_cell.fill = med_fill
                        imp_cell.font = Font(name=ff, bold=True, color="92400E")
                    else:
                        imp_cell.fill = low_fill
                        imp_cell.font = Font(name=ff, bold=True, color="065F46")

                    ws8.cell(row=r, column=3, value=rec.title).font = bold_font
                    ws8.cell(row=r, column=4, value=rec.category).alignment = ac
                    ws8.cell(row=r, column=5, value=rec.description)
                    bullets = "\n".join([f"- {a}" for a in rec.action_items]) if rec.action_items else "N/A"
                    ws8.cell(row=r, column=6, value=bullets).alignment = Alignment(wrap_text=True, vertical="top")

                    for c in range(1, 7):
                        ws8.cell(row=r, column=c).border = grid
            else:
                ws8.cell(row=3, column=1, value="No recommendations generated.").font = subtitle_font

            auto_width(ws8)
            finish_sheet(ws8, freeze="A4", table_end=(3 + len(d.recommendations), 6) if d.recommendations else None, tab_color="14B8A6")

            # Save
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            wb.save(output_path)
            return output_path
        except Exception as e:
            print(f"[ExcelGenerator] Error: {e}")
            import traceback
            traceback.print_exc()
            return None
