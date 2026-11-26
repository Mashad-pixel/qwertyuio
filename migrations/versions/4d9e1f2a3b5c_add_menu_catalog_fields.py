"""add diet, ingredients and preparation details to menu items

Revision ID: 4d9e1f2a3b5c
Revises: 3c8d2e4f5a6b
Create Date: 2026-11-25

"""
from alembic import op
import sqlalchemy as sa


revision = "4d9e1f2a3b5c"
down_revision = "3c8d2e4f5a6b"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows get NULL diet and empty detail fields. NULL means "not recorded", so
    # nothing is guessed about what is vegetarian.
    with op.batch_alter_table("menu_items") as batch:
        batch.add_column(sa.Column("is_veg", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("ingredients", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("preparation", sa.Text(), nullable=True))
        batch.add_column(sa.Column("recipe_steps", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("menu_items") as batch:
        batch.drop_column("recipe_steps")
        batch.drop_column("preparation")
        batch.drop_column("ingredients")
        batch.drop_column("is_veg")
