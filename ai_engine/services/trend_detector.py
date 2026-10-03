"""
Trend Detector Service — identifies directional trends, linear slopes, and change points.

Single Responsibility: analyzes numeric and time series columns for statistical trends.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from ai_engine.domain.entities import TrendResult
from ai_engine.domain.enums import TrendDirection


class TrendDetector:
    """
    Detects linear slope, R² goodness of fit, percentage change, and structural shift points.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df.copy()

    def detect_trends(
        self,
        columns: Optional[List[str]] = None,
        date_column: Optional[str] = None,
    ) -> List[TrendResult]:
        """
        Detect trends across all requested or inferred numeric columns.
        """
        if self._df.empty or len(self._df) < 5:
            return []

        numeric_cols = columns or self._df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            return []

        # Sort by date if date_column is present
        plot_df = self._df.copy()
        if date_column and date_column in plot_df.columns:
            try:
                plot_df[date_column] = pd.to_datetime(plot_df[date_column], errors="coerce")
                plot_df = plot_df.dropna(subset=[date_column]).sort_values(date_column)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        results: List[TrendResult] = []
        for col in numeric_cols[:10]:
            series = plot_df[col].dropna()
            if len(series) < 5:
                continue

            res = self._analyze_series_trend(col, series)
            if res:
                results.append(res)

        return results

    # ─── Private Trend Calculation ──────────────────────────────────────────

    def _analyze_series_trend(self, col_name: str, series: pd.Series) -> Optional[TrendResult]:
        try:
            n = len(series)
            x = np.arange(n)
            y = series.values.astype(float)

            mean_val = float(np.mean(y))
            std_val = float(np.std(y))

            # Linear regression: y = slope * x + intercept
            if n > 1 and np.var(x) > 0 and std_val > 0:
                slope, intercept = np.polyfit(x, y, 1)
                y_pred = slope * x + intercept
                ss_res = np.sum((y - y_pred) ** 2)
                ss_tot = np.sum((y - mean_val) ** 2)
                r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
            else:
                slope = 0.0
                r2 = 0.0

            # Percentage change (first vs last moving average)
            w = max(1, n // 10)
            start_val = series.iloc[:w].mean()
            end_val = series.iloc[-w:].mean()

            if start_val and start_val != 0:
                pct_change = float(((end_val - start_val) / abs(start_val)) * 100.0)
            else:
                pct_change = 0.0

            # Classify direction
            rel_slope = (slope * n) / abs(mean_val) if mean_val != 0 else slope
            if rel_slope > 0.05 and pct_change > 3.0:
                direction = TrendDirection.UPWARD
            elif rel_slope < -0.05 and pct_change < -3.0:
                direction = TrendDirection.DOWNWARD
            elif std_val / (abs(mean_val) + 1e-6) > 0.5:
                direction = TrendDirection.VOLATILE
            else:
                direction = TrendDirection.STABLE

            # Detect change points (structural mean shift)
            change_points = self._detect_change_points(series)

            # Generate natural language summary
            human_col = col_name.replace("_", " ").title()
            if direction == TrendDirection.UPWARD:
                summary = f"{human_col} demonstrates an upward trajectory (+{pct_change:.1f}% total shift, R²={r2:.2f})."
            elif direction == TrendDirection.DOWNWARD:
                summary = f"{human_col} shows a downward trend ({pct_change:.1f}% total shift, R²={r2:.2f})."
            elif direction == TrendDirection.VOLATILE:
                summary = f"{human_col} exhibits high volatility around mean {mean_val:,.2f} (std dev={std_val:,.2f})."
            else:
                summary = f"{human_col} remains stable around an average of {mean_val:,.2f}."

            return TrendResult(
                column=col_name,
                direction=direction,
                slope=float(slope),
                r2_score=max(0.0, min(1.0, r2)),
                pct_change=pct_change,
                mean_val=mean_val,
                std_val=std_val,
                change_points=change_points,
                summary_text=summary,
            )
        except Exception:
            return None

    def _detect_change_points(self, series: pd.Series) -> List[int]:
        """Detect indices where local mean shifts by more than 1.5 standard deviations."""
        try:
            n = len(series)
            if n < 20:
                return []

            window = max(5, n // 8)
            rolling_mean = series.rolling(window=window, min_periods=window).mean()
            diffs = rolling_mean.diff(window).abs()
            std_diff = diffs.std() or 1.0

            threshold = diffs.mean() + 1.8 * std_diff
            cp_indices = diffs[diffs > threshold].index.tolist()

            # Return raw row positions
            positions = [series.index.get_loc(idx) for idx in cp_indices if idx in series.index]
            return positions[:5]
        except Exception:
            return []
