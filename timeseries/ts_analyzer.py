"""
Module 4: Time Series Analysis
Additional Libraries: statsmodels, prophet
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import warnings

warnings.filterwarnings('ignore')

try:
    from statsmodels.tsa.seasonal import seasonal_decompose
    from statsmodels.tsa.stattools import adfuller, acf, pacf
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    print("⚠️ Statsmodels not installed. Install with: pip install statsmodels")

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    print("⚠️ Prophet not installed. Install with: pip install prophet")


class TimeSeriesAnalyzer:
    """Automated time series analysis"""
    
    def __init__(self, df, date_column, value_column):
        self.df = df.copy()
        self.date_col = date_column
        self.value_col = value_column
        
        # Ensure datetime
        if self.df[date_column].dtype != 'datetime64[ns]':
            self.df[date_column] = pd.to_datetime(self.df[date_column])
        
        # Sort by date
        self.df = self.df.sort_values(date_column)
    
    def check_stationarity(self):
        """Check if time series is stationary using Augmented Dickey-Fuller test"""
        if not STATSMODELS_AVAILABLE:
            return {"error": "Statsmodels not installed"}
        
        ts = self.df.set_index(self.date_col)[self.value_col].dropna()
        result = adfuller(ts)
        
        return {
            'test_statistic': result[0],
            'p_value': result[1],
            'critical_values': result[4],
            'is_stationary': result[1] < 0.05
        }
    
    def detect_seasonality(self):
        """Detect seasonal patterns"""
        if not STATSMODELS_AVAILABLE:
            return {"error": "Statsmodels not installed"}
        
        ts = self.df.set_index(self.date_col)[self.value_col].dropna()
        
        # Try to determine period automatically
        period = self._detect_period(ts)
        
        if period > 1 and len(ts) >= 2 * period:
            decomposition = seasonal_decompose(ts, model='additive', period=period)
            
            return {
                'trend': decomposition.trend.dropna().to_dict(),
                'seasonal': decomposition.seasonal.dropna().to_dict(),
                'residual': decomposition.resid.dropna().to_dict(),
                'detected_period': period
            }
        
        return {"error": "Could not detect seasonality or insufficient data"}
    
    def _detect_period(self, ts):
        """Automatically detect the seasonal period"""
        if not STATSMODELS_AVAILABLE:
            return 1
        
        # Calculate autocorrelation
        nlags = min(len(ts) // 2, 100)
        if nlags < 10:
            return 1
        
        autocorr = acf(ts.dropna(), nlags=nlags)
        
        # Find peaks in autocorrelation
        peaks, properties = signal.find_peaks(autocorr, height=0.1)
        
        if len(peaks) > 0:
            return peaks[0]
        return 1
    
    def forecast_prophet(self, periods=30):
        """Generate forecasts using Prophet"""
        if not PROPHET_AVAILABLE:
            return {"error": "Prophet not installed. Install with: pip install prophet"}
        
        # Prepare data for Prophet
        prophet_df = pd.DataFrame({
            'ds': self.df[self.date_col],
            'y': self.df[self.value_col]
        })
        
        # Fit Prophet model
        model = Prophet(
            yearly_seasonality='auto',
            weekly_seasonality='auto',
            daily_seasonality='auto'
        )
        model.fit(prophet_df)
        
        # Make future dataframe
        future = model.make_future_dataframe(periods=periods)
        forecast = model.predict(future)
        
        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(periods)
    
    def detect_anomalies_time_series(self, window=7, threshold=3):
        """Detect anomalies using rolling statistics"""
        ts = self.df.set_index(self.date_col)[self.value_col]
        
        # Calculate rolling statistics
        rolling_mean = ts.rolling(window=window).mean()
        rolling_std = ts.rolling(window=window).std()
        
        # Detect anomalies (values beyond threshold standard deviations)
        anomalies = np.abs(ts - rolling_mean) > (threshold * rolling_std)
        
        return anomalies