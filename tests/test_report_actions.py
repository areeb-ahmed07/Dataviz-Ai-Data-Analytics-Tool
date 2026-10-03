import os
from conftest import BaseTestCase
from app.services.report_service import ReportService


class TestReportActions(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.original_static = self.app.static_folder
        self.app.static_folder = os.path.join(self.temp_dir, 'static')
        self.login()
        with self.client.session_transaction() as session:
            self.user_id = session['user_id']
        self.directory = ReportService.report_directory(self.user_id)
        os.makedirs(self.directory, exist_ok=True)
        self.filename = 'Quarterly report.pdf'
        self.path = os.path.join(self.directory, self.filename)
        with open(self.path, 'wb') as report:
            report.write(b'%PDF-1.4 test report')
        from app.core.cache import dashboard_cache
        dashboard_cache.invalidate_user(self.user_id)
        self.url = '/reports/files/Quarterly%20report.pdf'

    def tearDown(self):
        self.app.static_folder = self.original_static
        self.app.config['WTF_CSRF_ENABLED'] = False
        super().tearDown()

    def test_view_and_download(self):
        for suffix, disposition in [('', 'inline'), ('?download=1', 'attachment')]:
            response = self.client.get(self.url + suffix)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers['Content-Disposition'].startswith(disposition))
            response.close()

    def test_delete_updates_dashboard(self):
        self.assertIn(self.filename.encode(), self.client.get('/dashboard').data)
        response = self.client.post(self.url + '/delete', data={'return_to': 'dashboard'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/dashboard'))
        self.assertFalse(os.path.exists(self.path))
        self.assertNotIn(self.filename.encode(), self.client.get('/dashboard').data)

    def test_other_user_cannot_access_or_delete(self):
        self.client.get('/logout')
        self.login()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url + '/delete').status_code, 404)
        self.assertTrue(os.path.exists(self.path))

    def test_delete_requires_post_and_csrf(self):
        self.assertEqual(self.client.get(self.url + '/delete').status_code, 405)
        self.app.config['WTF_CSRF_ENABLED'] = True
        response = self.client.post(self.url + '/delete')
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertTrue(any('Security validation failed' in message for _, message in session['_flashes']))
        self.assertTrue(os.path.exists(self.path))

    def test_invalid_paths_and_missing_report(self):
        for filename in ['../report.pdf', '..\\report.pdf', 'C:report.pdf', 'missing.pdf']:
            self.assertIsNone(ReportService.resolve_report(self.user_id, filename))
        self.assertEqual(self.client.get('/reports/files/missing.pdf').status_code, 404)

    def test_both_lists_have_accessible_icon_actions(self):
        for url in ['/dashboard', '/reports/']:
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            for label in ['View report', 'Download report', 'Delete report']:
                self.assertIn(label.encode(), page.data)
