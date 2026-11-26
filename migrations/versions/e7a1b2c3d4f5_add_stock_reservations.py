"""add stock reservations and reserved quantity

Revision ID: e7a1b2c3d4f5
Revises: 99d21c7d2218
Create Date: 2026-11-21 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7a1b2c3d4f5'
down_revision = '99d21c7d2218'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('menu_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reserved_quantity', sa.Integer(), server_default='0', nullable=False))
        batch_op.create_check_constraint('ck_menu_items_reserved_non_negative', 'reserved_quantity >= 0')
        batch_op.create_check_constraint(
            'ck_menu_items_reserved_within_stock',
            'stock_quantity IS NULL OR reserved_quantity <= stock_quantity',
        )

    op.create_table('stock_reservations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('menu_item_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('quantity > 0', name='ck_stock_reservations_quantity_positive'),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_id', 'menu_item_id', name='uq_stock_reservations_order_item')
    )
    with op.batch_alter_table('stock_reservations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_stock_reservations_menu_item_id'), ['menu_item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_reservations_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_reservations_status'), ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('stock_reservations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stock_reservations_status'))
        batch_op.drop_index(batch_op.f('ix_stock_reservations_order_id'))
        batch_op.drop_index(batch_op.f('ix_stock_reservations_menu_item_id'))

    op.drop_table('stock_reservations')

    # Dropping the column also drops the check constraints that use it.
    with op.batch_alter_table('menu_items', schema=None) as batch_op:
        batch_op.drop_column('reserved_quantity')
