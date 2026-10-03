# Keep your original AutomatedDataAnalyzer class here
# This is the base class that other modules will enhance
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
import warnings
from datetime import datetime
import os
from typing import Dict, List, Tuple, Any
import json
import base64

warnings.filterwarnings('ignore')

class AutomatedDataAnalyzer:
    """
    An automated data analysis tool that performs comprehensive EDA,
    statistical analysis, and basic machine learning on any dataset.
    """
    
    def __init__(self, data_path: str, output_dir: str = "analysis_output"):
        """
        Initialize the analyzer with data path and output directory.
        
        Args:
            data_path: Path to CSV/Excel file
            output_dir: Directory to save analysis outputs
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Load data
        if data_path.endswith('.csv'):
            self.df = pd.read_csv(data_path)
        elif data_path.endswith(('.xlsx', '.xls')):
            self.df = pd.read_excel(data_path)
        else:
            raise ValueError("Unsupported file format. Use CSV or Excel.")
        
        self.original_df = self.df.copy()
        self.analysis_results = {}
        self.target_column = None

    def _image_to_base64(self, image_path: str) -> str:
        """Convert an image file to a base64-encoded data URI for embedding in HTML."""
        if not os.path.exists(image_path):
            return ""
        try:
            with open(image_path, 'rb') as f:
                img_data = f.read()
            b64 = base64.b64encode(img_data).decode('utf-8')
            return f"data:image/png;base64,{b64}"
        except Exception:
            return ""
    
    def auto_detect_target(self) -> str:
        """
        Automatically detect the target column for analysis.
        """
        # Look for common target column names
        target_names = ['target', 'label', 'class', 'y', 'output', 'result', 'outcome']
        
        for col in self.df.columns:
            if col.lower() in target_names:
                return col
        
        # If no common target name found, use the last column
        return self.df.columns[-1]
    
    def generate_data_summary(self) -> Dict:
        """
        Generate a comprehensive summary of the dataset.
        """
        summary = {
            'dataset_shape': self.df.shape,
            'total_cells': self.df.size,
            'missing_cells': self.df.isnull().sum().sum(),
            'missing_percentage': (self.df.isnull().sum().sum() / self.df.size) * 100,
            'duplicate_rows': self.df.duplicated().sum(),
            'memory_usage': self.df.memory_usage(deep=True).sum() / 1024**2,  # in MB
            'numeric_columns': len(self.df.select_dtypes(include=[np.number]).columns),
            'categorical_columns': len(self.df.select_dtypes(include=['object']).columns),
            'datetime_columns': len(self.df.select_dtypes(include=['datetime64']).columns),
        }
        
        self.analysis_results['summary'] = summary
        return summary
    
    def analyze_column_types(self) -> pd.DataFrame:
        """
        Analyze and classify each column's data type and characteristics.
        """
        col_analysis = []
        
        for col in self.df.columns:
            col_info = {
                'column_name': col,
                'dtype': str(self.df[col].dtype),
                'unique_values': self.df[col].nunique(),
                'missing_values': self.df[col].isnull().sum(),
                'missing_percentage': (self.df[col].isnull().sum() / len(self.df)) * 100,
                'is_unique': self.df[col].is_unique,
            }
            
            if pd.api.types.is_numeric_dtype(self.df[col]):
                col_info.update({
                    'data_type': 'numeric',
                    'mean': self.df[col].mean(),
                    'median': self.df[col].median(),
                    'std': self.df[col].std(),
                    'min': self.df[col].min(),
                    'max': self.df[col].max(),
                    'skewness': self.df[col].skew(),
                    'kurtosis': self.df[col].kurtosis(),
                    'zeros_percentage': (self.df[col] == 0).sum() / len(self.df) * 100
                })
            elif pd.api.types.is_object_dtype(self.df[col]):
                col_info.update({
                    'data_type': 'categorical',
                    'top_value': self.df[col].mode().iloc[0] if not self.df[col].mode().empty else None,
                    'top_frequency': self.df[col].value_counts().iloc[0] if not self.df[col].value_counts().empty else 0
                })
            elif pd.api.types.is_datetime64_any_dtype(self.df[col]):
                col_info.update({
                    'data_type': 'datetime',
                    'date_range_start': self.df[col].min(),
                    'date_range_end': self.df[col].max()
                })
            
            col_analysis.append(col_info)
        
        result_df = pd.DataFrame(col_analysis)
        self.analysis_results['column_analysis'] = result_df
        return result_df
    
    def perform_correlation_analysis(self) -> Tuple[pd.DataFrame, str]:
        """
        Perform correlation analysis and create a heatmap.
        """
        numeric_df = self.df.select_dtypes(include=[np.number])
        
        if len(numeric_df.columns) < 2:
            return pd.DataFrame(), "Insufficient numeric columns for correlation analysis"
        
        # Calculate correlation matrix
        corr_matrix = numeric_df.corr()
        
        # Create correlation heatmap
        plt.figure(figsize=(12, 10))
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        sns.heatmap(corr_matrix, mask=mask, annot=True, cmap='coolwarm', 
                   center=0, square=True, linewidths=0.5, fmt='.2f')
        plt.title('Correlation Matrix Heatmap')
        plt.tight_layout()
        
        heatmap_path = os.path.join(self.output_dir, 'correlation_heatmap.png')
        plt.savefig(heatmap_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Find strong correlations
        strong_correlations = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                if abs(corr_matrix.iloc[i, j]) > 0.7:
                    strong_correlations.append({
                        'var1': corr_matrix.columns[i],
                        'var2': corr_matrix.columns[j],
                        'correlation': corr_matrix.iloc[i, j]
                    })
        
        self.analysis_results['correlation'] = {
            'matrix': corr_matrix,
            'strong_correlations': strong_correlations
        }
        
        return corr_matrix, heatmap_path
    
    def perform_statistical_tests(self) -> Dict:
        """
        Perform various statistical tests on the data.
        """
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        categorical_cols = self.df.select_dtypes(include=['object']).columns
        
        test_results = {
            'normality_tests': {},
            'outlier_detection': {}
        }
        
        # Normality tests for numeric columns
        for col in numeric_cols[:5]:  # Limit to first 5 columns to avoid overload
            data = self.df[col].dropna()
            if len(data) >= 8:  # Minimum sample size for normality test
                statistic, p_value = stats.normaltest(data)
                test_results['normality_tests'][col] = {
                    'statistic': statistic,
                    'p_value': p_value,
                    'is_normal': p_value > 0.05
                }
        
        # Outlier detection using IQR method
        for col in numeric_cols[:5]:
            Q1 = self.df[col].quantile(0.25)
            Q3 = self.df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            outliers = self.df[(self.df[col] < lower_bound) | (self.df[col] > upper_bound)][col]
            
            test_results['outlier_detection'][col] = {
                'lower_bound': lower_bound,
                'upper_bound': upper_bound,
                'outlier_count': len(outliers),
                'outlier_percentage': (len(outliers) / len(self.df)) * 100
            }
        
        self.analysis_results['statistical_tests'] = test_results
        return test_results
    
    def create_distribution_plots(self) -> List[str]:
        """
        Create distribution plots for numeric columns.
        """
        plot_paths = []
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns[:6]
        
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        axes = axes.flatten()
        
        for idx, col in enumerate(numeric_cols):
            if idx < 6:
                ax = axes[idx]
                self.df[col].dropna().hist(bins=30, ax=ax, edgecolor='black')
                ax.set_title(f'Distribution of {col}')
                ax.set_xlabel(col)
                ax.set_ylabel('Frequency')
        
        # Remove empty subplots
        for idx in range(len(numeric_cols), 6):
            fig.delaxes(axes[idx])
        
        plt.suptitle('Distribution Plots of Numeric Variables', size=16)
        plt.tight_layout()
        
        plot_path = os.path.join(self.output_dir, 'distribution_plots.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        plot_paths.append(plot_path)
        return plot_paths
    
    def create_box_plots(self) -> List[str]:
        """
        Create box plots for numeric columns to visualize outliers.
        """
        plot_paths = []
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns[:6]
        
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        axes = axes.flatten()
        
        for idx, col in enumerate(numeric_cols):
            if idx < 6:
                ax = axes[idx]
                self.df.boxplot(column=col, ax=ax)
                ax.set_title(f'Box Plot of {col}')
                ax.set_ylabel(col)
        
        # Remove empty subplots
        for idx in range(len(numeric_cols), 6):
            fig.delaxes(axes[idx])
        
        plt.suptitle('Box Plots Showing Data Distribution and Outliers', size=16)
        plt.tight_layout()
        
        plot_path = os.path.join(self.output_dir, 'box_plots.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        plot_paths.append(plot_path)
        return plot_paths
    
    def perform_pca_analysis(self) -> Tuple[pd.DataFrame, str]:
        """
        Perform PCA analysis for dimensionality reduction visualization.
        """
        numeric_df = self.df.select_dtypes(include=[np.number]).dropna()
        
        if numeric_df.shape[1] < 2:
            return pd.DataFrame(), "Insufficient numeric columns for PCA"
        
        # Standardize the features
        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(numeric_df)
        
        # Apply PCA
        pca = PCA()
        pca_result = pca.fit_transform(scaled_data)
        
        # Calculate explained variance
        explained_variance = pd.DataFrame({
            'PC': [f'PC{i+1}' for i in range(len(pca.explained_variance_ratio_))],
            'Explained_Variance_Ratio': pca.explained_variance_ratio_,
            'Cumulative_Variance': np.cumsum(pca.explained_variance_ratio_)
        })
        
        # Create scree plot
        plt.figure(figsize=(10, 6))
        plt.plot(range(1, len(pca.explained_variance_ratio_) + 1), 
                np.cumsum(pca.explained_variance_ratio_), 'bo-')
        plt.xlabel('Number of Components')
        plt.ylabel('Cumulative Explained Variance')
        plt.title('PCA - Explained Variance Ratio')
        plt.grid(True)
        
        pca_path = os.path.join(self.output_dir, 'pca_analysis.png')
        plt.savefig(pca_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.analysis_results['pca'] = explained_variance
        
        return explained_variance, pca_path
    
    def feature_importance_analysis(self, target_column: str) -> Tuple[pd.DataFrame, str]:
        """
        Calculate feature importance using Random Forest.
        """
        self.target_column = target_column
        
        # Prepare data
        X = self.df.drop(columns=[target_column])
        y = self.df[target_column]
        
        # Handle categorical variables
        categorical_cols = X.select_dtypes(include=['object']).columns
        for col in categorical_cols:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
        
        # Handle missing values
        X = X.fillna(X.mean())
        
        # Determine if classification or regression
        if y.dtype == 'object' or y.nunique() < 10:
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            problem_type = 'classification'
        else:
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            problem_type = 'regression'
        
        # Fit model
        model.fit(X, y)
        
        # Get feature importance
        feature_importance = pd.DataFrame({
            'feature': X.columns,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        # Create feature importance plot
        plt.figure(figsize=(12, 6))
        top_features = feature_importance.head(15)
        plt.barh(range(len(top_features)), top_features['importance'])
        plt.yticks(range(len(top_features)), top_features['feature'])
        plt.xlabel('Importance')
        plt.title(f'Top 15 Feature Importance ({problem_type})')
        plt.gca().invert_yaxis()
        plt.tight_layout()
        
        importance_path = os.path.join(self.output_dir, 'feature_importance.png')
        plt.savefig(importance_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.analysis_results['feature_importance'] = feature_importance
        
        return feature_importance, importance_path

    def generate_comprehensive_report(self) -> str:
        """
        Generate a comprehensive HTML report with all analysis results.
        Images are embedded as base64 so the report is self-contained.
        Automatically generates any missing plots before embedding.
        """
        report_path = os.path.join(self.output_dir, 'analysis_report.html')

        # -------------------------------------------------------
        # Auto-generate any plots that haven't been created yet
        # (e.g. when called from Streamlit which uses Plotly instead)
        # -------------------------------------------------------
        corr_heatmap_path = os.path.join(self.output_dir, 'correlation_heatmap.png')
        if not os.path.exists(corr_heatmap_path):
            try:
                self.perform_correlation_analysis()
            except Exception:
                pass

        dist_path = os.path.join(self.output_dir, 'distribution_plots.png')
        if not os.path.exists(dist_path):
            try:
                self.create_distribution_plots()
            except Exception:
                pass

        box_path = os.path.join(self.output_dir, 'box_plots.png')
        if not os.path.exists(box_path):
            try:
                self.create_box_plots()
            except Exception:
                pass

        pca_path = os.path.join(self.output_dir, 'pca_analysis.png')
        if not os.path.exists(pca_path):
            try:
                self.perform_pca_analysis()
            except Exception:
                pass

        feat_path = os.path.join(self.output_dir, 'feature_importance.png')
        if not os.path.exists(feat_path) and self.target_column and self.target_column in self.df.columns:
            try:
                self.feature_importance_analysis(self.target_column)
            except Exception:
                pass

        # Pre-load all images as base64 data URIs
        images = {
            'correlation_heatmap': self._image_to_base64(corr_heatmap_path),
            'distribution_plots': self._image_to_base64(dist_path),
            'box_plots': self._image_to_base64(box_path),
            'pca_analysis': self._image_to_base64(pca_path),
            'feature_importance': self._image_to_base64(feat_path),
        }

        # Helper to build an img tag with embedded base64, or hide section if truly unavailable
        def img_tag(key, alt_text):
            b64 = images.get(key, '')
            if b64:
                return f'<img src="{b64}" alt="{alt_text}">'
            return ''

        # Create HTML report
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Automated Data Analysis Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }}
                .summary-item {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #3498db; }}
                .summary-item h3 {{ margin-top: 0; color: #3498db; font-size: 14px; }}
                .summary-item p {{ font-size: 24px; font-weight: bold; margin: 10px 0; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #3498db; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .plot-container {{ margin: 30px 0; text-align: center; }}
                .plot-container img {{ max-width: 100%; height: auto; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-radius: 4px; }}
                .warning {{ color: #e74c3c; font-weight: bold; }}
                .success {{ color: #27ae60; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>Automated Data Analysis Report</h1>
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

            <h2>Dataset Overview</h2>
        """

        # Add summary statistics
        if 'summary' in self.analysis_results:
            summary = self.analysis_results['summary']
            html_content += """
            <div class="summary-grid">
            """

            metrics = [
                ('Dataset Shape', f"{summary['dataset_shape'][0]:,} x {summary['dataset_shape'][1]:,}"),
                ('Missing Values', f"{summary['missing_percentage']:.2f}%"),
                ('Duplicate Rows', f"{summary['duplicate_rows']:,}"),
                ('Numeric Columns', f"{summary['numeric_columns']:,}"),
                ('Categorical Columns', f"{summary['categorical_columns']:,}"),
                ('Memory Usage', f"{summary['memory_usage']:.2f} MB")
            ]

            for title, value in metrics:
                html_content += f"""
                <div class="summary-item">
                    <h3>{title}</h3>
                    <p>{value}</p>
                </div>
                """

            html_content += "</div>"

        # Add column analysis
        if 'column_analysis' in self.analysis_results:
            html_content += """
            <h2>Column Analysis</h2>
            """
            col_df = self.analysis_results['column_analysis']
            html_content += col_df.to_html(classes='dataframe', index=False)

        # Add correlation analysis
        corr_img = img_tag('correlation_heatmap', 'Correlation Heatmap')
        if corr_img and 'correlation' in self.analysis_results:
            html_content += """
            <h2>Correlation Analysis</h2>
            <div class="plot-container">
                """ + corr_img + """
            </div>
            """

            strong_corr = self.analysis_results['correlation']['strong_correlations']
            if strong_corr:
                html_content += """
                <h3>Strong Correlations (|r| > 0.7)</h3>
                <table>
                    <tr><th>Variable 1</th><th>Variable 2</th><th>Correlation</th></tr>
                """
                for corr in strong_corr:
                    html_content += f"""
                    <tr>
                        <td>{corr['var1']}</td>
                        <td>{corr['var2']}</td>
                        <td>{corr['correlation']:.3f}</td>
                    </tr>
                    """
                html_content += "</table>"

        # Add distribution plots
        dist_img = img_tag('distribution_plots', 'Distribution Plots')
        if dist_img:
            html_content += """
            <h2>Distribution Analysis</h2>
            <div class="plot-container">
                """ + dist_img + """
            </div>
            """

        # Add box plots
        box_img = img_tag('box_plots', 'Box Plots')
        if box_img:
            html_content += """
            <h2>Outlier Analysis</h2>
            <div class="plot-container">
                """ + box_img + """
            </div>
            """

        # Add PCA analysis
        pca_img = img_tag('pca_analysis', 'PCA Analysis')
        if pca_img:
            html_content += """
            <h2>PCA Analysis</h2>
            <div class="plot-container">
                """ + pca_img + """
            </div>
            """

        # Add feature importance if available
        feat_img = img_tag('feature_importance', 'Feature Importance')
        if feat_img and 'feature_importance' in self.analysis_results:
            html_content += """
            <h2>Feature Importance Analysis</h2>
            <div class="plot-container">
                """ + feat_img + """
            </div>
            """

            top_features = self.analysis_results['feature_importance'].head(10)
            html_content += """
            <h3>Top 10 Most Important Features</h3>
            """
            html_content += top_features.to_html(classes='dataframe', index=False)

        html_content += """
        </body>
        </html>
        """

        # Save report
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return report_path

    def export_results_to_json(self):
        """
        Export numerical results to JSON format.
        """
        json_path = os.path.join(self.output_dir, 'analysis_results.json')
        
        # Convert DataFrames to dict for JSON serialization
        export_results = {}
        for key, value in self.analysis_results.items():
            if isinstance(value, pd.DataFrame):
                export_results[key] = value.to_dict('records')
            elif isinstance(value, dict):
                export_results[key] = value
        
        with open(json_path, 'w') as f:
            json.dump(export_results, f, indent=2, default=str)
        
        return json_path

    def run_full_analysis(self, target_column: str = None) -> str:
        """
        Run the complete automated analysis pipeline.
        
        Args:
            target_column: Target variable for supervised analysis (optional)
        
        Returns:
            Path to the generated HTML report
        """
        print("Starting Automated Data Analysis...")
        
        # 1. Generate data summary
        print("Generating data summary...")
        self.generate_data_summary()
        
        # 2. Analyze column types
        print("Analyzing column types...")
        self.analyze_column_types()
        
        # 3. Perform correlation analysis
        print("Performing correlation analysis...")
        self.perform_correlation_analysis()
        
        # 4. Perform statistical tests
        print("Performing statistical tests...")
        self.perform_statistical_tests()
        
        # 5. Create distribution plots
        print("Creating distribution plots...")
        self.create_distribution_plots()
        
        # 6. Create box plots
        print("Creating box plots...")
        self.create_box_plots()
        
        # 7. Perform PCA analysis
        print("Performing PCA analysis...")
        self.perform_pca_analysis()
        
        # 8. Feature importance analysis (if target specified)
        if target_column is None:
            target_column = self.auto_detect_target()
        
        if target_column in self.df.columns:
            print(f"Performing feature importance analysis for target: {target_column}")
            self.feature_importance_analysis(target_column)
        
        # 9. Export results to JSON
        print("Exporting results...")
        self.export_results_to_json()
        
        # 10. Generate comprehensive report
        print("Generating comprehensive report...")
        report_path = self.generate_comprehensive_report()
        
        print(f"Analysis complete! Report saved to: {report_path}")
        return report_path


def main():
    """
    Example usage of the AutomatedDataAnalyzer.
    """
    # Create a sample dataset for demonstration
    np.random.seed(42)
    n_samples = 1000
    
    sample_data = {
        'age': np.random.normal(35, 12, n_samples).astype(int),
        'income': np.random.exponential(50000, n_samples),
        'credit_score': np.random.normal(700, 50, n_samples),
        'loan_amount': np.random.normal(200000, 50000, n_samples),
        'term_months': np.random.choice([12, 24, 36, 48, 60], n_samples),
        'employment_years': np.random.normal(8, 4, n_samples),
        'debt_to_income': np.random.beta(2, 5, n_samples) * 100,
        'category': np.random.choice(['A', 'B', 'C', 'D'], n_samples),
        'status': np.random.choice(['Good', 'Fair', 'Poor'], n_samples),
        'default': np.random.choice([0, 1], n_samples, p=[0.8, 0.2])
    }
    
    sample_df = pd.DataFrame(sample_data)
    sample_path = "sample_data.csv"
    sample_df.to_csv(sample_path, index=False)
    
    print(f"Created sample dataset: {sample_path}")
    print(f"Shape: {sample_df.shape}")
    print()
    
    # Initialize and run the analyzer
    analyzer = AutomatedDataAnalyzer(
        data_path=sample_path,
        output_dir="analysis_output"
    )
    
    # Run full analysis
    report_path = analyzer.run_full_analysis(target_column='default')
    
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)
    
    # Print key findings
    summary = analyzer.analysis_results['summary']
    print(f"Dataset: {summary['dataset_shape'][0]:,} rows x {summary['dataset_shape'][1]:,} columns")
    print(f"Missing values: {summary['missing_percentage']:.2f}%")
    print(f"Duplicate rows: {summary['duplicate_rows']:,}")
    
    if 'feature_importance' in analyzer.analysis_results:
        print("\nTop 5 Important Features:")
        top5 = analyzer.analysis_results['feature_importance'].head()
        for _, row in top5.iterrows():
            print(f"  - {row['feature']}: {row['importance']:.4f}")
    
    print(f"\nAll outputs saved to: {analyzer.output_dir}/")
    print(f"View the report: {report_path}")


if __name__ == "__main__":
    main()