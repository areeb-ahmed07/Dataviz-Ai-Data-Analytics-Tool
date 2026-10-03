# DataViz Pro

A Flask application for dataset analysis, cleaning, interactive charts, machine learning, time-series analysis, and reports. The browser interface uses Jinja templates and JavaScript; SQLAlchemy manages persistence.

## Run locally

From the project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Only create this file if you do not already have one:
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000. Keep a stable `SECRET_KEY` in `.env`. Explicit process environment settings take precedence over `.env` defaults. See [OAuth setup](docs/oauth.md) for Google and GitHub sign-in. Users and administrators share `/login`; `scripts/configure_admin.py` manages the administrator account.

## Project layout

| Location | Responsibility |
| --- | --- |
| `run.py`, `config.py` | Application entry point and environment configuration |
| `app/` | Flask factory, routes, web services, templates, and static assets |
| `auth/` | Database models, account services, and saved projects |
| `core/`, `connectors/` | Dataset profiling and data sources |
| `cleaner/` | Data cleaning operations |
| `ml/` | Training, evaluation, model export, and explainability |
| `ai_engine/`, `nlg/`, `timeseries/` | Insights, document generation, and time-series engines |
| `migrations/` | Database migration history |
| `scripts/` | Maintenance utilities |
| `tests/` | Automated checks |
| `docs/` | Architecture, OAuth, and cleanup notes |

See [architecture](docs/architecture.md) for module boundaries and [cleanup notes](docs/cleanup.md) for removed migration leftovers.

## Development checks

See [workflow features](docs/workflows.md) for saved workspaces, CSV predictions, and training progress, including current limits.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
node --test tests/theme.test.cjs
```

Python test discovery is restricted to `tests/`. The shared test setup selects a temporary SQLite database before application imports, so it cannot select your live database through `.env`. Node is needed only for the JavaScript checks.

## Runtime data

Keep `.env`, `dataviz_pro.db` (including SQLite WAL/SHM files), `uploads/`, `reports/`, `app/static/reports/`, `ml_models_storage/`, and `saved_projects/`. These are local credentials or user data, not source clutter. They are excluded from Git and Docker build contexts. Back up the database together with its associated uploaded and generated files.

## Deployment

`run.py` provides the development server. The Dockerfile uses Gunicorn on Linux, runs as a non-root user, and exposes port 5000. Supply environment secrets and persistent storage when deploying; configure HTTPS and matching OAuth callback URLs for the public address.

### Deploying to Vercel

The root `vercel.json` routes requests to `api/index.py`, which exports the production Flask app. Vercel installs the root `requirements.txt` for the Python function.

Configure a stable `SECRET_KEY` in Vercel's project environment variables. For persistent user accounts and data, also configure `DATABASE_URL` to a hosted PostgreSQL database; the SQLite fallback under `/tmp` is temporary and can be lost between function instances. Uploads and generated reports also use `/tmp` by default on Vercel, so they are temporary; use persistent object storage before relying on those features in production.

This project has a large scientific/ML dependency set in `requirements.txt`. If deployment fails while installing packages or reports that the function bundle is too large, the Vercel build/runtime log is needed to identify which dependencies or feature routes must be separated. Vercel serverless functions are also not a good fit for long-running model training.
