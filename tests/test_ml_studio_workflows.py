import json
import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification, make_regression, make_blobs
from app.services.ml_service import MLService
from ml.services.model_registry import get_model_zoo


@pytest.fixture
def workflow(monkeypatch):
    uid, did = 98765, 98765
    def configure(df, task, target=None, **extra):
        monkeypatch.setattr(MLService, 'load_dataset', lambda *args: (df.copy(), None))
        config = dict(problem_type=task, target_column=target,
                      feature_columns=[c for c in df.columns if c != target], cv_folds=3,
                      auto_mode=False, selected_algorithms=list(get_model_zoo(task)))
        config.update(extra)
        _, err = MLService.save_config(uid, did, config)
        assert err is None, err
        return uid, did
    yield configure
    MLService.clear_cache(uid, did)


@pytest.mark.parametrize('task', ['classification', 'regression', 'clustering'])
def test_all_models_train_and_comparison_is_json(workflow, task):
    if task == 'classification':
        X, y = make_classification(n_samples=100, n_features=4, random_state=42)
    elif task == 'regression':
        X, y = make_regression(n_samples=100, n_features=4, random_state=42)
    else:
        X, y = make_blobs(n_samples=100, n_features=4, centers=3, random_state=42)
    df = pd.DataFrame(X, columns=list('abcd'))
    df.loc[0, 'a'] = np.nan
    df['category'] = ['one', 'two'] * 50
    target = None
    if task != 'clustering':
        target = 'target'
        df[target] = np.where(y == 1, 'yes', 'no') if task == 'classification' else y
    ids = workflow(df, task, target)
    _, err = MLService.prepare_data(*ids)
    assert err is None, err
    result, err = MLService.train_models(*ids)
    assert err is None, err
    assert result['leaderboard']
    assert all(r['valid'] for r in result['model_results'].values()), result['model_results']
    assert len(result['model_results']) == len(get_model_zoo(task))
    json.dumps(result, allow_nan=False)
    if task == 'classification':
        result, err = MLService.get_confusion_matrix(*ids)
        assert err is None, err
        assert len(result['matrix']) == 2
    if task == 'regression':
        result, err = MLService.get_predictions(*ids)
        assert err is None, err


@pytest.mark.parametrize('task, target, message', [
    ('classification', [0.] * 19 + [.5], 'continuous'),
    ('classification', ['a'] * 19 + ['b'], 'at least 3'),
    ('classification', ['a'] * 20, 'at least two'),
    ('regression', ['a', 'b'] * 10, 'numeric target'),
])
def test_invalid_targets_have_actionable_errors(workflow, task, target, message):
    ids = workflow(pd.DataFrame({'feature': range(20), 'target': target}), task, 'target')
    _, err = MLService.prepare_data(*ids)
    assert message in err


def test_clustering_selection_and_undefined_metrics(workflow):
    ids = workflow(pd.DataFrame({'a': np.arange(20) * 100.}), 'clustering',
                   selected_algorithms=['DBSCAN'])
    _, err = MLService.prepare_data(*ids)
    assert err is None
    result, err = MLService.train_models(*ids)
    assert err is None
    assert list(result['model_results']) == ['DBSCAN']
    json.dumps(result, allow_nan=False)


def test_regression_ranking_uses_lower_errors():
    from ml.services.leaderboard import LeaderboardService
    from ml.domain.ml_result import ModelResult, CVResult
    cv = CVResult('model', 'kfold', 'r2', [.5, .6], .55, .05)
    results = {n: ModelResult(n, 'regression', cv, {'rmse': v, 'r2': 1 / v})
               for n, v in [('better', 2.), ('worse', 10.)]}
    assert LeaderboardService().build(results, 'regression', 'rmse')[0].model_name == 'better'
    assert LeaderboardService().build(results, 'regression')[0].primary_metric_name == 'r2'


def test_optimization_uses_current_tuner_api(workflow):
    df = pd.DataFrame({'x': range(40), 'target': np.arange(40) * 2.5})
    ids = workflow(df, 'regression', 'target', selected_algorithms=['Linear Regression'],
                   optimization_level='fast')
    assert MLService.prepare_data(*ids)[1] is None
    assert MLService.train_models(*ids)[1] is None
    result, error = MLService.optimize_model(*ids)
    assert error is None, error
    assert result['test_metrics']['r2'] == 1.


def test_rare_classes_reduce_cv_folds(workflow):
    df = pd.DataFrame({'x': range(30), 'target': ['a'] * 27 + ['b'] * 3})
    ids = workflow(df, 'classification', 'target', selected_algorithms=['Decision Tree'], cv_folds=10)
    assert MLService.prepare_data(*ids)[1] is None
    result, error = MLService.train_models(*ids)
    assert error is None, error
    assert result['cv_config']['folds'] == 2
