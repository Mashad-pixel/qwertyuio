"""add administrator MFA fields and server-side user sessions

Revision ID: 3c8d2e4f5a6b
Revises: 1a2b3c4d5e6f
Create Date: 2026-11-25

"""
from alembic import op
import sqlalchemy as sa


revision = "3c8d2e4f5a6b"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("mfa_secret", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("mfa_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("mfa_locked_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"], unique=False)


def downgrade():
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("mfa_locked_until")
        batch.drop_column("mfa_failed_attempts")
        batch.drop_column("mfa_last_step")
        batch.drop_column("mfa_secret")
        batch.drop_column("mfa_enabled")
