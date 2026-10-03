"""
Module 1: Advanced Data Quality Analysis
Additional Libraries: scikit-learn (already installed)
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from scipy.stats import ks_2samp
from datetime import datetime

class DataQualityAnalyzer:
    """Enhanced data quality checks and anomaly detection"""
    
    def __init__(self, df):
        self.df = df
        self.quality_report = {}
    
    def check_data_consistency(self):
        """Check for data consistency issues"""
        issues = []
        
        # Check for common value range problems
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            col_lower = col.lower()
            
            # Age checks
            if 'age' in col_lower:
                if (self.df[col] < 0).any():
                    issues.append(f"❌ Negative ages found in '{col}'")
                if (self.df[col] > 120).any():
                    issues.append(f"❌ Unrealistic ages (>120) found in '{col}'")
            
            # Price/Cost checks
            if any(term in col_lower for term in ['price', 'cost', 'salary', 'income']):
                if (self.df[col] < 0).any():
                    issues.append(f"❌ Negative values found in '{col}'")
            
            # Percentage checks
            if any(term in col_lower for term in ['percent', 'rate', 'ratio']):
                if (self.df[col] > 100).any():
                    issues.append(f"⚠️ Values > 100% found in '{col}'")
                if (self.df[col] < 0).any():
                    issues.append(f"❌ Negative percentages found in '{col}'")
        
        # Date consistency checks
        date_cols = self.df.select_dtypes(include=['datetime64']).columns
        for col in date_cols:
            if (self.df[col] > pd.Timestamp.now()).any():
                issues.append(f"⚠️ Future dates found in '{col}'")
        
        return issues
    
    def detect_anomalies(self, method='isolation_forest', contamination=0.1):
        """
        Detect anomalies using multiple methods
        
        Parameters:
        - method: 'isolation_forest' or 'lof'
        - contamination: Expected proportion of outliers
        """
        numeric_df = self.df.select_dtypes(include=[np.number]).dropna()
        
        if numeric_df.shape[1] == 0:
            return np.array([])
        
        if method == 'isolation_forest':
            detector = IsolationForest(
                contamination=contamination,
                random_state=42,
                n_jobs=-1
            )
            predictions = detector.fit_predict(numeric_df)
            # -1 for anomalies, 1 for normal
            return predictions == -1
            
        elif method == 'lof':
            detector = LocalOutlierFactor(
                contamination=contamination,
                n_jobs=-1
            )
            predictions = detector.fit_predict(numeric_df)
            return predictions == -1
        
        return np.array([])
    
    def check_data_drift(self, reference_df, significance_level=0.05):
        """
        Detect data drift between reference and current data
        Uses Kolmogorov-Smirnov test
        """
        drift_report = {}
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            if col in reference_df.columns:
                # Remove NaN values
                current_data = self.df[col].dropna()
                reference_data = reference_df[col].dropna()
                
                if len(current_data) > 0 and len(reference_data) > 0:
                    statistic, p_value = ks_2samp(reference_data, current_data)
                    drift_report[col] = {
                        'statistic': statistic,
                        'p_value': p_value,
                        'has_drift': p_value < significance_level,
                        'severity': 'High' if p_value < 0.01 else 
                                   'Medium' if p_value < 0.05 else 'Low'
                    }
        
        return drift_report
    
    def generate_data_quality_score(self):
        """Generate overall data quality score (0-100)"""
        score = 100
        
        # Deduct for missing values
        missing_percent = (self.df.isnull().sum().sum() / self.df.size) * 100
        score -= min(30, missing_percent * 2)
        
        # Deduct for duplicates
        duplicate_percent = (self.df.duplicated().sum() / len(self.df)) * 100
        score -= min(20, duplicate_percent * 2)
        
        # Deduct for anomalies
        anomalies = self.detect_anomalies()
        if len(anomalies) > 0:
            anomaly_percent = (anomalies.sum() / len(anomalies)) * 100
            score -= min(20, anomaly_percent)
        
        # Deduct for inconsistent data
        issues = self.check_data_consistency()
        score -= min(30, len(issues) * 5)
        
        return max(0, min(100, score))
    
    def get_quality_report(self):
        """Generate comprehensive quality report"""
        self.quality_report = {
            'quality_score': self.generate_data_quality_score(),
            'consistency_issues': self.check_data_consistency(),
            'anomalies_detected': self.detect_anomalies().sum() if len(self.detect_anomalies()) > 0 else 0,
            'missing_values': self.df.isnull().sum().to_dict(),
            'duplicate_rows': self.df.duplicated().sum(),
            'data_types': self.df.dtypes.astype(str).to_dict()
        }
        return self.quality_report