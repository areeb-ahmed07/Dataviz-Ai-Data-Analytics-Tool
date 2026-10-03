from unittest.mock import patch, MagicMock
from conftest import BaseTestCase
from app.oauth import resolve_identity
from auth.database import get_session, UserDB


class TestSocialAuth(BaseTestCase):
    def test_missing_provider_is_handled(self):
        with patch('app.oauth.get_client', return_value=None):
            response = self.client.get('/auth/google', follow_redirects=True)
            self.assertIn(b'not configured', response.data)

    def test_verified_identity_reused_and_disabled_blocked(self):
        suffix = self._unique_suffix()
        email = f'oauth{suffix}@example.com'
        user = resolve_identity('github', suffix, email, 'Test OAuth')
        self.assertEqual(user.role.value, 'user')
        self.assertEqual(user.id, resolve_identity('github', suffix, email, 'Test OAuth').id)
        with self.assertRaises(ValueError):
            resolve_identity('google', suffix, email, 'Another identity')
        db = get_session()
        try:
            db.get(UserDB, user.id).is_active = False
            db.commit()
        finally:
            db.close()
        with self.assertRaises(ValueError):
            resolve_identity('github', suffix, email, 'Test OAuth')

    def test_callback_failure_and_unverified_email(self):
        client = MagicMock()
        client.authorize_access_token.side_effect = RuntimeError('invalid state')
        with patch('app.oauth.get_client', return_value=client):
            self.assertEqual(self.client.get('/auth/google/callback').status_code, 302)
        client.authorize_access_token.side_effect = None
        client.authorize_access_token.return_value = {'userinfo': {'sub': 'abc', 'email_verified': False}}
        with patch('app.oauth.get_client', return_value=client):
            self.client.get('/auth/google/callback')
        with self.client.session_transaction() as session:
            self.assertFalse(session.get('authenticated'))

    def test_shared_login_keeps_admin_access_restricted(self):
        suffix = self._unique_suffix()
        email = f'regular{suffix}@example.com'
        self.register(email=email)
        self.logout()
        self.assertEqual(self.client.get('/admin/login').location, '/login')
        response = self.client.post('/login', data={'email': email, 'password': 'TestPass123!'})
        self.assertEqual(response.location, '/dashboard')
        self.assertEqual(self.client.get('/admin/users').status_code, 403)
        self.logout()
        from auth.security import hash_password
        db = get_session()
        try:
            account = db.query(UserDB).filter_by(email=email).one()
            account.role = 'admin'
            db.commit()
        finally:
            db.close()
        response = self.client.post('/login', data={'email': email, 'password': 'TestPass123!'})
        self.assertEqual(response.location, '/admin/users')
        self.assertEqual(self.client.get('/admin/users').status_code, 200)

    def test_verified_google_callback_sets_session(self):
        suffix = self._unique_suffix()
        client = MagicMock()
        client.authorize_access_token.return_value = {'userinfo': {
            'sub': f'google{suffix}', 'email': f'google{suffix}@example.com',
            'email_verified': True, 'name': 'Google Test',
        }}
        with patch('app.oauth.get_client', return_value=client):
            response = self.client.get('/auth/google/callback')
        self.assertEqual(response.location, '/dashboard')
        with self.client.session_transaction() as session:
            self.assertTrue(session['authenticated'])
            self.assertEqual(session['role'], 'user')

    def test_real_client_rejects_callback_without_state(self):
        if not self.app.extensions.get('social_oauth'):
            self.skipTest('Authlib download unavailable')
        self.app.config.update(GOOGLE_CLIENT_ID='test', GOOGLE_CLIENT_SECRET='test')
        response = self.client.get('/auth/google/callback?code=fake&state=missing')
        self.assertEqual(response.location, '/login')
        with self.client.session_transaction() as session:
            self.assertFalse(session.get('authenticated'))
