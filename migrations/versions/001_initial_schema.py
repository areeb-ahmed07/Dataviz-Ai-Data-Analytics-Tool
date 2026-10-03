"""Phase 12: Initial schema baseline with indexes, constraints, and relationships.

This migration captures the full DataViz Pro schema including:
- All 6 tables (users, projects, datasets, analyses, ml_models, saved_charts)
- Foreign key constraints with CASCADE/SET NULL
- Composite indexes for common query patterns
- CHECK constraints for data validation
- ORM relationships (back_populates)

Revision ID: 001_initial
Revises: -
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── SQLite pragmas ─────────────────────────────────────
    op.execute("PRAGMA journal_mode=WAL")
    op.execute("PRAGMA foreign_keys=ON")
    op.execute("PRAGMA busy_timeout=5000")

    # ── Users table ────────────────────────────────────────
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('full_name', sa.String(100), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='user'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('theme', sa.String(20), nullable=False, server_default='light'),
        sa.Column('notifications_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.CheckConstraint("length(username) >= 3", name='ck_users_username_min_len'),
        sa.CheckConstraint("length(email) >= 5", name='ck_users_email_min_len'),
        sa.CheckConstraint("role IN ('user', 'admin')", name='ck_users_role_valid'),
        sa.CheckConstraint("length(full_name) >= 1", name='ck_users_fullname_min_len'),
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_id', 'users', ['id'])

    # ── Projects table ─────────────────────────────────────
    op.create_table('projects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_name', sa.String(100), nullable=False),
        sa.Column('dataset_path', sa.String(255), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('col_count', sa.Integer(), nullable=True),
        sa.Column('file_size_kb', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(project_name) >= 1", name='ck_projects_name_min_len'),
    )
    op.create_index('ix_projects_id', 'projects', ['id'])
    op.create_index('ix_projects_user_created', 'projects', ['user_id', 'created_at'])

    # ── Datasets table ──────────────────────────────────────
    op.create_table('datasets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_format', sa.String(20), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('column_count', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('encoding', sa.String(50), nullable=True),
        sa.Column('delimiter', sa.String(10), nullable=True),
        sa.Column('column_info', sa.Text(), nullable=True),
        sa.Column('quality_info', sa.Text(), nullable=True),
        sa.Column('parent_dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('cleaning_pipeline', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(name) >= 1", name='ck_datasets_name_min_len'),
        sa.CheckConstraint("length(original_filename) >= 1", name='ck_datasets_filename_min_len'),
        sa.CheckConstraint("length(file_format) >= 1", name='ck_datasets_format_valid'),
        sa.CheckConstraint("row_count IS NULL OR row_count >= 0", name='ck_datasets_row_count_nonneg'),
        sa.CheckConstraint("column_count IS NULL OR column_count >= 0", name='ck_datasets_col_count_nonneg'),
        sa.CheckConstraint("file_size IS NULL OR file_size >= 0", name='ck_datasets_file_size_nonneg'),
    )
    op.create_index('ix_datasets_id', 'datasets', ['id'])
    op.create_index('ix_datasets_user_created', 'datasets', ['user_id', 'created_at'])
    op.create_index('ix_datasets_user_format', 'datasets', ['user_id', 'file_format'])
    op.create_index('ix_datasets_parent', 'datasets', ['parent_dataset_id'])

    # ── Analyses table ─────────────────────────────────────
    op.create_table('analyses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('analysis_type', sa.String(100), nullable=False),
        sa.Column('summary_metrics', sa.Text(), nullable=False),
        sa.Column('report_path', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(analysis_type) >= 1", name='ck_analyses_type_min_len'),
        sa.CheckConstraint("length(report_path) >= 1", name='ck_analyses_report_path_min_len'),
    )
    op.create_index('ix_analyses_id', 'analyses', ['id'])
    op.create_index('ix_analyses_user_created', 'analyses', ['user_id', 'created_at'])
    op.create_index('ix_analyses_project', 'analyses', ['project_id'])

    # ── ML Models table ────────────────────────────────────
    op.create_table('ml_models',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('algorithm', sa.String(100), nullable=False),
        sa.Column('problem_type', sa.String(50), nullable=False),
        sa.Column('target_column', sa.String(255), nullable=True),
        sa.Column('features', sa.Text(), nullable=True),
        sa.Column('metrics', sa.Text(), nullable=True),
        sa.Column('hyperparameters', sa.Text(), nullable=True),
        sa.Column('pipeline_config', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('model_path', sa.String(500), nullable=True),
        sa.Column('model_format', sa.String(20), nullable=True),
        sa.Column('experiment_config', sa.Text(), nullable=True),
        sa.Column('primary_metric', sa.String(50), nullable=True),
        sa.Column('primary_score', sa.Float(), nullable=True),
        sa.Column('cv_strategy', sa.String(50), nullable=True),
        sa.Column('cv_score', sa.Float(), nullable=True),
        sa.Column('cv_std', sa.Float(), nullable=True),
        sa.Column('random_state', sa.Integer(), nullable=True),
        sa.Column('test_size', sa.Float(), nullable=True),
        sa.Column('train_rows', sa.Integer(), nullable=True),
        sa.Column('test_rows', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(model_name) >= 1", name='ck_ml_models_name_min_len'),
        sa.CheckConstraint("length(algorithm) >= 1", name='ck_ml_models_algorithm_min_len'),
        sa.CheckConstraint("problem_type IN ('classification', 'regression', 'clustering')", name='ck_ml_models_problem_type_valid'),
        sa.CheckConstraint("version >= 1", name='ck_ml_models_version_positive'),
        sa.CheckConstraint("primary_score IS NULL OR primary_score >= 0", name='ck_ml_models_score_nonneg'),
        sa.CheckConstraint("primary_score IS NULL OR primary_score <= 1", name='ck_ml_models_score_max_one'),
        sa.CheckConstraint("cv_score IS NULL OR cv_score >= 0", name='ck_ml_models_cv_score_nonneg'),
        sa.CheckConstraint("cv_std IS NULL OR cv_std >= 0", name='ck_ml_models_cv_std_nonneg'),
        sa.CheckConstraint("test_size IS NULL OR (test_size > 0 AND test_size < 1)", name='ck_ml_models_test_size_range'),
        sa.CheckConstraint("train_rows IS NULL OR train_rows >= 0", name='ck_ml_models_train_rows_nonneg'),
        sa.CheckConstraint("test_rows IS NULL OR test_rows >= 0", name='ck_ml_models_test_rows_nonneg'),
    )
    op.create_index('ix_ml_models_id', 'ml_models', ['id'])
    op.create_index('ix_ml_models_user_created', 'ml_models', ['user_id', 'created_at'])
    op.create_index('ix_ml_models_user_dataset', 'ml_models', ['user_id', 'dataset_id'])
    op.create_index('ix_ml_models_user_active', 'ml_models', ['user_id', 'is_active'])
    op.create_index('ix_ml_models_dataset', 'ml_models', ['dataset_id'])
    op.create_index('ix_ml_models_algorithm', 'ml_models', ['algorithm'])

    # ── Saved Charts table ─────────────────────────────────
    op.create_table('saved_charts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('chart_type', sa.String(50), nullable=False),
        sa.Column('config', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(name) >= 1", name='ck_saved_charts_name_min_len'),
        sa.CheckConstraint("length(chart_type) >= 1", name='ck_saved_charts_type_min_len'),
    )
    op.create_index('ix_saved_charts_id', 'saved_charts', ['id'])
    op.create_index('ix_saved_charts_user_dataset', 'saved_charts', ['user_id', 'dataset_id'])
    op.create_index('ix_saved_charts_user_created', 'saved_charts', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('saved_charts')
    op.drop_table('ml_models')
    op.drop_table('analyses')
    op.drop_table('datasets')
    op.drop_table('projects')
    op.drop_table('users')
