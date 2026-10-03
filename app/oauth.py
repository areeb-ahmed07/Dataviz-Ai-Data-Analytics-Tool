"""Provider sign-in with Authlib state/nonce validation and stable identities."""
import os
import secrets
from flask import Blueprint, current_app, flash, redirect, session, url_for
from auth.database import get_session, UserDB, OAuthIdentityDB
from auth.security import hash_password
from app.auth_helpers import set_session_user

oauth_bp = Blueprint('oauth', __name__)


def init_oauth(app):
    app.register_blueprint(oauth_bp)
    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError:
        app.logger.warning('Provider sign-in requires Authlib: install project requirements.')
        app.extensions['social_oauth'] = None
        return
    oauth = OAuth(app)
    for provider in ('google', 'github'):
        for suffix in ('CLIENT_ID', 'CLIENT_SECRET'):
            key = f'{provider.upper()}_{suffix}'
            app.config[key] = os.environ.get(key, app.config.get(key, ''))
    oauth.register('google', server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                   client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256'})
    oauth.register('github', authorize_url='https://github.com/login/oauth/authorize',
                   access_token_url='https://github.com/login/oauth/access_token',
                   api_base_url='https://api.github.com/', client_kwargs={'scope': 'read:user user:email'})
    app.extensions['social_oauth'] = oauth


def resolve_identity(provider, subject, email, name):
    if not subject or not email or '@' not in email:
        raise ValueError('A verified email address is required to sign in.')
    db = get_session()
    try:
        identity = db.get(OAuthIdentityDB, (provider, subject))
        if identity:
            user = db.get(UserDB, identity.user_id)
        else:
            # Never silently link a provider to an existing password/admin account.
            if db.query(UserDB).filter_by(email=email.lower()).first():
                raise ValueError('This email already has an account. Please sign in with its existing login method.')
            user = UserDB(username=f'{provider}_{secrets.token_hex(8)}', email=email.lower(),
                          full_name=(name or provider.title() + ' user')[:100],
                          hashed_password=hash_password(secrets.token_urlsafe(32)), role='user', is_active=True)
            db.add(user)
            db.flush()
            db.add(OAuthIdentityDB(provider=provider, subject=subject, user_id=user.id))
        if not user or not user.is_active:
            raise ValueError('This account is disabled. Contact an administrator.')
        db.commit()
        return user.to_domain()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_client(provider):
    if not current_app.extensions.get('social_oauth'):
        return None
    if provider not in ('google', 'github'):
        return None
    if not all(current_app.config.get(f'{provider.upper()}_{suffix}') for suffix in ('CLIENT_ID', 'CLIENT_SECRET')):
        return None
    return current_app.extensions['social_oauth'].create_client(provider)


@oauth_bp.route('/auth/<provider>')
def login(provider):
    client = get_client(provider)
    if client is None:
        flash('This sign-in provider is not configured yet. Please use your username and password.', 'error')
        return redirect(url_for('auth.login'))
    return client.authorize_redirect(url_for('oauth.callback', provider=provider, _external=True))


@oauth_bp.route('/auth/<provider>/callback')
def callback(provider):
    client = get_client(provider)
    if client is None:
        return redirect(url_for('auth.login'))
    try:
        token = client.authorize_access_token()
        if provider == 'google':
            info = token['userinfo']  # Authlib validates the signed ID token and nonce.
            if info.get('email_verified') is not True:
                raise ValueError('Please verify your Google email before signing in.')
            subject, email, name = info['sub'], info.get('email'), info.get('name')
        else:
            response = client.get('user', token=token)
            response.raise_for_status()
            info = response.json()
            response = client.get('user/emails', token=token)
            response.raise_for_status()
            emails = response.json()
            verified = next((entry for entry in emails if entry.get('primary') and entry.get('verified')), None)
            if not verified:
                raise ValueError('Please verify your primary GitHub email before signing in.')
            subject, email, name = str(info['id']), verified['email'], info.get('name') or info.get('login')
        user = resolve_identity(provider, subject, email, name)
        session.clear()
        set_session_user(user)
        return redirect(url_for('dashboard.dashboard'))
    except ValueError as error:
        flash(str(error), 'error')
    except Exception:
        current_app.logger.warning('Provider sign-in failed for %s', provider)
        flash('Sign-in could not be completed. Please try again.', 'error')
    return redirect(url_for('auth.login'))
