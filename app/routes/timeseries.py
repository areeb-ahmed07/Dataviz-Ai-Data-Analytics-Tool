"""
DataViz Pro — Time Series Routes
"""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
import pandas as pd
import numpy as np

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService
from timeseries.ts_analyzer import TimeSeriesAnalyzer

timeseries_bp = Blueprint("timeseries", __name__, url_prefix="/time-series")


def _json_safe(value):
    """Convert pandas/NumPy values (including dictionary keys) to JSON types."""
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not np.isfinite(value):
            return None
        return value
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return value.isoformat()
    if value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(_json_safe(k)): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, np.ndarray, pd.Series)):
        return [_json_safe(v) for v in value]
    return str(value)

@timeseries_bp.route("/")
@login_required
def index():
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    return render_template("timeseries/index.html", datasets=datasets, active_page="time-series")

@timeseries_bp.route("/<int:dataset_id>/workspace")
@login_required
def workspace(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("timeseries.index"))
        
    return render_template("timeseries/analysis.html", dataset=dataset, active_page="time-series")

@timeseries_bp.route("/api/<int:dataset_id>/analyze", methods=["POST"])
@login_required
def api_analyze(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404
        
    data = request.json
    date_col = data.get("date_col")
    val_col = data.get("val_col")
    
    if not date_col or not val_col:
        return jsonify({"error": "Date and Value columns are required"}), 400
        
    df, error = DatasetService.load_dataframe(dataset.storage_path, dataset.file_format)
    if error or df is None:
        return jsonify({"error": error or "Failed to load dataset"}), 400
        
    if date_col not in df.columns or val_col not in df.columns:
        return jsonify({"error": "Selected columns do not exist in dataset"}), 400
        
    # Normalize user-selected columns before analysis. This prevents NumPy
    # scalar values and invalid dates from leaking into the JSON response.
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=[val_col, date_col]).sort_values(date_col)
    if len(df) < 3:
        return jsonify({"error": "The selected columns need at least 3 valid date/value rows."}), 400
    
    try:
        analyzer = TimeSeriesAnalyzer(df, date_column=date_col, value_column=val_col)
        
        # Keep one problematic analysis (for example a constant or very short
        # series) from breaking the whole response for the selected column.
        try:
            stationarity = analyzer.check_stationarity()
        except Exception as exc:
            stationarity = {"error": f"Stationarity analysis unavailable: {exc}"}
        try:
            seasonality = analyzer.detect_seasonality()
        except Exception as exc:
            seasonality = {"error": f"Seasonality analysis unavailable: {exc}"}
        try:
            forecast = analyzer.forecast_prophet(periods=30)
        except Exception as exc:
            forecast = {"error": f"Forecast unavailable: {exc}"}
        
        result = {
            "stationarity": stationarity,
            "seasonality": seasonality if "error" not in seasonality else None,
            "error_seasonality": seasonality.get("error") if "error" in seasonality else None,
        }
        
        # Format forecast for frontend
        if not isinstance(forecast, dict) or "error" not in forecast:
            forecast_df = forecast
            forecast_df['ds'] = forecast_df['ds'].astype(str)
            result["forecast"] = {
                "dates": forecast_df['ds'].tolist(),
                "yhat": forecast_df['yhat'].tolist(),
                "yhat_lower": forecast_df['yhat_lower'].tolist(),
                "yhat_upper": forecast_df['yhat_upper'].tolist(),
            }
        else:
            result["error_forecast"] = forecast.get("error")
            
        # Also return raw data for plotting
        result["raw"] = {
            "dates": df[date_col].astype(str).tolist(),
            "values": df[val_col].tolist()
        }
            
        return jsonify(_json_safe(result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
