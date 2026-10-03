"""Persist named analysis workspaces without altering existing data."""
from alembic import op
import sqlalchemy as sa

revision = '003_workspaces'
down_revision = '002_add_indexes'
branch_labels = None
depends_on = None


def upgrade():
    if 'analysis_workspaces' not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table('analysis_workspaces',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('dataset_id', sa.Integer, sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('state', sa.Text, nullable=False),
            sa.Column('created_at', sa.DateTime, nullable=False))
        op.create_index('ix_analysis_workspaces_user_id', 'analysis_workspaces', ['user_id'])


def downgrade():
    op.drop_table('analysis_workspaces')
