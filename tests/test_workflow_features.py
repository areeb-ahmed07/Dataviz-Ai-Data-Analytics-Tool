import io
import json
import os
import threading
from unittest.mock import patch
import pandas as pd
from conftest import BaseTestCase
from app.services.ml_service import MLService
from auth.database import get_session, SavedChartDB


class TestWorkflowFeatures(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        with self.client.session_transaction() as session:
            self.uid = session['user_id']
        csv = 'x,y\n' + '\n'.join(f'{i},{3*i+2}' for i in range(40))
        self.client.post('/datasets/upload', data={'file': (io.BytesIO(csv.encode()), 'training.csv')})
        self.did = self.client.get('/api/datasets').get_json()['datasets'][0]['id']
        config, error = MLService.save_config(self.uid, self.did, {
            'problem_type': 'regression', 'target_column': 'y', 'feature_columns': ['x'],
            'auto_mode': False, 'selected_algorithms': ['Linear Regression'], 'cv_folds': 2})
        self.assertIsNone(error)

    def test_workspace_survives_cache_reset_and_is_private(self):
        # Revisiting a workspace must receive the same metadata shape on a cache hit.
        first = self.client.get(f'/api/datasets/{self.did}/ml/info').get_json()
        second = self.client.get(f'/api/datasets/{self.did}/ml/info').get_json()
        self.assertEqual(first, second)
        self.assertEqual(second['rows'], 40)
        db = get_session()
        try:
            db.add(SavedChartDB(user_id=self.uid, dataset_id=self.did, name='Sales',
                               chart_type='bar', config=json.dumps({'type': 'bar', 'x': 'x', 'y': 'y'})))
            db.commit()
        finally:
            db.close()
        response = self.client.post(f'/api/datasets/{self.did}/workspaces', json={'name':'Forecast', 'ui':[]})
        self.assertEqual(response.status_code, 201)
        wid = response.get_json()['id']
        MLService._configs.pop(MLService._cache_key(self.uid, self.did))
        saved = self.client.get(f'/api/workspaces/{wid}').get_json()
        self.assertEqual(saved['config']['feature_columns'], ['x'])
        self.assertEqual(saved['charts'][0]['name'], 'Sales')
        self.assertEqual(self.client.get(f'/workspaces/{wid}/charts/0').status_code, 200)
        self.logout()
        self.login()
        self.assertEqual(self.client.get(f'/api/workspaces/{wid}').status_code, 404)
        self.assertEqual(self.client.get(f'/workspaces/{wid}/charts/0').status_code, 404)

    def test_prediction_upload_reuses_model_and_checks_columns_and_owner(self):
        _, error = MLService.prepare_data(self.uid, self.did)
        self.assertIsNone(error)
        _, error = MLService.train_models(self.uid, self.did)
        self.assertIsNone(error)
        with patch.object(MLService, 'MODEL_STORAGE_DIR', os.path.join(self.temp_dir, 'models')):
            result, error = MLService.save_model(self.uid, self.did, model_name='Linear Regression')
        self.assertIsNone(error)
        mid = result['model_id']
        response = self.client.post(f'/models/{mid}/predict', data={'file':(io.BytesIO(b'x,note\n41,=1+1\n42,hello\n'), 'new.csv')})
        self.assertEqual(response.status_code, 200)
        output = pd.read_csv(io.BytesIO(response.data))
        self.assertAlmostEqual(output.prediction.iloc[0], 125, places=5)
        self.assertEqual(output.note.iloc[0], "'=1+1")
        bad = self.client.post(f'/models/{mid}/predict', data={'file':(io.BytesIO(b'z\n1\n'), 'new.csv')})
        self.assertEqual(bad.status_code, 400)
        self.assertIn(b'Missing required columns: x', bad.data)
        self.logout()
        self.login()
        self.assertEqual(self.client.get(f'/models/{mid}/predict').status_code, 404)

    def test_training_progress_cancellation_and_ownership(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def training(uid, did, progress=None):
            try:
                progress(0, 2, 'First model')
                entered.set()
                release.wait(5)
                progress(1, 2, 'Second model')
                return {}, None
            finally:
                finished.set()
        with patch.object(MLService, 'train_models', side_effect=training):
            job = MLService.start_training_job(self.uid, self.did)['job_id']
            try:
                self.assertTrue(entered.wait(5))
                state, error = MLService.get_job_status(job, self.uid, self.did)
                self.assertEqual(state['model'], 'First model')
                self.assertNotIn('cancel', state)
                self.assertIsNone(MLService.get_job_status(job, self.uid+10000, self.did)[0])
                self.assertIsNone(MLService.cancel_job(job, self.uid, self.did+1)[0])
                state, error = MLService.cancel_job(job, self.uid, self.did)
                self.assertEqual(state['status'], 'cancelling')
            finally:
                release.set()
                self.assertTrue(finished.wait(5))
