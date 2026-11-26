"""add singleton canteen settings

Revision ID: a6c7e8f90123
Revises: f2b3c4d5e6a7
Create Date: 2026-11-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a6c7e8f90123"
down_revision = "f2b3c4d5e6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "canteen_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("is_accepting_orders", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("closed_message", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_canteen_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("canteen_settings")
