"""add menu categories table, seeded from the categories already used by menu items

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2026-11-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2b3c4d5e6f70"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "menu_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_menu_categories_name"),
    )
    # Every category already used by a menu item becomes a real category, so no item is orphaned.
    op.execute(
        "INSERT INTO menu_categories (name, created_at, updated_at) "
        "SELECT DISTINCT category, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM menu_items "
        "WHERE category IS NOT NULL AND TRIM(category) <> ''"
    )


def downgrade():
    op.drop_table("menu_categories")
