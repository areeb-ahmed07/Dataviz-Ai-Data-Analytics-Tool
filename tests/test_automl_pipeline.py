import unittest
import pandas as pd
import numpy as np

from ml.automl_pipeline import AutoMLPipeline


class AutoMLPipelineSpeedTest(unittest.TestCase):
    def test_fast_mode_runs_quickly_with_small_dataset(self):
        np.random.seed(42)
        df = pd.DataFrame({
            'feature_1': np.random.normal(0, 1, 80),
            'feature_2': np.random.normal(2, 0.5, 80),
            'category': np.random.choice(['A', 'B', 'C'], 80),
            'target': np.random.choice([0, 1], 80),
        })

        automl = AutoMLPipeline(df, 'target')
        results = automl.compare_models(cv_folds=2, fast_mode=True)

        self.assertIsInstance(results, dict)
        self.assertGreater(len(results), 0)


if __name__ == '__main__':
    unittest.main()
