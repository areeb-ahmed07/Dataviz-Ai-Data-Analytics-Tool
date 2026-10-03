# Migration cleanup — 2026-09-19

## Removed from the active tree

| Files | Reason |
| --- | --- |
| `setup_templates.py`, `fix_templates.py` | One-off migration generators tied to an old drive path |
| `test_comp.py`, `test_full.py`, `test_train.py`, `tmp_ml_smoke.py`, `tests/ml_taxis_smoke.py` | Scratch scripts with stale calls or operations against real application data; maintained automated tests remain in `tests/` |
| `auth/dependencies.py` | Unused FastAPI dependency module in the Flask application |
| `assets/bg.jpg`, `assets/logo.png` | Unreferenced legacy assets; current branding remains in `app/static/img/` |
| `app/static/img/dataviz-logo-home.png` | Byte-identical duplicate; the homepage now uses the shared logo |

Removed files were verified against a source archive before deletion:

`C:\Users\imbad\.codex\visualizations\2026\09\15\01a0a3f3-02b6-7a80-9616-74af193663fa\dataviz-source-before-cleanup-20260919.zip`

Restore a removed file using its relative path inside the archive. This archive is not a backup of credentials or user data.

## Organization and safeguards

- Replaced obsolete Streamlit/FastAPI setup documentation with current Flask instructions.
- Grouped architecture and OAuth documentation under `docs/`.
- Added development requirements and explicit test discovery.
- Isolated the shared test database from local `.env` settings.
- Excluded runtime data and local environments from Docker builds and source control.
- Made container application directories writable by its non-root user.
- Selected the production Flask configuration in the container entry point.
- Consolidated identical reporting dark-theme rules into `reports.css`.
- Reset the in-memory rate limiter between test cases and use unique test account identifiers.
- Updated the stale tuning-budget test to validate the discrete grids used by the current tuner.

The Python environment, credentials, database, uploads, reports, saved models, saved projects, active analysis packages, and migration history are retained.

## Verification

- Python suite: 174 passed, with 18 subtests passing. Existing dependency/deprecation warnings remain.
- JavaScript theme suite: 6 passed.
- Live homepage: HTTP 200 and references the shared logo.
- Generated Python/pytest caches removed after verification. They regenerate as the app runs.
- Docker build configuration was reviewed; a container image was not built during this cleanup.
