# Architecture

## Request flow

Browser requests enter a Flask blueprint in `app/routes/`. Routes handle request validation and access control, call workflows in `app/services/`, and return templates or JSON. Workflows reuse the analysis packages and SQLAlchemy persistence in `auth/`.

## Module boundaries

- `app/routes/`: HTTP requests, authentication requirements, responses.
- `app/services/`: workflows that connect web features to data engines.
- `core/`, `cleaner/`, `ml/`, `ai_engine/`, `nlg/`, `timeseries/`, `connectors/`: reusable analysis and data operations.
- `auth/database.py` and `auth/services/`: persisted records and account/project operations.
- `app/templates/`, `app/static/`: presentation. Shared theme styling belongs in `theme.css`; feature-specific styling belongs in the feature stylesheet.

Keep existing top-level analysis package names stable: exported model objects may refer to their Python import paths. A package move requires explicit compatibility and saved-model validation. Runtime storage locations also remain stable to preserve existing database file references.

## Configuration and tests

`config.py` loads local `.env` defaults without replacing explicit process settings. `create_app()` selects the Flask configuration. Tests select an isolated temporary SQLite database before importing the application. Developer dependencies live in `requirements-dev.txt`.

## Persistence

`migrations/` retains schema history. Startup also contains schema compatibility initialization; consolidating this into a migration-only deployment is a separate change requiring database upgrade checks. User data directories are excluded from source control and container build contexts, and must be backed up separately.
