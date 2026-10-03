"""
Unit Test Suite for Part 6 — Data Cleaning Module
"""
import unittest
import pandas as pd
import numpy as np

from cleaner.domain import (
    DuplicateConfig,
    ImputationConfig,
    OutlierConfig,
    EncodingConfig,
    ScalingConfig,
    ValidationRule
)
from cleaner.services import (
    DuplicateRemoverService,
    ImputerService,
    OutlierDetectorService,
    EncoderService,
    ScalerService,
    DataValidatorService,
    CleaningPipeline
)

class TestCleanerModule(unittest.TestCase):

    def setUp(self):
        """Create sample messy dataset for testing"""
        np.random.seed(42)
        self.df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 5, 7, 8, 9, 10],  # duplicate id 5
            'age': [25, np.nan, 35, 40, 150, 150, 22, 28, 30, np.nan],  # NaN and outlier 150
            'salary': [50000, 60000, np.nan, 80000, 900000, 900000, 45000, 52000, 61000, 70000],  # NaN & outlier 900000
            'city': ['New York', 'New York ', 'London', 'Paris', 'Tokyo', 'Tokyo', 'London', np.nan, 'Paris', 'Tokyo'],
            'status': ['Active', 'Active', 'Inactive', 'Active', 'Active', 'Active', 'Pending', 'Active', 'Inactive', 'Active']
        })

    def test_duplicate_remover(self):
        service = DuplicateRemoverService()

        # Exact Duplicate Test
        cfg_exact = DuplicateConfig(keep='first')
        cleaned, audit = service.process(self.df, cfg_exact)
        self.assertEqual(len(cleaned), 9)
        self.assertEqual(audit.rows_before, 10)
        self.assertEqual(audit.rows_after, 9)

        # Fuzzy Duplicate Test
        cfg_fuzzy = DuplicateConfig(fuzzy_enable=True, fuzzy_columns=['city'], fuzzy_threshold=0.85)
        cleaned_f, audit_f = service.process(self.df, cfg_fuzzy)
        self.assertTrue(len(cleaned_f) <= 10)

    def test_imputer(self):
        service = ImputerService()
        cfg = ImputationConfig(
            default_numeric_strategy='median',
            default_categorical_strategy='mode'
        )
        cleaned, audit = service.process(self.df, cfg)

        self.assertEqual(cleaned['age'].isnull().sum(), 0)
        self.assertEqual(cleaned['salary'].isnull().sum(), 0)
        self.assertEqual(cleaned['city'].isnull().sum(), 0)
        self.assertEqual(cleaned['age'].median(), 32.5)

    def test_outlier_detector(self):
        service = OutlierDetectorService()

        # IQR Capping
        cfg_iqr = OutlierConfig(method='iqr', action='cap', columns=['salary'], iqr_multiplier=1.5)
        cleaned, audit = service.process(self.df, cfg_iqr)
        self.assertLess(cleaned['salary'].max(), 900000)

        # Z-Score Capping
        cfg_z = OutlierConfig(method='zscore', action='cap', columns=['age'], zscore_threshold=1.5)
        cleaned_z, audit_z = service.process(self.df, cfg_z)
        self.assertLess(cleaned_z['age'].max(), 150)

    def test_encoder(self):
        service = EncoderService()

        # One-Hot Encoding
        cfg_ohe = EncodingConfig(strategy='onehot', columns=['status'], drop_first=True)
        cleaned_ohe, audit = service.process(self.df, cfg_ohe)
        self.assertIn('status_Inactive', cleaned_ohe.columns)

        # Ordinal Encoding
        cfg_ord = EncodingConfig(strategy='ordinal', columns=['city'])
        cleaned_ord, audit_ord = service.process(self.df, cfg_ord)
        self.assertTrue(np.issubdtype(cleaned_ord['city'].dtype, np.integer))

    def test_scaler(self):
        service = ScalerService()
        df_num = self.df[['age', 'salary']].fillna(0)

        # StandardScaler
        cfg_std = ScalingConfig(strategy='standard')
        cleaned_std, audit = service.process(df_num, cfg_std)
        self.assertAlmostEqual(cleaned_std['salary'].mean(), 0.0, places=1)

        # MinMaxScaler
        cfg_minmax = ScalingConfig(strategy='minmax')
        cleaned_mm, audit_mm = service.process(df_num, cfg_minmax)
        self.assertAlmostEqual(cleaned_mm['salary'].min(), 0.0, places=5)
        self.assertAlmostEqual(cleaned_mm['salary'].max(), 1.0, places=5)

    def test_data_validator(self):
        service = DataValidatorService()
        rules = [
            ValidationRule(rule_id="r1", column="age", rule_type="non_null"),
            ValidationRule(rule_id="r2", column="id", rule_type="unique"),
            ValidationRule(rule_id="r3", column="salary", rule_type="range", min_val=0, max_val=200000)
        ]
        report = service.validate(self.df, rules)

        self.assertEqual(report.total_rules, 3)
        self.assertFalse(report.overall_passed)
        self.assertEqual(report.failed_rules, 3) # age has null, id has duplicate, salary has 900000 > 200000

    def test_cleaning_pipeline(self):
        pipeline = CleaningPipeline(self.df)

        # Step 1: Remove Duplicates
        pipeline.remove_duplicates(DuplicateConfig(keep='first'))
        self.assertEqual(len(pipeline.current_df), 9)

        # Step 2: Impute Missing Values
        pipeline.impute_missing(ImputationConfig(default_numeric_strategy='median'))
        self.assertEqual(pipeline.current_df['age'].isnull().sum(), 0)

        # Step 3: Undo Step 2
        pipeline.undo_last_step()
        self.assertEqual(pipeline.current_df['age'].isnull().sum(), 2)

        # Step 4: Reset to Raw
        pipeline.reset_to_raw()
        self.assertEqual(len(pipeline.current_df), 10)

        # Code Exporter
        code = pipeline.generate_python_code()
        self.assertIn("import pandas as pd", code)

if __name__ == '__main__':
    unittest.main()
