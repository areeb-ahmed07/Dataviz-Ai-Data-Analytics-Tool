"""
Module 3: Natural Language Insights Generation
No additional libraries required (uses base Python)
"""

import pandas as pd
import numpy as np
from datetime import datetime


class NLGInsightsGenerator:
    """Generate natural language insights from analysis"""
    
    def __init__(self, analysis_results):
        self.results = analysis_results
        self.insights = []
        self.recommendations = []
    
    def generate_insights(self):
        """Generate human-readable insights from analysis results"""
        
        # Data quality insights
        if 'summary' in self.results:
            summary = self.results['summary']
            
            if isinstance(summary, dict):
                missing_pct = summary.get('missing_percentage', 0)
                if missing_pct > 10:
                    self.insights.append({
                        'type': 'warning',
                        'message': f"High missing data rate ({missing_pct:.1f}%). "
                                  f"Consider imputation strategies or collecting more complete data."
                    })
                
                duplicate_rows = summary.get('duplicate_rows', 0)
                if duplicate_rows > 0:
                    self.insights.append({
                        'type': 'info',
                        'message': f"Found {duplicate_rows:,} duplicate rows. "
                                  f"Review if these are legitimate or should be removed."
                    })
                
                # Dataset size insight
                shape = summary.get('dataset_shape', (0, 0))
                if shape[0] > 0:
                    self.insights.append({
                        'type': 'info',
                        'message': f"Dataset contains {shape[0]:,} rows and {shape[1]} columns."
                    })
        
        # Correlation insights
        if 'correlation' in self.results:
            corr_data = self.results['correlation']
            
            if isinstance(corr_data, dict):
                strong_corr = corr_data.get('strong_correlations', [])
                
                if strong_corr and len(strong_corr) > 0:
                    # Get top correlation
                    if isinstance(strong_corr, list):
                        top_corr = strong_corr[0]
                        if isinstance(top_corr, dict):
                            var1 = top_corr.get('var1', 'Variable1')
                            var2 = top_corr.get('var2', 'Variable2')
                            corr_value = top_corr.get('correlation', 0)
                            direction = "positively" if corr_value > 0 else "negatively"
                            
                            self.insights.append({
                                'type': 'insight',
                                'message': f"Strongest correlation: {var1} and {var2} "
                                          f"are {direction} correlated (r={corr_value:.2f})"
                            })
        
        # Feature importance insights
        if 'feature_importance' in self.results:
            feature_imp = self.results['feature_importance']
            
            # Check if it's a DataFrame and not empty
            if isinstance(feature_imp, pd.DataFrame) and not feature_imp.empty:
                # Check which column contains feature names
                if 'feature' in feature_imp.columns:
                    feature_col = 'feature'
                elif 'column_name' in feature_imp.columns:
                    feature_col = 'column_name'
                elif feature_imp.index.name == 'feature':
                    # Features are in the index
                    top_features = feature_imp.head(3).index.tolist()
                    feature_list = ', '.join([str(f) for f in top_features])
                    self.insights.append({
                        'type': 'insight',
                        'message': f"Top 3 most important features: {feature_list}"
                    })
                    # Skip the rest of feature importance processing
                    feature_col = None
                else:
                    # Use first column as feature names
                    feature_col = feature_imp.columns[0]
                
                if feature_col and feature_col in feature_imp.columns:
                    top_features = feature_imp.head(3)[feature_col].tolist()
                    feature_list = ', '.join([str(f) for f in top_features])
                    self.insights.append({
                        'type': 'insight',
                        'message': f"Top 3 most important features: {feature_list}"
                    })
        
        # Column analysis insights
        if 'column_analysis' in self.results:
            col_analysis = self.results['column_analysis']
            
            if isinstance(col_analysis, pd.DataFrame) and not col_analysis.empty:
                # Check for highly skewed columns
                if 'skewness' in col_analysis.columns and 'column_name' in col_analysis.columns:
                    numeric_cols = col_analysis[
                        col_analysis['data_type'] == 'numeric'
                    ] if 'data_type' in col_analysis.columns else col_analysis
                    
                    for _, col in numeric_cols.iterrows():
                        skew_val = col.get('skewness', 0)
                        if pd.notna(skew_val) and abs(skew_val) > 1:
                            direction = "right" if skew_val > 0 else "left"
                            col_name = col.get('column_name', 'Unknown')
                            self.insights.append({
                                'type': 'warning',
                                'message': f"{col_name} is highly skewed to the {direction} "
                                          f"(skewness={skew_val:.2f}). Consider transformation."
                            })
                            if len(self.insights) >= 10:  # Limit insights
                                break
        
        # Generate recommendations
        self._generate_recommendations()
        
        return self.insights, self.recommendations
    
    def _generate_recommendations(self):
        """Generate actionable recommendations based on insights"""
        
        # Check for data quality recommendations
        has_missing = any('missing' in str(i.get('message', '')).lower() for i in self.insights)
        has_duplicates = any('duplicate' in str(i.get('message', '')).lower() for i in self.insights)
        has_correlation = any('correlation' in str(i.get('message', '')).lower() for i in self.insights)
        has_skewed = any('skewed' in str(i.get('message', '')).lower() for i in self.insights)
        
        if has_missing:
            self.recommendations.append(
                "Implement missing data handling strategy (imputation, deletion, or collection)"
            )
        
        if has_duplicates:
            self.recommendations.append(
                "Review and remove duplicate records to ensure data quality"
            )
        
        if has_correlation:
            self.recommendations.append(
                "Consider feature engineering based on strong correlations found"
            )
        
        if has_skewed:
            self.recommendations.append(
                "Apply transformations (log, Box-Cox) to highly skewed features"
            )
        
        # General recommendations
        if not self.recommendations:
            self.recommendations.append(
                "Data looks clean! Proceed with modeling or deeper analysis."
            )
        
        self.recommendations.append(
            "Build predictive models using the most important features identified"
        )
        
        self.recommendations.append(
            "Set up automated monitoring for data quality and model performance"
        )
    
    def generate_executive_summary(self):
        """Generate an executive summary in markdown format"""
        
        summary = self.results.get('summary', {})
        
        if not isinstance(summary, dict):
            summary = {}
        
        shape = summary.get('dataset_shape', (0, 0))
        rows = shape[0] if isinstance(shape, (list, tuple)) else 0
        cols = shape[1] if isinstance(shape, (list, tuple)) and len(shape) > 1 else 0
        
        template = f"""
## 📊 Executive Summary

### Dataset Overview
- **Size**: {rows:,} rows × {cols:,} columns
- **Missing Data**: {summary.get('missing_percentage', 0):.1f}%
- **Duplicate Rows**: {summary.get('duplicate_rows', 0):,}
- **Memory Usage**: {summary.get('memory_usage', 0):.2f} MB

### Key Findings
"""
        
        if self.insights:
            for insight in self.insights[:5]:  # Top 5 insights
                icon = {
                    'warning': '⚠️',
                    'info': 'ℹ️',
                    'insight': '💡'
                }.get(insight.get('type', 'info'), '•')
                template += f"\n{icon} {insight['message']}"
        else:
            template += "\n✅ No significant issues found in the dataset."
        
        template += "\n\n### Recommended Actions\n"
        if self.recommendations:
            for i, rec in enumerate(self.recommendations[:5], 1):
                template += f"\n{i}. {rec}"
        else:
            template += "\nNo specific recommendations at this time."
        
        template += f"\n\n---\n*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        
        return template
    
    def to_dict(self):
        """Export insights to dictionary format"""
        return {
            'insights': self.insights,
            'recommendations': self.recommendations,
            'executive_summary': self.generate_executive_summary(),
            'generated_at': str(datetime.now()),
            'total_insights': len(self.insights),
            'total_recommendations': len(self.recommendations)
        }
    
    def to_json(self):
        """Export insights to JSON format"""
        import json
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def print_insights(self):
        """Print insights to console in a formatted way"""
        print("\n" + "="*60)
        print("📊 ANALYSIS INSIGHTS")
        print("="*60)
        
        if self.insights:
            print("\n🔍 Key Findings:")
            for i, insight in enumerate(self.insights, 1):
                icon = {
                    'warning': '⚠️',
                    'info': 'ℹ️',
                    'insight': '💡'
                }.get(insight.get('type', 'info'), '•')
                print(f"  {i}. {icon} {insight['message']}")
        else:
            print("\n✅ No significant insights found.")
        
        if self.recommendations:
            print("\n📋 Recommendations:")
            for i, rec in enumerate(self.recommendations, 1):
                print(f"  {i}. {rec}")
        
        print("\n" + "="*60)