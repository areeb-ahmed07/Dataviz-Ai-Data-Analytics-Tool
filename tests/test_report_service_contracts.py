import json
import pandas as pd

from app.services.report_service import ReportService


def test_report_gather_calls_column_scoped_distribution(monkeypatch):
    dataset = type('Dataset', (), {'id': 9, 'name': 'demo', 'storage_path': 'x', 'file_format': 'csv'})()
    frame = pd.DataFrame({'amount': [1., 2.], 'label': ['a', 'b']})
    monkeypatch.setattr('app.services.report_service._load_dataset', lambda *a, **k: (frame, None))
    monkeypatch.setattr('app.services.report_service.DatasetService.get_dataset', lambda *a: dataset)
    class Analysis:
        @staticmethod
        def get_overview(*a): return ({}, None)
        @staticmethod
        def get_quality(*a): return ({}, None)
        @staticmethod
        def get_statistics(*a): return ({'numeric': [], 'categorical': [], 'datetime': []}, None)
        @staticmethod
        def get_correlations(*a): return ({}, None)
        @staticmethod
        def get_distribution(*a):
            assert len(a) == 3
            return ({'column': a[2]}, None)
        @staticmethod
        def get_outliers(*a): return ({}, None)
        @staticmethod
        def get_categorical_analysis(*a): return ({}, None)
        @staticmethod
        def get_insights(*a): return ({}, None)
    monkeypatch.setattr('app.services.report_service.AnalysisService', Analysis)
    monkeypatch.setattr(ReportService, '_get_models_for_dataset', staticmethod(lambda *a: []))
    result, error = ReportService.gather_analysis_data(9, 4)
    assert error is None
    assert list(result['distributions']) == ['amount']
    json.dumps(result, allow_nan=False)


def test_preview_exposes_actual_column_counts(monkeypatch):
    data = {
        'dataset_name': 'demo', 'dataset_id': 1, 'row_count': 2, 'col_count': 2,
        'overview': {}, 'quality': {'quality_score': 95, 'missing_pct': 0, 'duplicate_rows': 0},
        'statistics': {'numeric_stats': [{}], 'categorical_stats': [{}], 'datetime_stats': []},
        'correlations': {}, 'distributions': {}, 'outliers': {}, 'ml_models': []
    }
    monkeypatch.setattr(ReportService, 'gather_analysis_data', staticmethod(lambda *a: (data, None)))
    preview, error = ReportService.get_report_preview(1, 1)
    assert error is None
    assert (preview['numeric_columns'], preview['categorical_columns']) == (1, 1)
    assert 'markdown' in preview['available_formats']
