from conftest import BaseTestCase


class TestThemePreference(BaseTestCase):
    def test_saved_theme_applies_across_pages_and_login(self):
        email = f"theme_{self._unique_suffix()}@example.com"
        self.login(email=email)
        for preference in ("dark", "light", "system"):
            response = self.client.post('/settings', data={
                'action': 'update_preferences', 'theme': preference,
                'notifications_enabled': 'on',
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            marker = f'data-theme-preference="{preference}"'.encode()
            self.assertIn(marker, response.data)
            for path in ('/dashboard', '/settings?tab=account', '/'):
                self.assertIn(marker, self.client.get(path).data)
        self.logout()
        self.login_with(email, 'TestPass123!')
        self.assertIn(b'data-theme-preference="system"', self.client.get('/dashboard').data)

    def test_guest_defaults_to_light(self):
        self.assertIn(b'data-theme-preference="light"', self.client.get('/login').data)

    def test_toolbar_switch_saves_only_theme(self):
        self.login()
        self.client.post('/settings', data={
            'action': 'update_preferences', 'theme': 'light',
            'notifications_enabled': 'off',
        })
        for theme in ('dark', 'light'):
            response = self.client.post('/settings/theme', json={'theme': theme})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {'theme': theme})
            self.assertIn(f'data-theme-preference="{theme}"'.encode(), self.client.get('/dashboard').data)
        from auth.database import get_session, UserDB
        with self.client.session_transaction() as session:
            user_id = session['user_id']
        db = get_session()
        try:
            self.assertFalse(db.query(UserDB).filter_by(id=user_id).one().notifications_enabled)
        finally:
            db.close()
        self.assertEqual(self.client.post('/settings/theme', json={'theme': 'invalid'}).status_code, 400)
