# DataViz Pro Project Documentation

Technical documentation and final year project report

Application version 2.0.0  
Documentation date 19 September 2026

## Abstract

DataViz Pro is a browser-based application for exploring structured datasets and carrying out common data science tasks in one workspace. It brings together data import, profiling, cleaning, interactive visualization, machine learning, model explanation, time series analysis, and report generation. The application uses Flask for its web layer, pandas and NumPy for data processing, scikit-learn for machine learning, and SQLAlchemy for persistent records. Dataset files and trained model bundles are stored separately on the filesystem.

The project addresses the effort involved in moving between spreadsheets, notebooks, plotting tools, and reporting software. Users can inspect the quality of an uploaded dataset, preserve a cleaned version, compare predictive models, and export findings without writing a separate program for each stage. Administrators can manage accounts and inspect audit records.

The implemented system is a modular Flask application. Its active AI Copilot produces statistical and rule-based insights; a complete conversational assistant and natural-language dashboard generation are not part of the verified active workflow. Forecasting and some model explanations depend on additional libraries. This document explains the implemented design, installation process, user workflows, test coverage present in the repository, and known limitations relevant to a project demonstration or handover.

## Contents

1. Project background and objectives
2. Scope and requirements
3. System architecture
4. Database and file storage
5. Functional modules
6. Machine learning methodology
7. Interface and API reference
8. Installation and configuration
9. User guide
10. Security and operational considerations
11. Testing and evaluation
12. Known limitations
13. Future development
14. Demonstration and handover
15. Source reference and glossary

## 1 Project background and objectives

### Problem statement

Tabular data often contains missing values, repeated records, inconsistent types, and unusual observations. These problems can distort charts and model evaluation. A user may also need several independent tools to clean the data, explore relationships, train models, and prepare a report. Repeating these steps manually makes it harder to preserve the relationship between a dataset, its transformations, and the resulting analysis.

DataViz Pro provides a shared workflow for those tasks. It is intended for students, analysts, and small teams working with structured datasets. The interface exposes common operations while the service layer manages validation, analysis, and persistence.

### Objectives

- Import supported files and data obtained from databases or REST APIs.
- Describe dataset structure and identify quality issues before analysis.
- Preview cleaning operations and save cleaned data as a separate version.
- Create interactive charts with explicit column and aggregation choices.
- Compare classification and regression models and explore clustering.
- Explain supported saved models using feature importance and local explanations.
- Generate downloadable reports from computed analysis results.
- Associate datasets, models, and saved charts with individual user accounts.

### Project contribution

The main contribution is the integration of data preparation, analysis, model comparison, explanation, and reporting in a browser interface. The project reuses established statistical methods and machine learning libraries; it does not introduce a new learning algorithm. Its academic value can be evaluated through workflow design, modular implementation, validation, reproducibility, and the quality of its experiments.

## 2 Scope and requirements

### Supported scope

The application works with structured data that can be represented as a pandas DataFrame. It accepts CSV, XLSX, XLS, JSON, and Parquet extensions. XLS and Parquet require compatible reader packages in addition to the main requirements. Database connector modules cover SQLite, PostgreSQL, and MySQL, and a REST connector supports importing API data.

“Any data” should be understood as compatible structured data, not arbitrary images, audio, video, scanned documents, or every JSON structure. The suitability of a dataset for forecasting or machine learning also depends on its columns, sample size, and data quality.

### Actors

| Actor | Main responsibilities |
| --- | --- |
| Visitor | View the landing page and access registration or sign-in |
| Registered user | Import and manage personal datasets, clean data, analyze, train models, create charts, and generate reports |
| Administrator | Manage account roles and activation status and inspect audit logs |
| External provider | Supply authorized database/API data or complete configured Google/GitHub sign-in |

### Functional requirements

| ID | Requirement | Implementation reference |
| --- | --- | --- |
| FR01 | Register users and authenticate browser sessions | `app/routes/auth.py`, `app/auth_helpers.py` |
| FR02 | Import, preview, download, and delete datasets | `app/routes/datasets.py` |
| FR03 | Produce quality summaries and descriptive analysis | `app/services/analysis_service.py` |
| FR04 | Preview, apply, undo, reset, and save cleaning operations | `app/services/cleaning_service.py` |
| FR05 | Build charts and save their configurations | `app/routes/visualization.py` |
| FR06 | Configure, prepare, train, compare, and tune ML experiments | `app/services/ml_service.py` |
| FR07 | Save and export supported supervised models | `app/services/ml_service.py` |
| FR08 | Explain supported saved models and predictions | `app/services/xai_service.py` |
| FR09 | Analyze a selected date column and numeric series | `app/routes/timeseries.py` |
| FR10 | Produce automated trends, anomalies, and recommendations | `app/routes/copilot.py`, `ai_engine/` |
| FR11 | Export analytical reports in multiple formats | `app/services/report_service.py` |
| FR12 | Manage users and inspect audit records | `app/routes/admin.py` |

These requirements describe code paths present in the application. They do not imply that every workflow has passed an acceptance test in the deployment environment.

### Nonfunctional requirements

The design aims to keep data associated with its owner, provide meaningful validation errors, separate web handling from analytical code, and preserve model configuration alongside results. Caches reduce repeated processing, and background threads allow the interface to poll for training progress. Deployment must provide writable storage and enough memory for the selected dataset and algorithms.

No measured throughput, maximum concurrent-user count, uptime guarantee, or response-time benchmark is established here. These should be measured with representative datasets before making performance claims.

## 3 System architecture

### Architectural style

DataViz Pro is a modular monolith: one Flask application contains multiple functional modules. `run.py` creates the application through `app.create_app()`. The factory loads configuration, registers blueprints, initializes database tables, configures CSRF protection, and installs error handlers and response headers.

The browser receives HTML rendered with Jinja templates. JavaScript requests analysis and workflow data from Flask endpoints and updates the interface. Plotly is loaded in the visualization workspace for interactive charts. Route handlers call application services, which coordinate the analytical modules and persistence layer.

```text
Browser
  HTML pages, CSS, JavaScript, interactive charts
                        |
Flask application factory and route blueprints
  Authentication, dataset ownership checks, request validation
                        |
Application services
  Datasets | Analysis | Cleaning | ML | XAI | Reports
                        |
Analytical modules
  core | cleaner | ml | timeseries | nlg | ai_engine | connectors
                        |
Persistence
  SQLAlchemy metadata database + dataset files + model/report files
```

### Main layers

The route layer is responsible for HTTP input, authentication checks, responses, and template selection. Services implement operations that may be called by several routes. Domain objects represent configuration and results. Analytical modules perform the underlying transformations and computations. SQLAlchemy models and filesystem paths retain the results needed after an application restart.

This separation makes it possible to test chart transformations or model-building logic without interacting with the complete interface. However, several workflows still keep their intermediate state in process memory, so the architecture is not yet a distributed worker system.

### Repository organization

```text
Dataviz/
  run.py                 Application entry point
  config.py              Development, production, and testing configuration
  requirements.txt       Application dependencies
  app/
    routes/              Flask page and JSON handlers
    services/            Workflow orchestration
    domain/              Dataset and ML workflow objects
    core/                Cache infrastructure
    templates/           Jinja HTML templates
    static/              CSS, JavaScript, images, generated reports
    oauth.py             Google and GitHub sign-in
    security.py          Validation, rate limits, audit helpers, headers
  auth/                  SQLAlchemy models and authentication services
  cleaner/               Cleaning operations and pipeline history
  connectors/            File, database, and API connectors
  core/                  Data analysis and quality logic
  ml/                    Model registry, comparison, tuning, and exports
  timeseries/            Stationarity, seasonality, and forecasting
  nlg/                   Natural-language insight generation
  ai_engine/             Analytical insights and report generators
  migrations/            Alembic migration configuration and revisions
  scripts/               Administrative utilities
  tests/                 Automated tests and fixtures
  uploads/               Uploaded and derived dataset files
  ml_models_storage/     Serialized model bundles
  docs/                  Project documentation
```

### Data flow

A typical workflow starts with an authenticated upload. The application validates the file, stores it, and creates a dataset record. Analysis services load that file into a DataFrame. Cleaning operates on a working copy; saving produces a child dataset with its own metadata. Charts and ML experiments then use the selected dataset version. A saved supervised model retains its estimator and preprocessor, while reports gather analysis outputs and generate downloadable files.

The selected dataset version matters. Cleaning a working copy does not imply that every other module is using that unsaved copy. Users should save the cleaned version and select it explicitly for subsequent analysis or training.

## 4 Database and file storage

### Metadata schema

The database schema is defined in `auth/database.py`. SQLite is the default local database. SQLAlchemy creates an engine from `DATABASE_URL`; using another database requires its driver and compatibility testing. For SQLite connections, the code enables foreign keys, WAL mode, and a busy timeout.

| Table | Key fields | Purpose |
| --- | --- | --- |
| `users` | `id`, unique `username`, unique `email`, `hashed_password`, `role`, `is_active` | Identity, access role, and preferences |
| `oauth_identities` | Composite key `provider` and `subject`, `user_id` | Stable external identity mapping |
| `projects` | `id`, `user_id`, `project_name`, `dataset_path` | Saved project metadata |
| `datasets` | `id`, `user_id`, `storage_path`, `file_format`, `parent_dataset_id` | File metadata, profile summaries, and version lineage |
| `analyses` | `id`, `user_id`, nullable `project_id`, `summary_metrics`, `report_path` | Recorded analysis summaries |
| `ml_models` | `id`, `user_id`, nullable `dataset_id`, `algorithm`, `metrics`, `model_path`, `version` | Saved model metadata and experiment details |
| `saved_charts` | `id`, `user_id`, `dataset_id`, `chart_type`, `config` | Reusable chart specifications |
| `audit_logs` | `id`, nullable `user_id`, `action`, `resource_id`, `success` | Recorded application and administrative events |
| `login_attempts` | `id`, `identifier`, `ip_address`, `success`, `created_at` | Sign-in attempt records |

### Relationships

```text
User 1 ---- many Datasets
User 1 ---- many Projects ---- many Analyses
User 1 ---- many Models
User 1 ---- many Saved Charts
User 1 ---- many OAuth Identities

Dataset 1 ---- many child Datasets through parent_dataset_id
Dataset 1 ---- many Models
Dataset 1 ---- many Saved Charts
```

Foreign-key actions vary by relationship. For example, deleting a dataset sets its related model's dataset reference to null, while saved charts use a cascading database relationship. Physical file cleanup is a separate application responsibility; a database relationship alone does not remove files.

### Storage conventions

Uploads are stored under the configured upload directory, with user-specific paths. Dataset records store their actual file paths. Cleaned dataset versions retain a parent reference and serialized cleaning information. ML Studio writes supervised model bundles to `ml_models_storage/` using joblib. Each bundle includes the model, preprocessing object, feature columns, target metadata, and metrics.

The report service currently writes into `app/static/reports/<user_id>/`. Although `config.py` defines `REPORTS_FOLDER`, that setting does not control the report service's active output path. This difference matters for backups, permissions, and deployment security.

### Persistent and temporary state

Database rows and saved files persist across restarts. Cleaning sessions, ML workflow state, background-job status, and caches are held in application memory. A restart can therefore discard unsaved changes or running-job information even when uploaded data and saved models remain available.

## 5 Functional modules

### Authentication and administration

Users register and sign in through Flask routes. Passwords are hashed with bcrypt. Browser authentication uses Flask sessions; JWT helpers exist in the repository but are not the principal browser sign-in mechanism. Without an additional session backend, Flask's default session is a signed client-side cookie, not a server-side session store.

Google and GitHub sign-in are implemented through Authlib and require configured provider credentials. The identity table associates provider subjects with local accounts. The implementation requires verified email information and does not silently attach a new provider identity to an existing account with the same email address.

Administrators have routes for listing users, changing roles, enabling or disabling accounts, and viewing audit logs. The explicit `scripts/configure_admin.py` utility creates or resets an administrator when an operator runs it.

### Dataset management

The dataset workflow validates the file extension, upload size, and selected binary signatures before parsing. Metadata includes dimensions, file format, column information, and quality summaries. Users can list, preview, rename or describe, download, and delete their datasets.

The default request-size limit is 52,428,800 bytes, approximately 50 MiB. This is an upload limit, not a promise that every accepted dataset can be processed efficiently. Memory use may exceed the original file size once pandas loads and copies the data.

### Exploratory analysis

Analysis views cover an overview, data quality, descriptive statistics, correlations, distributions, outliers, categorical columns, time-oriented summaries, and narrative insights. The analysis loader checks dataset ownership before reading a stored file.

Many analysis operations sample datasets above 50,000 rows using a fixed random seed of 42. The preview constant is 100 rows. Consequently, a statistic in an analysis or report can describe a sample rather than the entire uploaded dataset. This distinction should be stated when presenting conclusions.

### Cleaning and preparation

The cleaning service wraps operations for duplicate removal, missing-value treatment, outlier handling, categorical encoding, and scaling. It also supports column renaming, selection or removal, type conversion, constant-column removal, and selected transformations.

The working pipeline retains an audit history and intermediate DataFrame states for undo and reset. Users can preview an operation, apply it, inspect the changed dimensions or missing-value counts, and save a new version. The original dataset remains a separate record.

Cleaning decisions must follow the meaning of the data. An unusual transaction is not automatically erroneous, and replacing a missing value with an average is not appropriate for every column. Previewing changes provides an opportunity to review their effect before saving.

### Visualization

The chart service supports bar, line, scatter, pie, histogram, box, violin, heatmap, correlation, and treemap data. Aggregations include count, sum, mean, minimum, and maximum where the chart type supports them. It validates column choices and numeric requirements, handles nonfinite values for JSON output, and sorts line-chart data by its X column.

Chart configurations can be saved with a dataset reference. Saving a chart retains its configuration; it should not be described as creating a complete dashboard from a natural-language prompt.

### Automated insights

The active Copilot route invokes `AIEngine.run_full_ai_analysis()` and returns trends, anomalies, candidate root causes, and recommendations. These outputs come from statistical and rule-based analysis. A label such as “root cause” should be interpreted as a suggested association or segment difference to investigate, not proof of causation.

The separate `app/services/copilot_service.py` contains a syntax error and is not imported by the active Copilot route. Its conversational features must not be presented as a functioning chat API. Setting `OPENAI_API_KEY` alone does not establish a working conversational integration.

### Time series

Users select a date column and a numeric value column. The route converts values, removes invalid date/value rows, sorts observations by date, and requires at least three valid rows. Individual analyses can still need substantially more observations.

The analyzer uses an augmented Dickey-Fuller test for stationarity and seasonal decomposition when enough data supports a detected period. Forecasting uses Prophet and requests 30 future periods. Prophet is optional and is not listed in the main requirements file. Insufficient observations, constant values, or missing packages may make a particular output unavailable without invalidating all other results.

### Reports

The report service gathers dataset information, quality results, statistics, correlations, distributions, outliers, saved-model information, and narrative insights. The public generation route accepts `pdf`, `html`, `pptx`, `excel`, `word`, `executive`, and `markdown`. Word and Excel produce DOCX and XLSX files respectively; `executive` selects an executive PDF report.

Reports are summaries of available analysis. A generated report does not establish model accuracy independently or guarantee that every optional explanation succeeded. Users should review the selected data, warnings, and reported sample size before sharing it.

## 6 Machine learning methodology

### Workflow

The supervised workflow is configure, prepare, train, review, optionally optimize, then save. Users select a target, features, task type, preprocessing choices, and evaluation settings. Preparation validates the target and split size. Training runs in a thread pool, with a job identifier that the interface polls for progress.

The service splits supervised data before fitting its preprocessor. It fits preprocessing on training data and transforms the test data using that fitted object. This protects the holdout set from direct preprocessing leakage. Cross-validation should also preserve fold-level preprocessing isolation; the presence of a holdout split alone is not proof that every evaluation path is leakage-free.

### Algorithms

| Task | Examples in the registry | Important restriction |
| --- | --- | --- |
| Classification | Logistic Regression, Random Forest, Decision Tree, Extra Trees, Gradient Boosting, Naive Bayes, KNN, SVM | Fast mode exposes a different selection; suitability depends on the data |
| Regression | Linear Regression, Ridge, Random Forest, Decision Tree, Extra Trees, Gradient Boosting, KNN, Lasso, Elastic Net, SVR | Some choices are excluded in fast mode |
| Clustering | K-Means, DBSCAN, Agglomerative, Mini-Batch K-Means, Birch | ML Studio currently rejects saving clustering models |
| Optional boosting | XGBoost and LightGBM integration code | Availability flags are explicitly false in the current registry |

The registry comments cite Windows OpenMP crashes as the reason for disabling XGBoost and LightGBM. Installing their packages does not automatically enable them in the application.

### Evaluation

Classification results may include accuracy, precision, recall, F1, ROC AUC, and a confusion matrix where applicable. Regression results use measures such as R-squared, mean absolute error, and root mean squared error. Clustering uses internal measures such as silhouette, Calinski-Harabasz, and Davies-Bouldin scores when their mathematical requirements are met.

Accuracy alone can be misleading for an imbalanced classification problem. Error metrics should be interpreted in the units of the target variable. A high clustering score does not demonstrate that clusters correspond to meaningful real-world categories. No universal accuracy claim can be made without a defined dataset, split, baseline, and evaluation method.

### Model persistence and explanations

Saving a supervised model creates a versioned database record and a joblib bundle with its preprocessor and feature metadata. Prediction must use the same feature definitions and preprocessing as training. The service marks older active versions of the same algorithm and dataset inactive when a new version is saved.

The explainability service includes native feature importance, permutation importance, global and local SHAP outputs, LIME explanations, and prediction explanations. Availability depends on the estimator, stored data, and installed libraries. Feature attribution describes a model's behavior; it does not establish causal effects in the underlying domain.

### Recommended experimental protocol

For an FYP evaluation, choose a documented dataset, define a target and baseline, record the dataset version, and preserve the random seed and split configuration. Compare several suitable models using the same evaluation protocol. Include an error analysis and explain at least one successful and one incorrect prediction. Record failures and unavailable explanations alongside successful results rather than omitting them.

## 7 Interface and API reference

### Browser pages

| Path | Purpose |
| --- | --- |
| `/` | Landing page |
| `/login` and `/signup` | Authentication |
| `/dashboard` | User overview |
| `/datasets` and `/datasets/upload` | Dataset management and import |
| `/analysis/<dataset_id>/overview` | Start dataset analysis |
| `/datasets/<dataset_id>/clean` | Cleaning workspace |
| `/visualization/<dataset_id>/workspace` | Chart builder |
| `/datasets/<dataset_id>/ml` | ML Studio |
| `/models` | Saved supervised models |
| `/models/<model_id>/explain` | Explainability workspace |
| `/time-series/<dataset_id>/workspace` | Time series workspace |
| `/copilot/<dataset_id>/workspace` | Automated insights |
| `/reports/<dataset_id>/workspace` | Report builder |
| `/admin/users` | Administrator user management |

Angle-bracket identifiers represent the corresponding numeric database ID. These are browser routes within the same Flask application, not separate microservices.

### Representative JSON endpoints

| Method | Path | Operation |
| --- | --- | --- |
| GET | `/health` | Application name, version, and basic status |
| GET | `/api/datasets` | List accessible datasets |
| GET | `/api/datasets/<id>` | Dataset detail |
| DELETE | `/api/datasets/<id>` | Delete a dataset |
| GET | `/analysis/api/<id>/overview` | Analysis overview |
| POST | `/api/datasets/<id>/clean/preview` | Preview a cleaning operation |
| POST | `/api/datasets/<id>/clean/apply` | Apply a cleaning operation |
| POST | `/api/datasets/<id>/clean/save` | Persist the cleaned version |
| GET | `/visualization/api/<id>/data` | Prepare chart data |
| POST | `/api/datasets/<id>/ml/configure` | Store ML workflow configuration |
| POST | `/api/datasets/<id>/ml/prepare` | Prepare the selected experiment |
| POST | `/api/datasets/<id>/ml/train` | Start a training job |
| GET | `/api/datasets/<id>/ml/train/status/<job_id>` | Poll training status |
| GET | `/api/datasets/<id>/ml/results` | Retrieve experiment results |
| POST | `/api/datasets/<id>/ml/save` | Save a supervised model |
| GET | `/api/models/<id>/download` | Download a saved model bundle |
| GET | `/api/xai/models/<id>/global/feature-importance` | Global importance data |
| POST | `/time-series/api/<id>/analyze` | Analyze selected time series columns |
| GET | `/copilot/api/<id>/insights` | Generate automated analytical insights |
| POST | `/reports/api/<id>/generate` | Generate a report |

This is a selected reference, not a complete OpenAPI specification. Route prefixes are not uniform: several feature APIs sit under their module prefix rather than beginning with `/api/`.

### Authentication and error behavior

The browser's authenticated session is required for protected workflows. State-changing requests must also satisfy Flask-WTF CSRF validation; JSON calls from the interface should send the CSRF token, commonly through `X-CSRFToken`. A raw API request without a browser session is not automatically authenticated by supplying a JWT from the legacy helper module.

Response shapes differ by route. Many handlers return an `error` field with a 400 or 404 status. Authentication can redirect to the login page, and some framework errors return HTML. Clients should inspect both the status and content type before attempting JSON parsing. The `/health` response is a basic application response, not a deep database or model-service readiness check.

### Cleaning request example

For an authenticated session, the following JSON previews removal of duplicate rows while keeping the first occurrence:

```http
POST /api/datasets/12/clean/preview
Content-Type: application/json
X-CSRFToken: <token from the current page>

{
  "type": "remove_duplicates",
  "keep": "first"
}
```

Replace `12` with a dataset owned by the current account. Previewing does not save a new dataset. Applying the operation and saving the resulting version are separate requests.

### Report request example

```http
POST /reports/api/12/generate
Content-Type: application/json
X-CSRFToken: <token from the current page>

{
  "format": "word"
}
```

A successful response contains `success`, `filename`, `format`, and `download_url`. The exact filename is generated from the dataset and selected output. Follow the returned download URL using the same authenticated session.

### Time series request example

```json
{
  "date_col": "date",
  "val_col": "sales"
}
```

Send this body to `POST /time-series/api/<id>/analyze` only when those columns exist in the selected dataset. The response can contain successful stationarity or raw-series data alongside an unavailable forecast.

## 8 Installation and configuration

### Environment requirements

Use a Python environment compatible with the application dependencies. The source uses syntax requiring Python 3.10 or newer, and the Dockerfile starts from Python 3.11. A current browser, writable local storage, and internet access for installing packages are needed. External providers and CDN-loaded chart assets require network access when used.

For a small demonstration, 8 GB RAM is a practical starting recommendation and 16 GB provides more room for model training. These are planning suggestions, not benchmarked minimum requirements. Large datasets, wide one-hot encodings, and expensive explanations can require more memory.

### Windows local setup

Open PowerShell in the project directory. The following commands create an isolated environment and install the declared dependencies:

```powershell
cd D:\Dataviz
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `.venv` already contains the working project environment, use it rather than recreating it. There is no need to activate the environment when calling its Python executable directly.

Create a local `.env` from `.env.example` if one does not already exist. Preserve existing credentials and configuration. Set a stable random `SECRET_KEY` and a suitable database URL. For example, a local SQLite database in this workspace can use `sqlite:///D:/Dataviz/dataviz_pro.db`. Do not publish the real `.env` file.

A secret can be generated locally with:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated value into the local configuration. Treat it as a secret, not as material for a report or screenshot.

### Configuration reference

| Variable or setting | Role and current behavior |
| --- | --- |
| `SECRET_KEY` | Signs Flask sessions and supports CSRF; a random runtime fallback is used if absent |
| `DATABASE_URL` | SQLAlchemy connection URL; defaults to local SQLite |
| `MAX_CONTENT_LENGTH` | Default 52,428,800-byte upload request limit |
| `APP_BASE_URL` | Application metadata/base URL setting; does not change `run.py` host or port |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Optional Google sign-in credentials |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | Optional GitHub sign-in credentials |
| `OPENAI_API_KEY` | Present in configuration; not sufficient to enable a working conversational service |
| `DEBUG` | Read by the base class; development and production subclasses explicitly override it |
| `SESSION_LIFETIME` | Read in base configuration, but the factory sets the session lifetime to 24 hours |

`config.py` loads the project `.env` with `override=True`, so that file can override existing process environment variables. `FLASK_ENV`, `FLASK_HOST`, and `FLASK_PORT` in the example file do not select the factory configuration or override the explicit host and port in `run.py`.

### Starting the application

```powershell
.\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:5000` in the browser. The entry point binds to `0.0.0.0:5000` and uses the default development configuration. Run it only in a trusted development environment. Application initialization attempts to create the database tables; if initialization fails, inspect the startup warning and database permissions before continuing.

The old root README includes Streamlit and FastAPI commands that do not represent this entry point. Use the Flask commands in this section for the current codebase.

### Optional capabilities

```powershell
.\.venv\Scripts\python.exe -m pip install prophet
.\.venv\Scripts\python.exe -m pip install xlrd pyarrow
.\.venv\Scripts\python.exe -m pip install pytest
```

Prophet enables the implemented forecasting path. `xlrd` supports legacy XLS reading, and `pyarrow` supplies a Parquet engine. Pytest is needed for the test command but is not in the application requirements. Installing these packages does not fix unrelated application errors or enable algorithms that are explicitly disabled in code.

### Social sign-in and administrator setup

Configure the optional provider credentials, register the correct callback URLs, and restart the application. For local use with `127.0.0.1`, the callbacks are:

```text
http://127.0.0.1:5000/auth/google/callback
http://127.0.0.1:5000/auth/github/callback
```

Use the same browser hostname as the registered callback. The repository's `docs/oauth.md` provides the provider-specific setup notes. To explicitly create or reset an administrator, run:

```powershell
.\.venv\Scripts\python.exe scripts\configure_admin.py
```

Enter the administrator password when prompted. This changes the administrator account and should be performed by the project operator, not by every user.

### Deployment guidance

Use an explicit production factory configuration for deployment. On a Linux host with Gunicorn installed, a starting command is:

```sh
gunicorn -w 1 -b 127.0.0.1:5000 --timeout 120 "app:create_app('production')"
```

Place the service behind an HTTPS reverse proxy. Production enables secure session cookies, so the browser connection must use HTTPS. The single worker is a conservative starting point because ML and cleaning state are currently process-local. It is not a performance recommendation based on load testing.

The supplied Dockerfile launches four workers with `create_app()` and therefore the default development configuration. It also switches to a non-root user without an explicit ownership adjustment for application storage. Review its command and writable-volume permissions before deploying it. Do not treat the current image as a verified production deployment.

Alembic files are available, but startup also contains schema initialization logic. Back up an existing database and reconcile its schema with the migration history before applying migrations; do not run migrations blindly against a valuable database.

## 9 User guide

### Import and inspect a dataset

1. Sign in or create an account.
2. Open Datasets and select the upload/import action.
3. Choose a supported file, or provide authorized database/API connection information.
4. Review the dataset preview, column types, and row and column counts.
5. Open the analysis overview and quality views to identify missing values, duplicates, or suspicious fields.

A successful upload confirms that the parser accepted the input. It does not establish that the values are correct or suitable for every analysis.

### Prepare a cleaned version

1. Open the dataset's cleaning workspace.
2. Inspect detected issues before choosing an operation.
3. Preview the operation and compare its effect with the original data.
4. Apply it if the result is appropriate; use undo or reset when necessary.
5. Save the result as a new dataset version.
6. Select that saved version for charts, training, or reports.

Retain a short explanation for major cleaning choices, especially removed rows and imputed target-related values. Avoid using information from a future test period when preparing forecasting experiments.

### Create and save a chart

Open Visualization, select the dataset, and choose a chart type. Assign X, Y, and any required Z column. Use an aggregation when several records represent the same category. For example, a sales-by-region bar chart normally sums a numeric sales column by region rather than plotting every transaction separately. Review missing labels and totals, then save the chart configuration if it will be reused.

### Train and explain a model

Choose the saved dataset version and enter ML Studio. Select classification or regression, define the target, and exclude target-derived or future-information columns from the features. Configure the split and preprocessing, prepare the data, and run training. Inspect the comparison results and any algorithm failures before choosing a model.

Save a supported supervised model, then open its explanation workspace. Compare global importance with a local explanation for a selected record. Interpret the explanation together with prediction error and data quality; a plausible explanation does not guarantee a correct model.

Clustering is available for exploratory grouping, but the current save operation rejects clustering results. Plan the demonstration accordingly.

### Analyze a time series and export findings

Select a date column and numeric value in Time Series. Check that dates represent a meaningful sequence and that enough observations remain after conversion. Review stationarity, seasonal output, and forecasting availability separately. Generate a report from the report builder, select the desired format, and inspect the downloaded file before sharing it.

### Common problems

| Symptom | Likely explanation | Suggested response |
| --- | --- | --- |
| XLS or Parquet cannot be read | Missing format engine or invalid file | Install the compatible engine or export a valid CSV/XLSX |
| Upload is rejected as too large | Request exceeds configured limit | Use a smaller dataset or deliberately adjust the limit and memory budget |
| CSRF validation fails | Missing/stale token or changed session secret | Reload the form and sign in again; keep a stable secret |
| Training state disappears | Application restart or request reaches another worker | Reconfigure the experiment; use one worker until shared state is implemented |
| Forecast is unavailable | Prophet missing or data unsuitable | Install Prophet if needed and review the date/value series |
| Social login is unavailable | Provider credentials or callback mismatch | Check the local provider configuration and hostname |
| Analysis count differs from upload count | Analysis sampling or filtered time series rows | Identify the population used by that output before interpreting it |
| Model save fails | Unsupported clustering or persistence constraints | Read the returned error and review the limitations below |

## 10 Security and operational considerations

### Existing controls

The application includes password hashing, CSRF protection, session cookie settings, role checks, dataset ownership checks, upload validation, rate-limit helpers, security headers, and audit logging. API import URL validation rejects localhost and private/internal addresses. Database import validation restricts accepted query forms. These controls reduce specific risks but do not constitute a complete security audit.

Use database credentials that have only the permissions needed for import. Query text validation is not a substitute for a read-only database account. Store provider credentials in local configuration rather than source control or screenshots.

### Report storage exposure

Generated reports are written beneath Flask's static directory. Standard static serving can expose those files independently of the authenticated download route if their paths are known. Before hosting sensitive data, move report storage outside the public static tree and serve files through an ownership-checked route. Merely adding a user ID to a directory name is not access control.

### Session and worker behavior

A stable secret is necessary across restarts and processes. Process-local rate limits, caches, and workflow state are not shared automatically between multiple workers. Production scaling requires a shared store and a persistent job system, plus authorization checks for each job lookup. Deploying more workers without these changes can create inconsistent workflow behavior.

### Backup and recovery

Back up the metadata database together with uploaded datasets, saved model bundles, and generated reports. A metadata-only backup can leave records pointing to missing files. Use a consistent database backup method; copying a live SQLite file without accounting for its WAL state may produce an incomplete backup. Test recovery in a separate environment and protect secrets independently.

Only load trusted serialized model bundles. Joblib/pickle model files can execute code when deserialized and should not be treated as ordinary untrusted uploads.

## 11 Testing and evaluation

### Verification performed for this documentation

On 19 September 2026, a static syntax check parsed Python files under the application, analytical modules, authentication, migrations, tests, and scripts, plus `run.py` and `config.py`. It checked 140 files: 139 parsed successfully and one failed. The failure is `app/services/copilot_service.py`, where the parser reported an unterminated string literal at line 87.

The same inspection found 160 test functions or methods in the `tests/` directory. This is a source inventory, not a count of collected or passed test cases. Parameterization and test discovery can change the executed count. The application test suite, browser workflows, external provider sign-in, and deployment were not executed as part of this documentation task. No pass percentage or model-performance result is asserted.

### Existing test areas

| Area | Representative test files |
| --- | --- |
| Accounts and social sign-in | `test_auth.py`, `test_auth_service.py`, `test_social_auth.py` |
| Dataset and analysis workflows | `test_datasets.py`, `test_analysis.py` |
| Cleaning | `test_cleaning.py`, `test_cleaner.py` |
| Charts | `test_chart_service.py` |
| Machine learning | `test_ml.py`, `test_automl_pipeline.py`, `test_ml_studio_workflows.py` |
| Explainability | `test_xai.py` |
| Copilot and time series | `test_copilot.py`, `test_timeseries_json.py` |
| Reports | `test_reporting.py`, `test_report_service_contracts.py` |
| Security and API behavior | `test_security.py`, `test_phase14_security.py`, `test_api_consistency.py` |
| Appearance | `test_theme.py` |

### Running automated tests safely

Use a disposable project copy with a separate SQLite database and storage directories. The shared test fixture sets a database URL before importing the app, but `config.py` loads `.env` with override enabled. A copied real `.env` can therefore redirect tests to an unintended database. Configure an isolated test environment and verify the effective database target before running tests.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Run this command only from the isolated test copy. Record the actual collected, passed, skipped, and failed counts with the date and environment. Do not report the source inventory above as a successful test run.

### Acceptance test plan

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| AT01 | Register, sign in, and sign out | Correct account/session transitions and protected-page behavior |
| AT02 | Upload a valid CSV and inspect it | Stored dataset with accurate dimensions and a readable preview |
| AT03 | Upload an unsupported or oversized file | Clear rejection without a usable invalid dataset record |
| AT04 | Access another user's dataset ID | Access denied or resource not found |
| AT05 | Preview, apply, undo, and save cleaning | Correct row/value changes and a separate saved version |
| AT06 | Create a grouped bar chart | Aggregated totals agree with an independently computed result |
| AT07 | Train and save a regression/classification model | Real metrics, valid persisted bundle, and reproducible prediction input |
| AT08 | Request explanations for a supported model | Valid output or a clear capability/dependency error |
| AT09 | Analyze a short or invalid time series | Clear validation or partial-analysis errors |
| AT10 | Export a report | File opens and reflects the selected dataset and available results |
| AT11 | Call a protected mutation without a valid CSRF token | Request rejected |
| AT12 | Use an administrator-only route as a normal user | Administrative action refused |

These are proposed acceptance tests, not recorded passes. For each execution, record input, actual output, status, and evidence. Include representative failures and boundary conditions.

## 12 Known limitations

### Incomplete or conditional features

- The standalone conversational Copilot service fails syntax parsing. The active Copilot route uses the analytical engine directly and does not provide the claimed full conversation workflow.
- A prompt-to-dashboard generation route is not present in the inspected route set. Saved chart configurations and the user dashboard are separate implemented features.
- XGBoost and LightGBM are deliberately disabled in the model registry despite appearing in the dependencies.
- Clustering model persistence is rejected by ML Studio's save method.
- Prophet forecasting requires an optional package that is absent from `requirements.txt`; XLS and Parquet readers also need compatible engines.

### Data and evaluation limitations

Large-data analysis is capped by sampling in many service methods. Time-series validity depends on dates, ordering, frequency, and sufficient history. Model explanations are conditional on estimator support and the stored training context. Generated recommendations should be reviewed by someone who understands the domain.

The `ml_models` schema constrains `primary_score` to the interval from zero to one and `cv_score` to nonnegative values. Some valid regression scores can be negative, and error metrics can exceed one. These constraints can reject legitimate experiment results and should be reviewed before broad model benchmarking.

### Operational limitations

Workflows and jobs depend on process memory, while the Docker example starts several processes. Report files reside in a publicly served directory. The default factory configuration is development, and several example environment variables do not control the entry point as their names might suggest. These are specific release-readiness issues, not proof that every local workflow fails.

The root README describes a previous stack and should be updated separately. Dependency versions use broad lower bounds rather than a fully locked environment. Reproducible installation and production readiness require additional validation.

## 13 Future development

The first priority is to make the documented feature set dependable: repair or remove the unused conversational service, align the README with Flask, correct score constraints, and complete isolated acceptance testing. Move report output outside static storage and verify authorization for downloads and background-job status.

For larger deployments, move job execution and workflow state to durable shared services, add structured job ownership, and measure memory and latency under realistic load. Add explicit sampling information to analysis and report outputs so readers can distinguish sample statistics from full-data counts.

Later enhancements can include tested conversational analysis, prompt-based dashboard creation, persistent clustering workflows, a consistent versioned API, locked dependency versions, and a release pipeline with regression tests. These are proposed improvements, not current capabilities.

## 14 Demonstration and handover

### Suggested FYP demonstration

Use a small, non-sensitive dataset with documented columns and a clear question. Demonstrate import and quality inspection, then one justified cleaning operation and a saved version. Create a chart that answers the question. Train two suitable supervised algorithms with the same split, compare their actual results, and save one model. Explain a prediction and export a report.

If forecasting is included, install and verify Prophet beforehand and use a dataset with meaningful time history. Demonstrate the active Copilot as automated insights. Do not depend on the broken conversational service, disabled boosting algorithms, or clustering persistence during the presentation.

### Handover checklist

- Include source code, dependency instructions, and `.env.example` without real credentials.
- Include this documentation and a small, permitted demonstration dataset.
- Record the environment, commands, and optional dependencies used for the successful demo.
- Attach actual test results and measured model metrics when available.
- Explain where datasets, models, reports, and database backups are stored.
- State outstanding limitations and the scope of maintenance or support.
- Add institution, student, supervisor, and submission details only when the correct information is supplied.

### Project conclusion

DataViz Pro combines the main stages of a structured-data analysis workflow within a modular Flask application. Its current strengths are the breadth of integrated analytical operations and the separation of routes, services, analytical modules, and persistence. A complete project evaluation should demonstrate these workflows with reproducible evidence and address the documented gaps before claiming production readiness or unrestricted AI capabilities.

## 15 Source reference and glossary

### Implementation references

The following repository files provide the implementation reference for this document. Paths are relative to the project root.

| Subject | Source files |
| --- | --- |
| Entry point and configuration | `run.py`, `config.py`, `app/__init__.py`, `.env.example` |
| Dependencies and deployment | `requirements.txt`, `Dockerfile` |
| Schema and records | `auth/database.py`, `app/domain/dataset.py`, `app/domain/ml_model.py` |
| Authentication and OAuth | `app/routes/auth.py`, `app/auth_helpers.py`, `app/oauth.py`, `auth/security.py`, `docs/oauth.md` |
| Dataset import and security | `app/routes/datasets.py`, `app/services/dataset_service.py`, `app/security.py` |
| Analysis and cleaning | `app/services/analysis_service.py`, `app/services/cleaning_service.py`, `core/`, `cleaner/` |
| Charts | `app/routes/visualization.py`, `app/services/chart_service.py` |
| Machine learning | `app/services/ml_service.py`, `ml/services/model_registry.py`, `ml/services/` |
| Explanations | `app/services/xai_service.py`, `app/routes/xai.py` |
| Time series and insights | `timeseries/ts_analyzer.py`, `app/routes/timeseries.py`, `app/routes/copilot.py`, `ai_engine/` |
| Reporting | `app/services/report_service.py`, `app/routes/reports.py`, `ai_engine/generators/` |
| Caching and testing | `app/core/cache.py`, `tests/conftest.py`, `tests/test_*.py` |

### Glossary

| Term | Meaning |
| --- | --- |
| API | An interface through which software requests data or operations |
| Blueprint | A Flask component grouping related routes |
| CSRF | Cross-site request forgery; token checks protect authenticated mutations |
| DataFrame | A table-like data structure used by pandas |
| EDA | Exploratory data analysis |
| FYP | Final year project |
| Holdout set | Data reserved for evaluation rather than fitting |
| Imputation | Replacing missing values using a defined strategy |
| Leakage | Information entering training or evaluation in a way that inflates results |
| ORM | Mapping between program objects and relational database records |
| SHAP and LIME | Methods for explaining model outputs through feature contributions |
| TTL | Time to live, after which a cached value expires |
| WAL | SQLite write-ahead logging mode |
| XAI | Explainable artificial intelligence |
