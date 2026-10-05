"""WSGI entry point for production servers.

Gunicorn is given a plain ``module:attribute`` target, so the start command
needs no shell quoting around a factory call:

    gunicorn --worker-class gthread --workers 1 --threads 4 \\
             --timeout 120 --bind 0.0.0.0:$PORT wsgi:app

The Dockerfile keeps using ``app:create_app('production')`` because it runs in
exec form and Hugging Face Spaces depends on that image binding port 5000.
"""

from app import create_app

app = create_app("production")
