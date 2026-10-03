from types import SimpleNamespace

import pandas as pd
import pytest
from flask import Flask

from app.routes import copilot
from ai_engine.domain.entities import (
    AnomalyItem, AnomalySummary, BusinessRecommendation, ExecutiveReportData,
    RootCauseItem, TrendResult,
)
from ai_engine.domain.enums import AnomalyMethod, ImpactLevel, TrendDirection


@pytest.fixture
def copilot_client(monkeypatch):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-only'
    app.register_blueprint(copilot.copilot_bp)
    monkeypatch.setattr(copilot, 'get_current_user', lambda: SimpleNamespace(id=1))
    monkeypatch.setattr(copilot.DatasetService, 'get_dataset',
                        lambda *args: SimpleNamespace(name='fixture', storage_path='fixture', file_format='csv'))
    df = pd.DataFrame({'value': list(range(1, 100)) + [10000],
                       'group': ['a', 'b'] * 50})
    monkeypatch.setattr(copilot.DatasetService, 'load_dataframe', lambda *args: (df, ''))
    with app.test_client() as client:
        with client.session_transaction() as session:
            session.update(user_id=1, authenticated=True)
        yield client


def test_insights_serializes_actual_domain_fields(copilot_client, monkeypatch):
    report = ExecutiveReportData(
        trends=[TrendResult('value', TrendDirection.UPWARD, 2., .9, 25., 10., 2., summary_text='Increasing')],
        anomalies=AnomalySummary(100, 2, 2., [
            AnomalyItem(4, 'value', 10, .5, AnomalyMethod.IQR, reason='Lower score'),
            AnomalyItem(9, 'value', 100, .9, AnomalyMethod.IQR, reason='Outside range'),
        ]),
        root_causes=[RootCauseItem('group', 'group = a', .75, 20, 20., 'Segment difference')],
        recommendations=[BusinessRecommendation('Review', ImpactLevel.HIGH, 'Risk', 'Review outliers', ['Inspect row 9'])],
    )
    monkeypatch.setattr(copilot.AIEngine, 'run_full_ai_analysis', lambda self: report)
    response = copilot_client.get('/copilot/api/1/insights')
    assert response.status_code == 200
    data = response.json
    assert data['trends'][0]['pct_change'] == 25.
    assert data['trends'][0]['description'] == 'Increasing'
    assert data['anomalies']['items'][0]['index'] == 9
    assert data['anomalies']['items'][0]['description'] == 'Outside range'
    assert data['root_causes'][0]['condition'] == 'group = a'
    assert data['root_causes'][0]['impact_score'] == .75
    assert data['recommendations'][0]['expected_impact'] == 'high'


def test_insights_with_real_engine(copilot_client):
    response = copilot_client.get('/copilot/api/1/insights')
    assert response.status_code == 200, response.json
    assert response.json['trends']
    assert response.json['anomalies']['count'] > 0
    assert response.json['recommendations']
