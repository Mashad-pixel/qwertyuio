"""add canteen name and operating hours to the settings row

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
Create Date: 2026-11-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3c4d5e6f7081"
down_revision = "2b3c4d5e6f70"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("canteen_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "canteen_name",
            sa.String(length=80),
            nullable=False,
            server_default="TrayUP Canteen",
        ))
        batch_op.add_column(sa.Column("opens_at", sa.String(length=5), nullable=True))
        batch_op.add_column(sa.Column("closes_at", sa.String(length=5), nullable=True))


def downgrade():
    with op.batch_alter_table("canteen_settings", schema=None) as batch_op:
        batch_op.drop_column("closes_at")
        batch_op.drop_column("opens_at")
        batch_op.drop_column("canteen_name")
