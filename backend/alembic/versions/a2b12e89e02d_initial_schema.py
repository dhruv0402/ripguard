"""initial_schema

Revision ID: a2b12e89e02d
Revises: 
Create Date: 2026-10-20 02:20:56.742642

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b12e89e02d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. analysis_sessions
    op.create_table(
        'analysis_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.Column('annotated_video_path', sa.String(length=512), nullable=True),
        sa.Column('status', sa.Enum('pending', 'processing', 'done', 'failed', name='sessionstatus'), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('overall_risk_level', sa.Enum('low', 'medium', 'high', name='risklevel'), nullable=True),
        sa.Column('risk_timeline', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # 3. detections
    op.create_table(
        'detections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('start_timestamp_sec', sa.Float(), nullable=False),
        sa.Column('end_timestamp_sec', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('bounding_region', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['analysis_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # 4. benchmark_runs
    op.create_table(
        'benchmark_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('dataset_split', sa.String(length=64), nullable=False),
        sa.Column('iou', sa.Float(), nullable=False),
        sa.Column('dice_f1', sa.Float(), nullable=False),
        sa.Column('precision', sa.Float(), nullable=False),
        sa.Column('recall', sa.Float(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('benchmark_runs')
    op.drop_table('detections')
    op.drop_table('analysis_sessions')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
