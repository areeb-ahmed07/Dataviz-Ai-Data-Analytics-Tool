"""Compatibility shim for Render's default start command.

When a Render web service is created manually in the dashboard instead of from
``render.yaml``, Render pre-fills the start command with::

    gunicorn your_application:app

A manually created service never reads the blueprint, so that placeholder
survives every deploy and gunicorn fails at startup with::

    ModuleNotFoundError: No module named 'your_application'

This module satisfies the name by re-exporting the exact WSGI application that
``wsgi:app`` exposes, so the service boots with either start command:

    gunicorn your_application:app      # Render's placeholder
    gunicorn ... --bind 0.0.0.0:$PORT wsgi:app   # what render.yaml sets

Gunicorn makes this importable: its ``--chdir`` setting defaults to the startup
directory and ``Application.chdir()`` inserts that directory into ``sys.path``,
which is the repository root Render runs the start command from.

Prefer setting the Start Command explicitly in the Render dashboard (or creating
the service from ``render.yaml``); this file only exists so a dashboard-created
service works without that extra step.
"""

from wsgi import app  # noqa: F401

__all__ = ["app"]
