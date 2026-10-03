from datetime import datetime
from unittest.mock import patch

from conftest import BaseTestCase
from auth.database import AuditLogDB, UserDB, get_session


class TestAdminAuditLogs(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        with self.client.session_transaction() as session:
            self.user_id = session['user_id']
        db = get_session()
        try:
            db.get(UserDB, self.user_id).role = 'admin'
            db.commit()
        finally:
            db.close()

    def test_populated_page_and_json_use_current_audit_fields(self):
        action = 'audit_test_' + self._unique_suffix()
        db = get_session()
        try:
            db.add_all([
                AuditLogDB(user_id=self.user_id, username='Audit Tester',
                           action=action, success=True,
                           created_at=datetime(2026, 9, 19, 13, 45)),
                AuditLogDB(action=action, success=False,
                           created_at=datetime(2026, 9, 19, 13, 46)),
            ])
            db.commit()
        finally:
            db.close()

        response = self.client.get('/admin/audit-logs', query_string={'action': action})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sep 19, 2026 01:45 PM', response.data)
        self.assertIn(b'Audit Tester', response.data)
        self.assertIn(b'System / anonymous', response.data)
        self.assertIn(b'Success', response.data)
        self.assertIn(b'Failure', response.data)
        payload = self.client.get('/admin/api/audit-logs', query_string={'action': action}).get_json()
        self.assertEqual(payload['total'], 2)
        self.assertIsInstance(payload['logs'][0]['created_at'], str)
        self.assertIs(payload['logs'][0]['success'], False)

    def test_empty_and_missing_timestamp_render(self):
        with patch('app.routes.admin.AuditService.get_logs', return_value=([], 0)):
            response = self.client.get('/admin/audit-logs')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'No audit logs yet', response.data)
        entry = dict(created_at=None, username=None, user_id=None,
                     action='system_event', resource_type=None, resource_id=None,
                     ip_address=None, success=True)
        with patch('app.routes.admin.AuditService.get_logs', return_value=([entry], 1)):
            self.assertEqual(self.client.get('/admin/audit-logs').status_code, 200)

    def test_user_management_omits_other_account_email(self):
        from auth.services.auth_service import AuthService
        suffix = self._unique_suffix()
        email = f'private_{suffix}@example.com'
        username = f'private_{suffix}'
        db = get_session()
        try:
            result = AuthService(db=db).register_user('Private User', username, email, 'TestPass123!')
            self.assertTrue(result[0])
        finally:
            db.close()
        response = self.client.get('/admin/users')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(email.encode(), response.data)
        self.assertIn(username.encode(), response.data)

    def test_historical_audit_emails_are_redacted_in_html_and_json(self):
        import json
        email = 'private.person@example.com'
        action = 'privacy_' + self._unique_suffix()
        db = get_session()
        try:
            db.add(AuditLogDB(action=action, username=email, success=False,
                             details=json.dumps({'email': email, 'nested': [
                                 {'reason': f"Email '{email}' is already registered."}]})))
            db.commit()
        finally:
            db.close()
        for path in ('/admin/audit-logs', '/admin/api/audit-logs'):
            response = self.client.get(path, query_string={'action': action})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(email.encode(), response.data)
            self.assertIn(b'[email hidden]', response.data)
        # Privacy filtering must not destroy the original audit record.
        from app.security import AuditService
        entries, _ = AuditService.get_logs(action=action)
        self.assertEqual(entries[0]['username'], email)
