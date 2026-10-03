import os
import datetime
import json
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text, inspect, text, BigInteger, Index, CheckConstraint, event, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv
from auth.domain.user import UserDomain, Role
from auth.domain.project import ProjectDomain, AnalysisDomain

logger = logging.getLogger(__name__)
load_dotenv()

# Default to local SQLite database dataviz_pro.db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dataviz_pro.db")
# Handle non-standard URL formats (e.g. "file:" prefix from root .env)
if DATABASE_URL.startswith("file:"):
    _path = DATABASE_URL[5:]  # strip "file:"
    # Ensure parent directory exists
    _dir = os.path.dirname(_path)
    if _dir:
        os.makedirs(_dir, exist_ok=True)
    DATABASE_URL = f"sqlite:///{_path}"
_is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── SQLite: enforce foreign keys at connection level ──────────────
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL journal mode and foreign key enforcement for every new SQLite connection."""
    if _is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


# ── SQLAlchemy Models ─────────────────────────────────────────────

class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default=Role.USER.value, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=True)
    theme = Column(String(20), default="light", nullable=False)
    notifications_enabled = Column(Boolean, default=True, nullable=False)

    # ── ORM relationships ───────────────────────────────────
    projects = relationship("ProjectDB", back_populates="user", lazy="select", passive_deletes=True)
    datasets = relationship("DatasetDB", back_populates="user", lazy="select", passive_deletes=True)
    analyses = relationship("AnalysisDB", back_populates="user", lazy="select", passive_deletes=True)
    ml_models = relationship("ModelDB", back_populates="user", lazy="select", passive_deletes=True)
    saved_charts = relationship("SavedChartDB", back_populates="user", lazy="select", passive_deletes=True)
    audit_logs = relationship("AuditLogDB", back_populates="user", lazy="select", passive_deletes=True)

    # ── Constraints ──────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("length(username) >= 3", name="ck_users_username_min_len"),
        CheckConstraint("length(email) >= 5", name="ck_users_email_min_len"),
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role_valid"),
        CheckConstraint("length(full_name) >= 1", name="ck_users_fullname_min_len"),
    )

    def to_domain(self) -> UserDomain:
        return UserDomain(
            id=self.id,
            username=self.username,
            email=self.email,
            full_name=self.full_name,
            role=Role(self.role),
            is_active=self.is_active,
            created_at=self.created_at,
            theme=self.theme,
            notifications_enabled=self.notifications_enabled
        )


class OAuthIdentityDB(Base):
    __tablename__ = "oauth_identities"
    provider = Column(String(20), primary_key=True)
    subject = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class ProjectDB(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_name = Column(String(100), nullable=False)
    dataset_path = Column(String(255), nullable=False)
    row_count = Column(Integer, nullable=True)
    col_count = Column(Integer, nullable=True)
    file_size_kb = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # ── ORM relationships ───────────────────────────────────
    user = relationship("UserDB", back_populates="projects")
    analyses = relationship("AnalysisDB", back_populates="project", lazy="select", passive_deletes=True)

    # ── Composite index for user project listing queries ────
    __table_args__ = (
        Index("ix_projects_user_created", "user_id", "created_at"),
        CheckConstraint("length(project_name) >= 1", name="ck_projects_name_min_len"),
    )

    def to_domain(self) -> ProjectDomain:
        return ProjectDomain(
            id=self.id,
            user_id=self.user_id,
            project_name=self.project_name,
            dataset_path=self.dataset_path,
            row_count=self.row_count,
            col_count=self.col_count,
            file_size_kb=self.file_size_kb,
            created_at=self.created_at
        )


class DatasetDB(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_format = Column(String(20), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    storage_path = Column(String(500), nullable=False)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    encoding = Column(String(50), nullable=True)
    delimiter = Column(String(10), nullable=True)
    column_info = Column(Text, nullable=True)  # JSON-serialized column metadata
    quality_info = Column(Text, nullable=True)  # JSON-serialized quality summary
    parent_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    cleaning_pipeline = Column(Text, nullable=True)  # JSON-serialized cleaning operations
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    # ── ORM relationships ───────────────────────────────────
    user = relationship("UserDB", back_populates="datasets")
    parent = relationship("DatasetDB", remote_side=[id], foreign_keys=[parent_dataset_id])
    children = relationship("DatasetDB", back_populates="parent", foreign_keys=[parent_dataset_id], lazy="select")
    ml_models = relationship("ModelDB", back_populates="dataset", lazy="select", passive_deletes=True)
    saved_charts = relationship("SavedChartDB", back_populates="dataset", lazy="select", passive_deletes=True)

    # ── Composite indexes for common query patterns ─────────
    __table_args__ = (
        Index("ix_datasets_user_created", "user_id", "created_at"),
        Index("ix_datasets_user_format", "user_id", "file_format"),
        Index("ix_datasets_parent", "parent_dataset_id"),
        CheckConstraint("length(name) >= 1", name="ck_datasets_name_min_len"),
        CheckConstraint("length(original_filename) >= 1", name="ck_datasets_filename_min_len"),
        CheckConstraint("length(file_format) >= 1", name="ck_datasets_format_valid"),
        CheckConstraint("row_count IS NULL OR row_count >= 0", name="ck_datasets_row_count_nonneg"),
        CheckConstraint("column_count IS NULL OR column_count >= 0", name="ck_datasets_col_count_nonneg"),
        CheckConstraint("file_size IS NULL OR file_size >= 0", name="ck_datasets_file_size_nonneg"),
    )


class AnalysisDB(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    analysis_type = Column(String(100), nullable=False)
    summary_metrics = Column(Text, nullable=False)  # Stored as serialized JSON string
    report_path = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # ── ORM relationships ───────────────────────────────────
    user = relationship("UserDB", back_populates="analyses")
    project = relationship("ProjectDB", back_populates="analyses")

    # ── Composite indexes for common query patterns ─────────
    __table_args__ = (
        Index("ix_analyses_user_created", "user_id", "created_at"),
        Index("ix_analyses_project", "project_id"),
        CheckConstraint("length(analysis_type) >= 1", name="ck_analyses_type_min_len"),
        CheckConstraint("length(report_path) >= 1", name="ck_analyses_report_path_min_len"),
    )

    def to_domain(self) -> AnalysisDomain:
        metrics = {}
        if self.summary_metrics:
            try:
                metrics = json.loads(self.summary_metrics)
            except Exception:
                pass
        return AnalysisDomain(
            id=self.id,
            user_id=self.user_id,
            project_id=self.project_id,
            analysis_type=self.analysis_type,
            summary_metrics=metrics,
            report_path=self.report_path,
            created_at=self.created_at
        )


class ModelDB(Base):
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    model_name = Column(String(255), nullable=False)
    algorithm = Column(String(100), nullable=False)
    problem_type = Column(String(50), nullable=False)  # classification, regression, clustering
    target_column = Column(String(255), nullable=True)
    features = Column(Text, nullable=True)  # JSON list of feature column names
    metrics = Column(Text, nullable=True)  # JSON dict of model metrics
    hyperparameters = Column(Text, nullable=True)  # JSON dict of hyperparameters
    pipeline_config = Column(Text, nullable=True)  # JSON dict of preprocessing pipeline config
    version = Column(Integer, default=1, nullable=False)
    model_path = Column(String(500), nullable=True)  # path to serialized model file
    model_format = Column(String(20), nullable=True)  # joblib, pickle
    experiment_config = Column(Text, nullable=True)  # JSON dict of full experiment config
    primary_metric = Column(String(50), nullable=True)
    primary_score = Column(Float, nullable=True)
    cv_strategy = Column(String(50), nullable=True)
    cv_score = Column(Float, nullable=True)
    cv_std = Column(Float, nullable=True)
    random_state = Column(Integer, nullable=True)
    test_size = Column(Float, nullable=True)
    train_rows = Column(Integer, nullable=True)
    test_rows = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    # ── ORM relationships ───────────────────────────────────
    user = relationship("UserDB", back_populates="ml_models")
    dataset = relationship("DatasetDB", back_populates="ml_models")

    # ── Composite indexes for common query patterns ─────────
    __table_args__ = (
        Index("ix_ml_models_user_created", "user_id", "created_at"),
        Index("ix_ml_models_user_dataset", "user_id", "dataset_id"),
        Index("ix_ml_models_user_active", "user_id", "is_active"),
        Index("ix_ml_models_dataset", "dataset_id"),
        Index("ix_ml_models_algorithm", "algorithm"),
        CheckConstraint("length(model_name) >= 1", name="ck_ml_models_name_min_len"),
        CheckConstraint("length(algorithm) >= 1", name="ck_ml_models_algorithm_min_len"),
        CheckConstraint("problem_type IN ('classification', 'regression', 'clustering')", name="ck_ml_models_problem_type_valid"),
        CheckConstraint("version >= 1", name="ck_ml_models_version_positive"),
        CheckConstraint("primary_score IS NULL OR primary_score >= 0", name="ck_ml_models_score_nonneg"),
        CheckConstraint("primary_score IS NULL OR primary_score <= 1", name="ck_ml_models_score_max_one"),
        CheckConstraint("cv_score IS NULL OR cv_score >= 0", name="ck_ml_models_cv_score_nonneg"),
        CheckConstraint("cv_std IS NULL OR cv_std >= 0", name="ck_ml_models_cv_std_nonneg"),
        CheckConstraint("test_size IS NULL OR test_size > 0 AND test_size < 1", name="ck_ml_models_test_size_range"),
        CheckConstraint("train_rows IS NULL OR train_rows >= 0", name="ck_ml_models_train_rows_nonneg"),
        CheckConstraint("test_rows IS NULL OR test_rows >= 0", name="ck_ml_models_test_rows_nonneg"),
    )

    def to_domain(self):
        from app.domain.ml_model import ModelDomain
        features = []
        if self.features:
            try:
                features = json.loads(self.features)
            except Exception:
                pass
        metrics = {}
        if self.metrics:
            try:
                metrics = json.loads(self.metrics)
            except Exception:
                pass
        hyperparams = {}
        if self.hyperparameters:
            try:
                hyperparams = json.loads(self.hyperparameters)
            except Exception:
                pass
        pipeline_cfg = {}
        if self.pipeline_config:
            try:
                pipeline_cfg = json.loads(self.pipeline_config)
            except Exception:
                pass
        experiment_cfg = {}
        if self.experiment_config:
            try:
                experiment_cfg = json.loads(self.experiment_config)
            except Exception:
                pass
        return ModelDomain(
            id=self.id,
            user_id=self.user_id,
            dataset_id=self.dataset_id,
            model_name=self.model_name,
            algorithm=self.algorithm,
            problem_type=self.problem_type,
            target_column=self.target_column,
            features=features,
            metrics=metrics,
            hyperparameters=hyperparams,
            pipeline_config=pipeline_cfg,
            version=self.version,
            model_path=self.model_path,
            model_format=self.model_format,
            experiment_config=experiment_cfg,
            primary_metric=self.primary_metric,
            primary_score=self.primary_score,
            cv_strategy=self.cv_strategy,
            cv_score=self.cv_score,
            cv_std=self.cv_std,
            random_state=self.random_state,
            test_size=self.test_size,
            train_rows=self.train_rows,
            test_rows=self.test_rows,
            is_active=self.is_active,
            description=self.description,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class AuditLogDB(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(50), nullable=True)  # denormalized for fast queries even if user deleted
    action = Column(String(100), nullable=False, index=True)  # e.g. login_success, login_failed, dataset_upload, admin_role_change
    resource_type = Column(String(50), nullable=True)  # user, dataset, model, system
    resource_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON-serialized extra context
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # ── ORM relationships ───────────────────────────────────
    user = relationship("UserDB")

    # ── Composite indexes for audit log queries ─────────────
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        CheckConstraint("length(action) >= 1", name="ck_audit_logs_action_min_len"),
    )


class LoginAttemptDB(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(100), nullable=False, index=True)  # email or username
    ip_address = Column(String(45), nullable=False)
    success = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_login_attempts_ip_created", "ip_address", "created_at"),
        Index("ix_login_attempts_identifier_created", "identifier", "created_at"),
    )


class WorkspaceDB(Base):
    __tablename__ = 'analysis_workspaces'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(120), nullable=False)
    state = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class SavedChartDB(Base):
    __tablename__ = "saved_charts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    chart_type = Column(String(50), nullable=False)
    config = Column(Text, nullable=False)  # JSON configuration
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # ── ORM relationships ───────────────────────────────────
    user = relationship("UserDB", back_populates="saved_charts")
    dataset = relationship("DatasetDB", back_populates="saved_charts")

    # ── Composite indexes for common query patterns ─────────
    __table_args__ = (
        Index("ix_saved_charts_user_dataset", "user_id", "dataset_id"),
        Index("ix_saved_charts_user_created", "user_id", "created_at"),
        CheckConstraint("length(name) >= 1", name="ck_saved_charts_name_min_len"),
        CheckConstraint("length(chart_type) >= 1", name="ck_saved_charts_type_min_len"),
    )


# ── DB Session helpers ─────────────────────────────────────────────

def get_session():
    """Create and return a new database session.

    IMPORTANT: The caller is responsible for closing this session.
    Prefer using ``session_scope()`` context manager instead.
    """
    return SessionLocal()


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations.

    Usage::

        with session_scope() as db:
            db.query(UserDB).first()

    The session is **always** closed when the context exits,
    and the transaction is committed on success or rolled back on exception.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize database tables with safe schema migration.

    Instead of dropping tables (data-destructive), this function:
    1. Ensures foreign key enforcement is enabled.
    2. Adds any missing columns to existing tables (safe ALTER TABLE).
    3. Creates tables that don't exist yet.
    4. Creates indexes that are missing.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # ── Safe column additions for existing tables ───────────
    if "users" in existing_tables:
        _ensure_columns("users", inspector, {
            "updated_at": "DATETIME",
            "theme": "VARCHAR(20) DEFAULT 'light' NOT NULL",
            "notifications_enabled": "BOOLEAN DEFAULT 1 NOT NULL",
        })

    if "datasets" in existing_tables:
        _ensure_columns("datasets", inspector, {
            "parent_dataset_id": "INTEGER REFERENCES datasets(id) ON DELETE SET NULL",
            "cleaning_pipeline": "TEXT",
        })

    # ── Create any tables that don't exist yet ──────────────
    Base.metadata.create_all(bind=engine)

    # ── Ensure composite indexes exist (idempotent) ─────────
    _ensure_composite_indexes(inspector)

    logger.info("[database] Schema initialization complete.")


def _ensure_columns(table_name: str, inspector, column_specs: dict):
    """Add missing columns to an existing table. Uses raw SQL for SQLite compatibility."""
    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for col_name, col_ddl in column_specs.items():
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_ddl}"))
                logger.info("[database] Added column %s.%s", table_name, col_name)


def _ensure_composite_indexes(inspector):
    """Create composite indexes that may be missing from older schemas.

    This is idempotent — it checks if the index already exists before creating.
    SQLite silently ignores CREATE INDEX IF NOT EXISTS duplicates.
    """
    indexes_to_ensure = [
        ("ix_projects_user_created", "projects", ["user_id", "created_at"]),
        ("ix_datasets_user_created", "datasets", ["user_id", "created_at"]),
        ("ix_datasets_user_format", "datasets", ["user_id", "file_format"]),
        ("ix_datasets_parent", "datasets", ["parent_dataset_id"]),
        ("ix_analyses_user_created", "analyses", ["user_id", "created_at"]),
        ("ix_analyses_project", "analyses", ["project_id"]),
        ("ix_ml_models_user_created", "ml_models", ["user_id", "created_at"]),
        ("ix_ml_models_user_dataset", "ml_models", ["user_id", "dataset_id"]),
        ("ix_ml_models_user_active", "ml_models", ["user_id", "is_active"]),
        ("ix_ml_models_dataset", "ml_models", ["dataset_id"]),
        ("ix_ml_models_algorithm", "ml_models", ["algorithm"]),
        ("ix_saved_charts_user_dataset", "saved_charts", ["user_id", "dataset_id"]),
        ("ix_saved_charts_user_created", "saved_charts", ["user_id", "created_at"]),
        ("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"]),
        ("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"]),
        ("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"]),
        ("ix_login_attempts_ip_created", "login_attempts", ["ip_address", "created_at"]),
        ("ix_login_attempts_identifier_created", "login_attempts", ["identifier", "created_at"]),
    ]

    existing_indexes = set()
    for table_name in ["users", "projects", "datasets", "analyses", "ml_models", "saved_charts", "audit_logs", "login_attempts"]:
        if table_name in inspector.get_table_names():
            for idx in inspector.get_indexes(table_name):
                existing_indexes.add(idx["name"])

    with engine.begin() as conn:
        for idx_name, table_name, columns in indexes_to_ensure:
            if idx_name not in existing_indexes:
                cols_sql = ", ".join(columns)
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({cols_sql})"))
                logger.info("[database] Created index %s on %s(%s)", idx_name, table_name, cols_sql)


def check_data_integrity() -> dict:
    """Run data integrity checks and return a report.

    Returns a dict with keys:
      - "valid": bool — overall pass/fail
      - "checks": list of {"name", "passed", "detail"} dicts
    """
    checks = []
    overall_valid = True

    with engine.begin() as conn:
        # 1. Orphaned datasets (user_id references non-existent user)
        result = conn.execute(text(
            "SELECT COUNT(*) FROM datasets d LEFT JOIN users u ON d.user_id = u.id WHERE u.id IS NULL"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "orphaned_datasets", "passed": passed, "detail": f"{result} datasets with missing user"})

        # 2. Orphaned analyses
        result = conn.execute(text(
            "SELECT COUNT(*) FROM analyses a LEFT JOIN users u ON a.user_id = u.id WHERE u.id IS NULL"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "orphaned_analyses", "passed": passed, "detail": f"{result} analyses with missing user"})

        # 3. Orphaned ml_models
        result = conn.execute(text(
            "SELECT COUNT(*) FROM ml_models m LEFT JOIN users u ON m.user_id = u.id WHERE u.id IS NULL"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "orphaned_ml_models", "passed": passed, "detail": f"{result} ml_models with missing user"})

        # 4. Orphaned saved_charts
        result = conn.execute(text(
            "SELECT COUNT(*) FROM saved_charts sc LEFT JOIN users u ON sc.user_id = u.id WHERE u.id IS NULL"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "orphaned_saved_charts", "passed": passed, "detail": f"{result} saved_charts with missing user"})

        # 5. Datasets with invalid parent_dataset_id (self-ref FK violation)
        result = conn.execute(text(
            "SELECT COUNT(*) FROM datasets d WHERE d.parent_dataset_id IS NOT NULL "
            "AND d.parent_dataset_id NOT IN (SELECT id FROM datasets)"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "invalid_dataset_parents", "passed": passed, "detail": f"{result} datasets with missing parent"})

        # 6. Analyses with invalid project_id
        result = conn.execute(text(
            "SELECT COUNT(*) FROM analyses a WHERE a.project_id IS NOT NULL "
            "AND a.project_id NOT IN (SELECT id FROM projects)"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "invalid_analysis_projects", "passed": passed, "detail": f"{result} analyses with missing project"})

        # 7. ML models with invalid dataset_id
        result = conn.execute(text(
            "SELECT COUNT(*) FROM ml_models m WHERE m.dataset_id IS NOT NULL "
            "AND m.dataset_id NOT IN (SELECT id FROM datasets)"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "invalid_model_datasets", "passed": passed, "detail": f"{result} ml_models with missing dataset"})

        # 8. Duplicate usernames (should be caught by unique constraint but verify)
        result = conn.execute(text(
            "SELECT COUNT(*) - COUNT(DISTINCT username) FROM users"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "duplicate_usernames", "passed": passed, "detail": f"{result} duplicate usernames detected"})

        # 9. Duplicate emails
        result = conn.execute(text(
            "SELECT COUNT(*) - COUNT(DISTINCT email) FROM users"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "duplicate_emails", "passed": passed, "detail": f"{result} duplicate emails detected"})

        # 10. Circular dataset parent references
        result = conn.execute(text(
            "SELECT COUNT(*) FROM datasets d1 WHERE d1.parent_dataset_id IS NOT NULL "
            "AND EXISTS ("
            "  WITH RECURSIVE chain(id) AS ("
            "    SELECT d1.parent_dataset_id UNION ALL "
            "    SELECT d.parent_dataset_id FROM datasets d JOIN chain c ON d.id = c.id WHERE d.parent_dataset_id IS NOT NULL"
            "  ) SELECT 1 FROM chain WHERE id = d1.id"
            ")"
        )).scalar()
        passed = result == 0
        if not passed:
            overall_valid = False
        checks.append({"name": "circular_dataset_parents", "passed": passed, "detail": f"{result} datasets with circular parent references"})

    return {"valid": overall_valid, "checks": checks}
