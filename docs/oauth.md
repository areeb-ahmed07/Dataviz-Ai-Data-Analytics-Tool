# Google and GitHub sign-in

Install requirements, then put these values in the project's local `.env`:

```dotenv
SECRET_KEY=<a stable random secret>
GOOGLE_CLIENT_ID=<Google web application client ID>
GOOGLE_CLIENT_SECRET=<Google client secret>
GITHUB_CLIENT_ID=<GitHub OAuth app client ID>
GITHUB_CLIENT_SECRET=<GitHub OAuth app client secret>
```

Register these exact callback URLs for local use:

- Google: `http://127.0.0.1:5000/auth/google/callback`
- GitHub: `http://127.0.0.1:5000/auth/github/callback`

Use the same hostname when opening the app. For a deployed site, register the corresponding HTTPS URLs. Restart after configuring credentials. Do not commit `.env`.

Google uses OpenID Connect with verified email and nonce validation. GitHub requests read-only profile and email access and requires a verified primary email. Returning accounts are identified by provider ID. Existing email accounts are not automatically linked to avoid granting access to a password or admin account via a different sign-in method.

Administrators and users both sign in at `/login`. Administrators are redirected to user management after sign-in. To explicitly create or reset the admin account later, run `python scripts/configure_admin.py` and enter the desired password. This is a one-time operation; app startup does not reset it.

References: https://docs.authlib.org/en/latest/oauth2/client/web/flask.html and https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app
