---
title: DataViz Pro
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 5000
---

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

### Free public demo on Hugging Face Spaces

Create a new Space, select **Docker**, then push this repository's files to the Space repository. The Space metadata above selects the Docker SDK and configures the public app port to match the Dockerfile.

In the Space's **Settings → Variables and secrets**, set a stable `SECRET_KEY`. The app uses local SQLite by default, and uploads and generated reports are stored on the container filesystem. Space filesystem data is temporary and can be lost when the Space restarts or rebuilds, so use this only as a demo; do not store important or private user data there. For persistent data, configure a hosted database and external file storage.

### Deploying to Vercel

The root `vercel.json` routes requests to `api/index.py`, which exports the production Flask app. Vercel installs the root `requirements.txt` for the Python function.

Configure a stable `SECRET_KEY` in Vercel's project environment variables. For persistent user accounts and data, also configure `DATABASE_URL` to a hosted PostgreSQL database; the SQLite fallback under `/tmp` is temporary and can be lost between function instances. Uploads and generated reports also use `/tmp` by default on Vercel, so they are temporary; use persistent object storage before relying on those features in production.

This project has a large scientific/ML dependency set in `requirements.txt`. If deployment fails while installing packages or reports that the function bundle is too large, the Vercel build/runtime log is needed to identify which dependencies or feature routes must be separated. Vercel serverless functions are also not a good fit for long-running model training.

### Deploying to Render

The repository includes a `render.yaml` blueprint that targets Render's native Python runtime.

1. Push this repository to GitHub.
2. In the Render Dashboard choose **New + → Blueprint** and select the repository. Render reads `render.yaml`, creates the `dataviz-pro` web service, and generates a stable `SECRET_KEY`.
3. Apply the blueprint. The first build installs the full scientific/ML dependency set and takes several minutes.

The start command binds to the port Render assigns through `$PORT`:

```
gunicorn --worker-class gthread --workers 1 --threads 4 --timeout 120 \
         --bind 0.0.0.0:$PORT "app:create_app('production')"
```

`/health` is the health-check path. `PYTHON_VERSION` (and `.python-version`) pin Python 3.11.9; change both if you need a different interpreter. Set `OPENAI_API_KEY` in the dashboard to enable the AI features — it is declared with `sync: false` so it is never committed.

**First run and the administrator account.** The database starts empty. The first time the auth service is constructed it seeds an `admin` account with a cryptographically random password and prints it once to standard output:

```
[AuthService] Seeded default admin: admin / <password>
```

On Render, open the service's **Logs** tab, copy that password, and sign in at `/login` using the username `admin`. Because free instances have ephemeral storage, the database is wiped on every deploy and restart, so this line is re-emitted with a **new** password each time — always take the latest value from the logs. Seeding is skipped as soon as any user exists.

**Storage on the free plan.** Render's free instances have an ephemeral filesystem. `dataviz_pro.db`, `uploads/` and `reports/` are recreated on every deploy and restart, so user accounts, uploaded datasets and generated reports do not survive, and free services spin down after 15 minutes of inactivity. Treat a free Render deploy as a public demo only.

To make a Render deployment persistent:

- Move the service to a paid instance type and attach a disk — disks are not available on free instances. Then set `UPLOAD_FOLDER` and `REPORTS_FOLDER` to directories inside the mount.
- For the database, either point `DATABASE_URL` at a file on that same disk, or configure a Render Postgres instance. Note that Postgres covers only accounts and metadata; uploads and reports still require the disk.

`DATABASE_URL` accepts any SQLAlchemy URL. Use a `postgresql://…` scheme — SQLAlchemy 2.0 rejects the legacy `postgres://` form.
