"""
PDF Report Generator — creates comprehensive PDF documents using FPDF.

Consumes ExecutiveReportData (enriched with real analysis results by ReportService)
and produces a multi-page PDF with cover, KPIs, quality, statistics,
correlations, outliers, ML models, trends, anomalies, and recommendations.

Single Responsibility: converts ExecutiveReportData into a PDF document.
"""

from __future__ import annotations

import os
from typing import Optional

from ai_engine.domain.entities import ExecutiveReportData

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False


def _clean(text: str) -> str:
    if not text:
        return ""
    text = text.replace("—", "-").replace("–", "-").replace("×", "x").replace("•", "-").replace("’", "'").replace("”", '"').replace("“", '"')
    return text.encode("ascii", "ignore").decode("ascii")


def _fmt(val, d=2):
    if val is None: return "N/A"
    try:
        f = float(val)
        return f"{f:,.{d}f}" if abs(f) >= 1e6 else f"{f:.{d}f}"
    except (ValueError, TypeError):
        return str(val)


if FPDF_AVAILABLE:
    class ReportPDF(FPDF):
        def __init__(self, title_text="Analytics Report"):
            super().__init__()
            self._title_text = _clean(title_text)

        def header(self):
            if self.page_no() == 1: return
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(100, 116, 139)
            self.set_x(self.l_margin)
            self.cell(w=self.epw, h=8, text=f"DATAVIZ PRO  |  {self._title_text.upper()}", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(226, 232, 240)
            self.line(self.l_margin, self.t_margin + 7, self.w - self.r_margin, self.t_margin + 7)
            self.ln(6)

        def footer(self):
            if self.page_no() == 1: return
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(148, 163, 184)
            self.set_draw_color(226, 232, 240)
            self.line(self.l_margin, self.h - 17, self.w - self.r_margin, self.h - 17)
            self.cell(w=0, h=10, text=f"Page {self.page_no()}/{{nb}}  |  DataViz Pro", align="C")

        def stitle(self, text):
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(79, 70, 229)
            self.cell(w=0, h=8, text=_clean(text), new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(226, 232, 240)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(4)

        def btext(self, text):
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "", 10)
            self.set_text_color(51, 65, 85)
            self.multi_cell(w=0, h=5.5, text=_clean(text))
            self.ln(3)

        def kpi(self, x, y, w, h, label, value):
            self.set_fill_color(241, 245, 249)
            self.rect(x, y, w, h, "F")
            self.set_xy(x + 2, y + 2)
            self.set_font("Helvetica", "", 7.5)
            self.set_text_color(100, 116, 139)
            self.cell(w - 4, 4, text=label)
            self.set_x(x + 2)
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(79, 70, 229)
            self.cell(w - 4, 8, text=value)

        def thead(self, cols, widths):
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "B", 8.5)
            self.set_fill_color(15, 23, 42)
            self.set_text_color(255, 255, 255)
            for i, c in enumerate(cols):
                self.cell(widths[i], 7, text=_clean(c), border=1, fill=True, align="C")
            self.ln()

        def trow(self, cells, widths, zebra=False):
            self.set_x(self.l_margin)
            self.set_fill_color(248, 250, 252) if zebra else self.set_fill_color(255, 255, 255)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(51, 65, 85)
            for i, c in enumerate(cells):
                self.cell(widths[i], 6, text=_clean(str(c)), border=1, fill=True, align="C" if i > 0 else "L")
            self.ln()


class PDFGenerator:
    def __init__(self, data: ExecutiveReportData) -> None:
        self._data = data

    def generate(self, output_path: str) -> Optional[str]:
        if not FPDF_AVAILABLE:
            print("[PDFGenerator] fpdf2 is not installed.")
            return None
        try:
            d = self._data
            pdf = ReportPDF(d.title)
            pdf.alias_nb_pages()
            pdf.set_auto_page_break(auto=True, margin=20)

            # ======== COVER ========
            pdf.add_page()
            pdf.set_fill_color(15, 23, 42)
            pdf.rect(0, 0, 70, 297, "F")
            pdf.set_left_margin(80)
            pdf.set_y(60)
            pdf.set_font("Helvetica", "B", 22)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(w=115, h=10, text=_clean(d.title))
            pdf.ln(4)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(100, 116, 139)
            pdf.multi_cell(w=115, h=6, text=_clean("Comprehensive data analytics report with statistical profiling, quality assessment, correlation analysis, outlier detection, ML model evaluation, and AI-generated strategic recommendations."))
            pdf.ln(60)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(79, 70, 229)
            pdf.cell(w=115, h=5, text="REPORT METADATA", new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(79, 70, 229)
            pdf.line(80, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(4)
            for label, value in [("Dataset:", d.dataset_name), ("Dimensions:", f"{d.dataset_shape[0]:,} rows x {d.dataset_shape[1]} features"), ("Quality Score:", f"{d.quality_score:.1f}/100"), ("Missing Data:", f"{d.missing_percentage:.2f}%"), ("Generated:", d.generated_at.strftime('%Y-%m-%d %H:%M'))]:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(35, 6, text=label)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(51, 65, 85)
                pdf.cell(80, 6, text=_clean(str(value)), new_x="LMARGIN", new_y="NEXT")

            # ======== CONTENT ========
            pdf.set_left_margin(15)
            pdf.set_right_margin(15)

            # 1. Executive Summary
            pdf.add_page()
            pdf.stitle("1. Executive Summary")
            pdf.btext(d.summary_paragraph or f"Comprehensive analysis of {d.dataset_name}.")
            if d.kpis:
                pdf.ln(2)
                y0 = pdf.get_y()
                cw, ch, gap = 42, 18, 4
                for i, k in enumerate(d.kpis[:4]):
                    col = i % 4
                    row_i = i // 4
                    pdf.kpi(15 + col * (cw + gap), y0 + row_i * (ch + gap), cw, ch, k.get("title", "Metric"), k.get("value", "0"))
                pdf.set_y(y0 + ((len(d.kpis) - 1) // 4 + 1) * (ch + gap) + 4)

            # 2. Data Quality
            pdf.ln(6)
            pdf.stitle("2. Data Quality Assessment")
            qd = d.quality_detail
            if qd:
                qs = qd.get("quality_score", d.quality_score)
                pdf.btext(f"Overall Data Quality Score: {qs:.1f}/100. Missing data accounts for {d.missing_percentage:.2f}% of all cells. Duplicate rows: {qd.get('duplicate_rows', 0):,}.")
                missing = qd.get("missing_per_column", [])
                if missing:
                    pdf.ln(2)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(30, 41, 59)
                    pdf.cell(w=0, h=6, text="Columns with Missing Values:", new_x="LMARGIN", new_y="NEXT")
                    pdf.ln(2)
                    pdf.thead(["Column", "Missing Count", "Missing %"], [65, 55, 60])
                    for i, m in enumerate(missing[:15]):
                        pdf.trow([m["column"], f"{m['missing_count']:,}", f"{m['missing_pct']:.2f}%"], [65, 55, 60], zebra=(i % 2 == 1))
                type_issues = qd.get("type_issues", [])
                if type_issues:
                    pdf.ln(4)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(30, 41, 59)
                    pdf.cell(w=0, h=6, text="Data Type Issues:", new_x="LMARGIN", new_y="NEXT")
                    for ti in type_issues:
                        pdf.btext(f"  - {ti['column']}: {ti['issue']}")
            else:
                pdf.btext(f"Data quality score: {d.quality_score:.1f}/100. Missing data: {d.missing_percentage:.2f}%.")

            # 3. Descriptive Statistics
            pdf.add_page()
            pdf.stitle("3. Descriptive Statistics")
            ns = d.statistics.get("numeric_stats", [])
            if ns:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(30, 41, 59)
                pdf.cell(w=0, h=6, text=f"Numeric Columns ({len(ns)} features):", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
                pdf.thead(["Column", "Mean", "Std Dev", "Min", "Median", "Max", "Skewness"], [38, 22, 22, 22, 22, 22, 22])
                for i, s in enumerate(ns[:25]):
                    pdf.trow([s["column"], _fmt(s["mean"]), _fmt(s["std"]), _fmt(s["min"]), _fmt(s["median"]), _fmt(s["max"]), _fmt(s["skewness"])], [38, 22, 22, 22, 22, 22, 22], zebra=(i % 2 == 1))
            else:
                pdf.btext("No numeric columns found.")
            cs = d.statistics.get("categorical_stats", [])
            if cs:
                pdf.ln(6)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(30, 41, 59)
                pdf.cell(w=0, h=6, text=f"Categorical Columns ({len(cs)} features):", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
                pdf.thead(["Column", "Unique", "Top Value", "Top Count", "Top Freq"], [45, 30, 35, 30, 40])
                for i, c in enumerate(cs[:15]):
                    top = c.get("top_values", [{}])[0] if c.get("top_values") else {}
                    pdf.trow([c["column"], str(c.get("unique", 0)), str(top.get("value", "N/A"))[:25], str(top.get("count", 0)), f"{top.get('frequency', 0):.1f}%"], [45, 30, 35, 30, 40], zebra=(i % 2 == 1))

            # 4. Correlations
            pairs = d.correlations.get("top_pairs", []) if d.correlations else []
            if pairs:
                pdf.add_page()
                pdf.stitle("4. Correlation Analysis")
                pdf.btext(f"Identified {len(pairs)} strongly correlated feature pairs (|r| > 0.5).")
                pdf.ln(2)
                pdf.thead(["Feature A", "Feature B", "Correlation", "Strength"], [50, 50, 40, 40])
                for i, p in enumerate(pairs[:15]):
                    rv = abs(p.get("correlation", 0))
                    strength = "Strong" if rv > 0.8 else ("Moderate" if rv > 0.6 else "Weak")
                    pdf.trow([p["col_a"], p["col_b"], f"{p.get('correlation', 0):.4f}", strength], [50, 50, 40, 40], zebra=(i % 2 == 1))

            # 5. Outliers
            iqr = d.outliers.get("iqr_outliers", []) if d.outliers else []
            if iqr:
                pdf.ln(6)
                pdf.stitle("5. Outlier Detection")
                pdf.btext(f"IQR Method: Detected outliers in {len(iqr)} columns.")
                pdf.ln(2)
                pdf.thead(["Column", "Count", "Outlier %", "Lower Bound", "Upper Bound"], [45, 30, 30, 35, 40])
                for i, o in enumerate(iqr[:15]):
                    pdf.trow([o["column"], str(o.get("count", 0)), f"{o.get('percentage', 0):.1f}%", _fmt(o.get("lower_bound")), _fmt(o.get("upper_bound"))], [45, 30, 30, 35, 40], zebra=(i % 2 == 1))

            # 6. Trends
            if d.trends:
                pdf.add_page()
                pdf.stitle("6. AI Trend Analysis")
                pdf.btext(f"Linear trend analysis identified {len(d.trends)} column trajectories.")
                pdf.ln(2)
                pdf.thead(["Column", "Direction", "R2", "Change %", "Summary"], [40, 28, 28, 28, 56])
                for i, t in enumerate(d.trends[:12]):
                    pdf.trow([t.column, t.direction.value.upper(), f"{t.r2_score:.3f}", f"{t.pct_change:+.1f}%", t.summary_text[:60]], [40, 28, 28, 28, 56], zebra=(i % 2 == 1))

            # 7. Anomalies
            if d.anomalies and d.anomalies.anomalous_rows_count > 0:
                pdf.ln(6)
                pdf.stitle("7. Anomaly Assessment")
                anom = d.anomalies
                pdf.btext(f"Ensemble detection identified {anom.anomalous_rows_count:,} anomalous rows ({anom.anomaly_percentage:.1f}% of total).")
                pdf.ln(2)
                for item in anom.detected_anomalies[:8]:
                    pdf.btext(f"  - Row #{item.row_index} | '{item.column}' = {item.value}: {item.reason}")

            # 8. ML Models
            if d.ml_models:
                pdf.add_page()
                pdf.stitle("8. ML Model Performance")
                pdf.btext(f"{len(d.ml_models)} trained model(s) evaluated.")
                pdf.ln(2)
                for m in d.ml_models:
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(15, 23, 42)
                    pdf.cell(w=0, h=6, text=_clean(f"{m['model_name']} ({m['algorithm']}) - {m.get('problem_type', '').title()}"), new_x="LMARGIN", new_y="NEXT")
                    metrics = m.get("metrics", {})
                    if metrics:
                        pdf.set_font("Helvetica", "", 9)
                        pdf.set_text_color(51, 65, 85)
                        mstr = " | ".join([f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}" for k, v in metrics.items()])
                        pdf.multi_cell(w=0, h=5, text=_clean(mstr))
                    pdf.ln(4)

            # 9. Recommendations
            if d.recommendations:
                pdf.add_page()
                pdf.stitle("9. Strategic Recommendations")
                for idx, r in enumerate(d.recommendations, 1):
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(15, 23, 42)
                    pdf.cell(w=0, h=6, text=_clean(f"{idx}. [{r.impact.value.upper()}] {r.title} ({r.category})"), new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", "", 9.5)
                    pdf.set_text_color(51, 65, 85)
                    pdf.multi_cell(w=0, h=5, text=_clean(r.description))
                    if r.action_items:
                        for action in r.action_items:
                            pdf.set_font("Helvetica", "", 9)
                            pdf.set_x(pdf.l_margin + 5)
                            pdf.multi_cell(w=pdf.epw - 5, h=5, text=_clean(f"- {action}"))
                    pdf.ln(4)

            # 10. Root Causes
            if d.root_causes:
                pdf.ln(4)
                pdf.stitle("10. Root Cause Drivers")
                for rc in d.root_causes[:6]:
                    pdf.btext(f"- {rc.feature} ({rc.condition}): {rc.description} [Impact: {rc.impact_score:.2f}, Affected: {rc.affected_percentage:.1f}%]")

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            pdf.output(output_path)
            return output_path
        except Exception as e:
            print(f"[PDFGenerator] Error: {e}")
            import traceback
            traceback.print_exc()
            return None
