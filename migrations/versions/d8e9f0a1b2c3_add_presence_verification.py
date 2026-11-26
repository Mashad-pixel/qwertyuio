"""add presence verification (live QR tokens, redemptions, single-use sessions)

Revision ID: d8e9f0a1b2c3
Revises: c95428642e8a
Create Date: 2026-11-24 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8e9f0a1b2c3'
down_revision = 'c95428642e8a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('presence_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('issued_by_id', sa.Integer(), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['issued_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('presence_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_presence_tokens_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_presence_tokens_issued_by_id'), ['issued_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_presence_tokens_token_hash'), ['token_hash'], unique=True)

    op.create_table('presence_redemptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('distance_meters', sa.Integer(), nullable=False),
    sa.Column('accuracy_meters', sa.Integer(), nullable=False),
    sa.CheckConstraint('accuracy_meters >= 0', name='ck_presence_redemptions_accuracy_non_negative'),
    sa.CheckConstraint('distance_meters >= 0', name='ck_presence_redemptions_distance_non_negative'),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['token_id'], ['presence_tokens.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_id', 'student_id', name='uq_presence_redemptions_token_student')
    )
    with op.batch_alter_table('presence_redemptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_presence_redemptions_student_id'), ['student_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_presence_redemptions_token_id'), ['token_id'], unique=False)

    op.create_table('presence_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_hash', sa.String(length=64), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('redemption_id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['redemption_id'], ['presence_redemptions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_id', name='uq_presence_sessions_order'),
    sa.UniqueConstraint('redemption_id', name='uq_presence_sessions_redemption')
    )
    with op.batch_alter_table('presence_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_presence_sessions_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_presence_sessions_session_hash'), ['session_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_presence_sessions_student_id'), ['student_id'], unique=False)


def downgrade():
    with op.batch_alter_table('presence_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_presence_sessions_student_id'))
        batch_op.drop_index(batch_op.f('ix_presence_sessions_session_hash'))
        batch_op.drop_index(batch_op.f('ix_presence_sessions_expires_at'))
    op.drop_table('presence_sessions')

    with op.batch_alter_table('presence_redemptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_presence_redemptions_token_id'))
        batch_op.drop_index(batch_op.f('ix_presence_redemptions_student_id'))
    op.drop_table('presence_redemptions')

    with op.batch_alter_table('presence_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_presence_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_presence_tokens_issued_by_id'))
        batch_op.drop_index(batch_op.f('ix_presence_tokens_expires_at'))
    op.drop_table('presence_tokens')
