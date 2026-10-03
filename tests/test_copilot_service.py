import json
import time
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from app.services.copilot_service import CopilotService, _JobStore


@pytest.fixture
def use_frame(monkeypatch):
    def set_frame(frame):
        monkeypatch.setattr(CopilotService, '_load_df', classmethod(lambda cls, dataset_id: (frame, None)))
    return set_frame


@pytest.mark.parametrize('question,method,extra', [
    ('missing values', '_quick_missing', False),
    ('correlation', '_quick_correlations', False),
    ('more detail', '_follow_up_analysis', True),
    ('compare', '_quick_comparison', True),
    ('saved model', '_quick_model_info', False),
])
def test_intent_handlers_receive_expected_arguments(monkeypatch, question, method, extra):
    expected = {'answer': 'result'}
    handler = Mock(return_value=expected)
    monkeypatch.setattr(CopilotService, method, handler)
    history = [{'content': 'previous question'}]
    assert CopilotService.detect_intent_and_respond(17, question, history) == expected
    handler.assert_called_once_with(17, question, *([history] if extra else []))


def test_empty_question_needs_no_dataset():
    result = CopilotService.detect_intent_and_respond(17, '  ', [])
    assert 'Please ask a question' in result['answer']


def test_missing_counts_cells_and_columns(use_frame):
    use_frame(pd.DataFrame({'x': [1., None, 3.], 'y': [None, None, 6.]}))
    result = CopilotService.detect_intent_and_respond(17, 'missing values', [])
    assert result['data'] == {'columns_missing': ['x', 'y'], 'total_missing': 3, 'total_cells': 6}
    assert '50.0%' in result['answer']
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('frame', [pd.DataFrame(), pd.DataFrame({'x': [1, 2]})])
def test_clean_or_empty_missing_values(use_frame, frame):
    use_frame(frame)
    assert 'No missing values' in CopilotService._quick_missing(17, '')['answer']


def test_correlations_are_unique_signed_and_json_serializable(use_frame):
    use_frame(pd.DataFrame({'x': [1, 2, 3, 4], 'y': [8, 6, 4, 2], 'constant': [1]*4, 'label': ['a']*4}))
    result = CopilotService._quick_correlations(17, '')
    assert result['data'] == [{'column1': 'x', 'column2': 'y', 'correlation': -1.0}]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('frame', [pd.DataFrame(), pd.DataFrame({'label': ['a']}), pd.DataFrame({'x': [1, 2]})])
def test_correlations_without_valid_pairs(use_frame, frame):
    use_frame(frame)
    result = CopilotService._quick_correlations(17, '')
    assert result['intent'] == 'correlation_info'
    assert not result.get('data')


def test_overview_reports_missing_and_duplicates(use_frame):
    use_frame(pd.DataFrame({'x': [1., 1., None], 'y': [2., 2., 3.]}))
    result = CopilotService._quick_overview(17, '')
    assert '1/6 (16.7%)' in result['answer']
    assert 'Duplicate rows: 1.' in result['answer']


def test_empty_overview(use_frame):
    use_frame(pd.DataFrame())
    assert '0/0 (0.0%)' in CopilotService._quick_overview(17, '')['answer']


def test_recommendations_use_actual_missing_and_duplicate_counts(use_frame, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    use_frame(pd.DataFrame({'x': [1., 1., None]}))
    result = CopilotService._quick_recommendations(17, '')
    assert 'Cleaning' in result['answer']
    assert 'Deduplicate' in result['answer']


def test_trends_compute_regression(use_frame):
    use_frame(pd.DataFrame({'x': [2, 4, 6, 8, 10, 12]}))
    trend = CopilotService._quick_trends(17, '')['data'][0]
    assert trend['slope'] == pytest.approx(2)
    assert trend['r2'] == pytest.approx(1)
    assert trend['direction'] == 'upward'


def test_root_causes_report_outlier_percentage(use_frame):
    use_frame(pd.DataFrame({'x': [0]*19 + [100]}))
    result = CopilotService._quick_root_causes(17, '')
    assert result['data'][0]['affected_pct'] == 5
    assert '5.0%' in result['data'][0]['description']


@pytest.mark.parametrize('outcome', ['success', 'error', 'exception'])
def test_background_jobs_complete_and_report_errors(outcome):
    def work():
        if outcome == 'exception':
            raise ValueError('analysis failed')
        if outcome == 'error':
            return None, 'analysis failed'
        return {'values': np.array([1, 2]), 'count': np.int64(2)}, None

    job = CopilotService.start_analysis_job(work)
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status, error = CopilotService.get_job_status(job['job_id'])
            assert error is None
            if status['status'] != 'running':
                break
            time.sleep(0.01)
        if outcome == 'success':
            assert status == {'status': 'done', 'result': {'values': [1, 2], 'count': 2}}
            json.dumps(status)
        else:
            assert status == {'status': 'error', 'error': 'analysis failed'}
    finally:
        with _JobStore._lock:
            _JobStore._jobs.pop(job['job_id'], None)
