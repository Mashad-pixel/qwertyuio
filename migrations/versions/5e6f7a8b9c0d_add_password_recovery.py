"""add password recovery: email codes, reset tokens, backup codes, support requests

Revision ID: 5e6f7a8b9c0d
Revises: 4d9e1f2a3b5c
Create Date: 2026-11-26 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "5e6f7a8b9c0d"
down_revision = "4d9e1f2a3b5c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_challenges_user_id", "otp_challenges", ["user_id"])
    op.create_index("ix_otp_challenges_expires_at", "otp_challenges", ["expires_at"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])

    op.create_table(
        "recovery_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("identifier", sa.String(length=120), nullable=False),
        sa.Column("contact_email", sa.String(length=120), nullable=False),
        sa.Column("created_estimate", sa.String(length=60), server_default="", nullable=False),
        sa.Column("last_login_estimate", sa.String(length=60), server_default="", nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("extra", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="received", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_recovery_requests_reference"),
    )


def downgrade():
    op.drop_table("recovery_requests")
    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_otp_challenges_expires_at", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_user_id", table_name="otp_challenges")
    op.drop_table("otp_challenges")
