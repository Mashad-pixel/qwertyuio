"""add refunds

Revision ID: f2b3c4d5e6a7
Revises: e7a1b2c3d4f5
Create Date: 2026-11-21 13:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b3c4d5e6a7'
down_revision = 'e7a1b2c3d4f5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('refunds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('provider_refund_id', sa.String(length=64), nullable=False),
    sa.Column('amount_paise', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('requested_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('amount_paise > 0', name='ck_refunds_amount_positive'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_refund_id')
    )
    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refunds_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refunds_payment_id'), ['payment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refunds_requested_by'), ['requested_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_refunds_status'), ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refunds_status'))
        batch_op.drop_index(batch_op.f('ix_refunds_requested_by'))
        batch_op.drop_index(batch_op.f('ix_refunds_payment_id'))
        batch_op.drop_index(batch_op.f('ix_refunds_order_id'))

    op.drop_table('refunds')
