"""add persistent menu categories and canteen name and hours

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-11-25 09:00:00.000000

"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    categories = op.create_table(
        "menu_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_menu_categories_name"),
    )

    # Every category already used by a menu item becomes a row, so existing items stay valid.
    bind = op.get_bind()
    names = [
        row[0]
        for row in bind.execute(
            sa.text("SELECT DISTINCT category FROM menu_items WHERE category IS NOT NULL ORDER BY category")
        )
    ]
    now = datetime.now(timezone.utc)
    if names:
        op.bulk_insert(
            categories,
            [
                {"name": name, "sort_order": index * 10, "created_at": now, "updated_at": now}
                for index, name in enumerate(names)
            ],
        )

    with op.batch_alter_table("canteen_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "canteen_name", sa.String(length=120), server_default="TrayUP Canteen", nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "opens_at", sa.Time(), server_default="08:00:00", nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "closes_at", sa.Time(), server_default="18:00:00", nullable=False,
        ))


def downgrade():
    with op.batch_alter_table("canteen_settings", schema=None) as batch_op:
        batch_op.drop_column("closes_at")
        batch_op.drop_column("opens_at")
        batch_op.drop_column("canteen_name")

    op.drop_table("menu_categories")
