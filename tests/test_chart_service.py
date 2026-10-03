import json

import numpy as np
import pandas as pd
import pytest

from app.services.chart_service import prepare_chart_data


@pytest.mark.parametrize('kind', ['bar', 'line', 'scatter', 'pie', 'histogram',
                                  'box', 'violin', 'heatmap', 'correlation', 'treemap'])
def test_supported_charts_are_strict_json(kind):
    df = pd.DataFrame({'x': [1, 2, 3], 'y': [2., np.nan, 4.], 'z': [3., 4., 5.]})
    result = prepare_chart_data(df, kind, 'x', 'y', 'z')
    json.dumps(result, allow_nan=False)
    assert result['x']


def test_aggregation_preserves_all_rows_and_categories():
    df = pd.DataFrame({'group': list(range(150)) * 40, 'value': [2.] * 6000})
    result = prepare_chart_data(df, 'bar', 'group', 'value', agg='sum')
    assert len(result['x']) == 150
    assert sum(result['y']) == 12000


def test_count_includes_missing_values_and_same_column():
    df = pd.DataFrame({'group': ['a', 'a', 'b'], 'value': [1., np.nan, 2.]})
    assert prepare_chart_data(df, 'bar', 'group', 'value', agg='count')['y'] == [2, 1]
    assert prepare_chart_data(df, 'bar', 'group', 'group', agg='count')['y'] == [2, 1]


def test_line_sorted_and_not_randomly_sampled():
    df = pd.DataFrame({'x': list(range(6000, 0, -1)), 'y': [2.] * 6000})
    result = prepare_chart_data(df, 'line', 'x', 'y', agg='sum')
    assert result['x'] == list(range(1, 6001))


def test_heatmap_matrix_has_correct_cells():
    df = pd.DataFrame({'x': ['a', 'a', 'b'], 'y': ['c', 'c', 'd'], 'z': [2., 4., 7.]})
    result = prepare_chart_data(df, 'heatmap', 'x', 'y', 'z', 'sum')
    assert result == {'x': ['a', 'b'], 'y': ['c', 'd'], 'z': [[6., None], [None, 7.]]}
    with pytest.raises(ValueError, match='aggregation'):
        prepare_chart_data(df, 'heatmap', 'x', 'y', 'z')


def test_invalid_numeric_choice_is_actionable():
    df = pd.DataFrame({'x': ['a'], 'y': ['b']})
    with pytest.raises(ValueError, match='must contain numbers'):
        prepare_chart_data(df, 'pie', 'x', 'y')


def test_treemap_retains_missing_category_total():
    df = pd.DataFrame({'x': ['a', None], 'y': [2., 3.]})
    result = prepare_chart_data(df, 'treemap', 'x', 'y', agg='sum')
    assert result == {'x': ['a', '(Missing)'], 'y': [2., 3.]}


def test_nonfinite_and_undefined_correlation_are_null():
    df = pd.DataFrame({'x': [1, 2, 3], 'y': [np.inf, 2., np.nan], 'constant': [1, 1, 1]})
    result = prepare_chart_data(df, 'bar', 'x', 'y', agg='sum')
    assert result['y'] == [None, 2., None]
    corr = prepare_chart_data(df, 'correlation')
    assert corr['z'][2] == [None, None, None]
    json.dumps(corr, allow_nan=False)


def test_chart_api_returns_valid_json_and_validation_errors(monkeypatch):
    from flask import Flask
    from types import SimpleNamespace
    from app.routes import visualization

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-only'
    app.register_blueprint(visualization.visualization_bp)
    monkeypatch.setattr(visualization, 'get_current_user', lambda: SimpleNamespace(id=1))
    monkeypatch.setattr(visualization.DatasetService, 'get_dataset',
                        lambda *args: SimpleNamespace(storage_path='fixture', file_format='csv'))
    frame = pd.DataFrame({'x': ['a', 'b'], 'y': [np.nan, 5.]})
    monkeypatch.setattr(visualization.DatasetService, 'load_dataframe', lambda *args, **kwargs: (frame, ''))
    with app.test_client() as client:
        with client.session_transaction() as session:
            session.update(user_id=1, authenticated=True)
        response = client.get('/visualization/api/1/data?chart_type=bar&x=x&y=y&agg=sum')
        assert response.status_code == 200
        assert b'NaN' not in response.data
        assert response.json['y'] == [None, 5.]
        response = client.get('/visualization/api/1/data?chart_type=pie&x=x&y=x')
        assert response.status_code == 400
        assert 'must contain numbers' in response.json['error']
