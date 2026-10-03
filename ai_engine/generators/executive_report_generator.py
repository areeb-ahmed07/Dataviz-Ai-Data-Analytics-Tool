"""
Executive Report Generator - produces C-Suite Executive Summaries in Markdown and HTML.

Consumes ExecutiveReportData enriched with real analysis results by ReportService.
Includes: KPIs, quality assessment, statistics tables, correlations,
outlier detection, ML model performance, trends, anomalies, and recommendations.

Single Responsibility: converts ExecutiveReportData into Markdown and HTML documents.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ai_engine.domain.entities import ExecutiveReportData


class ExecutiveReportGenerator:
    """
    Generates comprehensive reports formatted as Markdown and responsive HTML.
    """

    def __init__(self, data: ExecutiveReportData) -> None:
        self._data = data

    # ────────────────────────────────────────────────────────────────
    # MARKDOWN GENERATOR
    # ────────────────────────────────────────────────────────────────

    def generate_markdown(self) -> str:
        """Generate structured Markdown report with all analysis sections."""
        d = self._data
        lines = [
            f"# {d.title}",
            f"**Generated:** {d.generated_at.strftime('%Y-%m-%d %H:%M:%S')}  |  **Dataset:** `{d.dataset_name}` ({d.dataset_shape[0]:,} rows x {d.dataset_shape[1]} cols)",
            "---",
            "## 1. Executive Summary",
            d.summary_paragraph or f"Comprehensive analysis of `{d.dataset_name}`. Quality Score: {d.quality_score:.1f}/100.",
            "",
        ]

        # KPIs
        if d.kpis:
            lines.append("## 2. Key Performance Indicators")
            lines.append("| Metric | Value | Status |")
            lines.append("|---|---|---|")
            for kpi in d.kpis:
                status_icon = "OK" if kpi.get("status") == "OK" else "WARNING"
                lines.append(f"| {kpi.get('title', 'N/A')} | {kpi.get('value', '0')} | {status_icon} |")
            lines.append("")

        # Data Quality
        qd = d.quality_detail
        if qd:
            lines.append("## 3. Data Quality Assessment")
            lines.append(f"**Quality Score:** {qd.get('quality_score', d.quality_score):.1f}/100")
            lines.append(f"**Missing Data:** {d.missing_percentage:.2f}% across all cells")
            lines.append(f"**Duplicate Rows:** {qd.get('duplicate_rows', 0):,}")
            missing = qd.get("missing_per_column", [])
            if missing:
                lines.append("")
                lines.append("| Column | Missing Count | Missing % |")
                lines.append("|---|---|---|")
                for m in missing:
                    lines.append(f"| {m['column']} | {m['missing_count']:,} | {m['missing_pct']:.2f}% |")
            lines.append("")

        # Descriptive Statistics
        stats = d.statistics
        numeric_stats = stats.get("numeric_stats", [])
        if numeric_stats:
            lines.append("## 4. Descriptive Statistics")
            lines.append(f"### Numeric Columns ({len(numeric_stats)} features)")
            lines.append("| Column | Mean | Std Dev | Min | Median | Max | Skewness |")
            lines.append("|---|---|---|---|---|---|---|")
            for ns in numeric_stats:
                lines.append(f"| {ns['column']} | {ns['mean']:.4f} | {ns['std']:.4f} | {ns['min']:.4f} | {ns['median']:.4f} | {ns['max']:.4f} | {ns['skewness']:.4f} |")
            lines.append("")

        cat_stats = stats.get("categorical_stats", [])
        if cat_stats:
            lines.append(f"### Categorical Columns ({len(cat_stats)} features)")
            lines.append("| Column | Unique | Top Value | Top Frequency |")
            lines.append("|---|---|---|---|")
            for cs in cat_stats:
                top = cs.get("top_values", [{}])[0] if cs.get("top_values") else {}
                lines.append(f"| {cs['column']} | {cs.get('unique', 0)} | {top.get('value', 'N/A')} | {top.get('frequency', 0):.1f}% |")
            lines.append("")

        # Correlations
        corr = d.correlations
        top_pairs = corr.get("top_pairs", []) if corr else []
        if top_pairs:
            lines.append("## 5. Correlation Analysis")
            lines.append("| Feature A | Feature B | Correlation | Strength |")
            lines.append("|---|---|---|---|")
            for p in top_pairs:
                r_val = abs(p.get("correlation", 0))
                strength = "Strong" if r_val > 0.8 else ("Moderate" if r_val > 0.6 else "Weak")
                lines.append(f"| {p['col_a']} | {p['col_b']} | {p.get('correlation', 0):.4f} | {strength} |")
            lines.append("")

        # Outliers
        outlier_data = d.outliers
        if outlier_data:
            iqr_outliers = outlier_data.get("iqr_outliers", [])
            if iqr_outliers:
                lines.append("## 6. Outlier Detection (IQR Method)")
                lines.append("| Column | Outlier Count | Outlier % | Lower Bound | Upper Bound |")
                lines.append("|---|---|---|---|---|")
                for o in iqr_outliers:
                    lines.append(f"| {o['column']} | {o.get('count', 0)} | {o.get('percentage', 0):.1f}% | {o.get('lower_bound', 0):.4f} | {o.get('upper_bound', 0):.4f} |")
                lines.append("")

        # Trends
        if d.trends:
            lines.append("## 7. AI Trend Analysis")
            for t in d.trends:
                lines.append(f"- **{t.column}** ({t.direction.value}): {t.summary_text} (R2={t.r2_score:.3f}, Change={t.pct_change:+.1f}%)")
            lines.append("")

        # Anomalies
        if d.anomalies and d.anomalies.anomalous_rows_count > 0:
            lines.append("## 8. Anomaly Assessment")
            lines.append(f"Detected {d.anomalies.anomalous_rows_count:,} anomalous rows ({d.anomalies.anomaly_percentage:.1f}%).")
            for item in d.anomalies.detected_anomalies[:10]:
                lines.append(f"- Row #{item.row_index} | '{item.column}' = {item.value}: {item.reason}")
            lines.append("")

        # ML Models
        if d.ml_models:
            lines.append("## 9. ML Model Performance")
            for m in d.ml_models:
                lines.append(f"### {m['model_name']} ({m['algorithm']})")
                lines.append(f"Problem Type: {m.get('problem_type', 'N/A')}")
                metrics = m.get("metrics", {})
                if metrics:
                    lines.append("| Metric | Value |")
                    lines.append("|---|---|")
                    for k, v in metrics.items():
                        val = f"{v:.4f}" if isinstance(v, float) else str(v)
                        lines.append(f"| {k} | {val} |")
                lines.append("")

        # Root Causes
        if d.root_causes:
            lines.append("## 10. Root Cause Drivers")
            for rc in d.root_causes:
                lines.append(f"- **{rc.feature}** ({rc.condition}): {rc.description} [Impact: {rc.impact_score:.2f}, Affected: {rc.affected_percentage:.1f}%]")
            lines.append("")

        # Recommendations
        if d.recommendations:
            lines.append("## 11. Strategic Recommendations")
            for idx, r in enumerate(d.recommendations, 1):
                lines.append(f"### {idx}. [{r.impact.value.upper()}] {r.title} ({r.category})")
                lines.append(r.description)
                if r.action_items:
                    for a in r.action_items:
                        lines.append(f"  - {a}")
                lines.append("")

        return "\n".join(lines)

    # ────────────────────────────────────────────────────────────────
    # HTML GENERATOR
    # ────────────────────────────────────────────────────────────────

    def generate_html(self) -> str:
        """Generate a standalone, responsive HTML report."""
        d = self._data
        html = self._html_head(d.title)
        html += self._html_cover(d)
        html += self._html_kpis(d)
        html += self._html_quality(d)
        html += self._html_statistics(d)
        html += self._html_correlations(d)
        html += self._html_outliers(d)
        html += self._html_trends(d)
        html += self._html_anomalies(d)
        html += self._html_ml_models(d)
        html += self._html_root_causes(d)
        html += self._html_recommendations(d)
        html += self._html_footer(d)
        return html

    def _html_head(self, title: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{ --primary: #4F46E5; --dark: #0F172A; --text: #1E293B; --muted: #64748B; --border: #E2E8F0; --surface: #F8FAFC; --white: #FFFFFF; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--text); line-height: 1.6; background: var(--surface); }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 2rem; }}
.cover {{ background: var(--dark); color: var(--white); padding: 3rem 2rem; border-radius: 12px; margin-bottom: 2rem; }}
.cover h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
.cover .meta {{ color: #94A3B8; font-size: 0.9rem; margin-top: 1rem; }}
.section {{ background: var(--white); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.section h2 {{ color: var(--primary); font-size: 1.2rem; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--border); }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; margin-top: 1rem; }}
.kpi-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; text-align: center; }}
.kpi-card .value {{ font-size: 1.6rem; font-weight: 700; color: var(--primary); }}
.kpi-card .label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.25rem; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 0.75rem; font-size: 0.85rem; }}
thead th {{ background: var(--dark); color: var(--white); padding: 0.5rem 0.75rem; text-align: left; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; }}
tbody td {{ padding: 0.45rem 0.75rem; border-bottom: 1px solid var(--border); }}
tbody tr:nth-child(even) {{ background: var(--surface); }}
.badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 9999px; font-size: 0.7rem; font-weight: 600; }}
.badge-high {{ background: #FEE2E2; color: #991B1B; }}
.badge-medium {{ background: #FEF3C7; color: #92400E; }}
.badge-low {{ background: #DCFCE7; color: #065F46; }}
.badge-ok {{ background: #DCFCE7; color: #065F46; }}
.badge-warning {{ background: #FEF3C7; color: #92400E; }}
.rec-card {{ background: var(--surface); border-left: 4px solid var(--primary); padding: 1rem; margin-bottom: 1rem; border-radius: 0 8px 8px 0; }}
.rec-card.high {{ border-left-color: #EF4444; }}
.rec-card.medium {{ border-left-color: #F59E0B; }}
.rec-card.low {{ border-left-color: #22C55E; }}
.rec-card h3 {{ font-size: 0.95rem; margin-bottom: 0.25rem; }}
.rec-card p {{ font-size: 0.85rem; color: var(--muted); }}
.rec-card ul {{ margin-top: 0.5rem; padding-left: 1.25rem; font-size: 0.85rem; }}
.summary-text {{ font-size: 0.95rem; color: var(--text); line-height: 1.7; }}
.empty {{ color: var(--muted); font-style: italic; padding: 1rem; text-align: center; }}
.footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 2rem; padding: 1rem; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<div class="container">
"""

    def _html_cover(self, d: ExecutiveReportData) -> str:
        return f"""<div class="cover">
<h1>{d.title}</h1>
<p style="font-size:1.05rem; color:#CBD5E1;">Comprehensive data analytics report with statistical profiling, quality assessment, correlation analysis, outlier detection, ML model evaluation, and AI-generated strategic recommendations.</p>
<div class="meta">
<p><strong>Dataset:</strong> {d.dataset_name} &nbsp;|&nbsp; <strong>Dimensions:</strong> {d.dataset_shape[0]:,} rows x {d.dataset_shape[1]} cols &nbsp;|&nbsp; <strong>Quality Score:</strong> {d.quality_score:.1f}/100</p>
<p><strong>Generated:</strong> {d.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>
</div>"""

    def _html_kpis(self, d: ExecutiveReportData) -> str:
        if not d.kpis:
            return ""
        cards = "".join(
            f'<div class="kpi-card"><div class="value">{k.get("value", "0")}</div><div class="label">{k.get("title", "")}</div></div>'
            for k in d.kpis
        )
        return f'<div class="section"><h2>Key Performance Indicators</h2><div class="kpi-grid">{cards}</div></div>'

    def _html_quality(self, d: ExecutiveReportData) -> str:
        qd = d.quality_detail
        if not qd:
            return ""

        missing = qd.get("missing_per_column", [])
        missing_rows = "".join(
            f"<tr><td>{m['column']}</td><td>{m['missing_count']:,}</td><td>{m['missing_pct']:.2f}%</td></tr>"
            for m in missing
        )
        missing_table = ""
        if missing:
            missing_table = (
                '<h3 style="margin-top:1rem;font-size:0.95rem">Missing Values by Column</h3>'
                '<table><thead><tr><th>Column</th><th>Missing Count</th><th>Missing %</th></tr></thead><tbody>'
                f"{missing_rows}"
                '</tbody></table>'
            )

        type_issues = qd.get("type_issues", [])
        type_rows = "".join(
            f"<tr><td>{ti['column']}</td><td>{ti['issue']}</td></tr>"
            for ti in type_issues
        )
        type_table = ""
        if type_issues:
            type_table = (
                '<h3 style="margin-top:1rem;font-size:0.95rem">Data Type Issues</h3>'
                '<table><thead><tr><th>Column</th><th>Issue</th></tr></thead><tbody>'
                f"{type_rows}"
                '</tbody></table>'
            )

        return f'''<div class="section">
<h2>Data Quality Assessment</h2>
<p class="summary-text">Quality Score: <strong>{qd.get("quality_score", d.quality_score):.1f}/100</strong> | Missing: <strong>{d.missing_percentage:.2f}%</strong> | Duplicates: <strong>{qd.get("duplicate_rows", 0):,}</strong></p>
{missing_table}{type_table}
</div>'''

    def _html_statistics(self, d: ExecutiveReportData) -> str:
        stats = d.statistics
        ns = stats.get("numeric_stats", [])
        cs = stats.get("categorical_stats", [])
        if not ns and not cs:
            return ""

        ns_rows = "".join(
            f"<tr><td>{s['column']}</td><td>{s['mean']:.4f}</td><td>{s['std']:.4f}</td><td>{s['min']:.4f}</td><td>{s['median']:.4f}</td><td>{s['max']:.4f}</td><td>{s['skewness']:.4f}</td></tr>"
            for s in ns
        )
        cs_rows = "".join(
            f"<tr><td>{c['column']}</td><td>{c.get('unique',0)}</td><td>{top.get('value','N/A')}</td><td>{top.get('frequency',0):.1f}%</td></tr>"
            for c in cs for top in [c.get("top_values", [{}])[0] if c.get("top_values") else {}]
        )

        numeric_table = ""
        if ns:
            numeric_table = (
                f'<h3 style="margin-bottom:0.5rem;font-size:0.95rem">Numeric Columns ({len(ns)} features)</h3>'
                '<table><thead><tr><th>Column</th><th>Mean</th><th>Std Dev</th><th>Min</th><th>Median</th><th>Max</th><th>Skewness</th></tr></thead><tbody>'
                f"{ns_rows}"
                '</tbody></table>'
            )

        categorical_table = ""
        if cs:
            categorical_table = (
                f'<h3 style="margin-top:1.5rem;margin-bottom:0.5rem;font-size:0.95rem">Categorical Columns ({len(cs)} features)</h3>'
                '<table><thead><tr><th>Column</th><th>Unique</th><th>Top Value</th><th>Top Freq</th></tr></thead><tbody>'
                f"{cs_rows}"
                '</tbody></table>'
            )

        return f'''<div class="section">
<h2>Descriptive Statistics</h2>
{numeric_table}{categorical_table}
</div>'''

    def _html_correlations(self, d: ExecutiveReportData) -> str:
        pairs = d.correlations.get("top_pairs", []) if d.correlations else []
        if not pairs:
            return ""
        rows = "".join(
            f"<tr><td>{p['col_a']}</td><td>{p['col_b']}</td><td>{p.get('correlation',0):.4f}</td><td><span class=\"badge badge-{'high' if abs(p.get('correlation',0))>0.8 else 'medium'}\">{'Strong' if abs(p.get('correlation',0))>0.8 else 'Moderate'}</span></td></tr>"
            for p in pairs
        )
        return f'''<div class="section">
<h2>Correlation Analysis</h2>
<p class="summary-text">{len(pairs)} strongly correlated feature pairs identified (|r| > 0.5).</p>
<table><thead><tr><th>Feature A</th><th>Feature B</th><th>Correlation</th><th>Strength</th></tr></thead><tbody>{rows}</tbody></table>
</div>'''

    def _html_outliers(self, d: ExecutiveReportData) -> str:
        iqr = d.outliers.get("iqr_outliers", []) if d.outliers else []
        if not iqr:
            return ""
        rows = "".join(
            f"<tr><td>{o['column']}</td><td>{o.get('count',0)}</td><td>{o.get('percentage',0):.1f}%</td><td>{o.get('lower_bound',0):.4f}</td><td>{o.get('upper_bound',0):.4f}</td></tr>"
            for o in iqr
        )
        return f'''<div class="section">
<h2>Outlier Detection</h2>
<table><thead><tr><th>Column</th><th>Outlier Count</th><th>Outlier %</th><th>Lower Bound</th><th>Upper Bound</th></tr></thead><tbody>{rows}</tbody></table>
</div>'''

    def _html_trends(self, d: ExecutiveReportData) -> str:
        if not d.trends:
            return ""
        items = "".join(
            f"<tr><td>{t.column}</td><td><span class=\"badge badge-{t.direction.value}\">{t.direction.value.upper()}</span></td><td>{t.r2_score:.3f}</td><td>{t.pct_change:+.1f}%</td><td>{t.summary_text}</td></tr>"
            for t in d.trends
        )
        return f'''<div class="section">
<h2>AI Trend Analysis</h2>
<table><thead><tr><th>Column</th><th>Direction</th><th>R2</th><th>Change</th><th>Summary</th></tr></thead><tbody>{items}</tbody></table>
</div>'''

    def _html_anomalies(self, d: ExecutiveReportData) -> str:
        if not d.anomalies or d.anomalies.anomalous_rows_count == 0:
            return ""
        items = "".join(
            f"<tr><td>#{item.row_index}</td><td>{item.column}</td><td>{item.value}</td><td>{item.reason}</td></tr>"
            for item in d.anomalies.detected_anomalies[:10]
        )
        return f'''<div class="section">
<h2>Anomaly Assessment</h2>
<p class="summary-text">{d.anomalies.anomalous_rows_count:,} anomalous rows detected ({d.anomalies.anomaly_percentage:.1f}%).</p>
<table><thead><tr><th>Row</th><th>Column</th><th>Value</th><th>Reason</th></tr></thead><tbody>{items}</tbody></table>
</div>'''

    def _html_ml_models(self, d: ExecutiveReportData) -> str:
        if not d.ml_models:
            return ""

        model_cards = []
        for m in d.ml_models:
            metrics_html = ""
            metrics = m.get("metrics", {})
            if metrics:
                metric_rows = "".join(
                    f"<tr><td>{k}</td><td>{v:.4f}</td></tr>"
                    for k, v in metrics.items()
                    if isinstance(v, (int, float))
                )
                metrics_html = (
                    '<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>'
                    f"{metric_rows}"
                    '</tbody></table>'
                )

            model_cards.append(
                f'''<div class="section" style="margin-bottom:1rem;">
<h3 style="color:var(--dark);font-size:0.95rem;">{m['model_name']} <span style="color:var(--muted);font-weight:normal;">({m['algorithm']})</span></h3>
<p style="font-size:0.85rem;color:var(--muted);">Problem Type: {m.get('problem_type', 'N/A')}</p>
{metrics_html}
</div>'''
            )

        return f'<div class="section"><h2>ML Model Performance</h2>{"".join(model_cards)}</div>'

    def _html_root_causes(self, d: ExecutiveReportData) -> str:
        if not d.root_causes:
            return ""
        items = "".join(
            f"<tr><td>{rc.feature}</td><td>{rc.condition}</td><td>{rc.impact_score:.2f}</td><td>{rc.affected_percentage:.1f}%</td><td>{rc.description}</td></tr>"
            for rc in d.root_causes
        )
        return f'''<div class="section">
<h2>Root Cause Drivers</h2>
<table><thead><tr><th>Feature</th><th>Condition</th><th>Impact</th><th>Affected</th><th>Description</th></tr></thead><tbody>{items}</tbody></table>
</div>'''

    def _html_recommendations(self, d: ExecutiveReportData) -> str:
        if not d.recommendations:
            return ""

        cards = []
        for r in d.recommendations:
            action_items_html = ""
            if r.action_items:
                action_items_html = (
                    '<ul>'
                    f"{''.join(f'<li>{a}</li>' for a in r.action_items)}"
                    '</ul>'
                )

            cards.append(
                f'''<div class="rec-card {r.impact.value}">
<h3>{r.title} <span class="badge badge-{r.impact.value}">{r.impact.value.upper()}</span> <span style="color:var(--muted);font-weight:normal;">| {r.category}</span></h3>
<p>{r.description}</p>
{action_items_html}
</div>'''
            )

        return f'<div class="section"><h2>Strategic Recommendations</h2>{"".join(cards)}</div>'

    def _html_footer(self, d: ExecutiveReportData) -> str:
        return f'''<div class="footer">
<p>DataViz Pro Analytics Report &mdash; Generated {d.generated_at.strftime("%Y-%m-%d %H:%M:%S")} &mdash; {d.dataset_name}</p>
</div>
</div>
</body>
</html>'''
