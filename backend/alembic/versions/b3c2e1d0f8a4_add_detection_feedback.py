"""add_detection_feedback

Revision ID: b3c2e1d0f8a4
Revises: a2b12e89e02d
Create Date: 2026-10-20 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c2e1d0f8a4'
down_revision: Union[str, Sequence[str], None] = 'a2b12e89e02d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'detection_feedback',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('detection_id', sa.UUID(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'feedback_type',
            sa.Enum(
                'confirmed_true_positive',
                'false_positive_wake',
                'false_positive_sandbar',
                'false_positive_wave_break',
                'false_positive_other',
                'missed_detection',
                name='feedbacktype',
            ),
            nullable=False,
        ),
        sa.Column('confidence_rating', sa.Integer(), nullable=True),
        sa.Column('operator_notes', sa.Text(), nullable=True),
        sa.Column('corrected_region', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['analysis_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['detection_id'], ['detections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('detection_feedback')
    op.execute("DROP TYPE IF EXISTS feedbacktype")
