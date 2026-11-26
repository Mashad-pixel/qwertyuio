"""add account recovery tables, recovery codes, order customer details and request fingerprint

Revision ID: 3f9a1c2b4d5e
Revises: 1a2b3c4d5e6f
Create Date: 2026-11-25

"""
from alembic import op
import sqlalchemy as sa


revision = "3f9a1c2b4d5e"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("customer_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("customer_phone", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("instructions", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("request_fingerprint", sa.String(length=64), nullable=True))

    op.create_table(
        "password_recovery_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code_consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_token_hash", sa.String(length=64), nullable=True),
        sa.Column("reset_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_password_recovery_attempts_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reset_token_hash"),
    )
    op.create_index(
        "ix_password_recovery_challenges_user_id",
        "password_recovery_challenges",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_recovery_codes_user_code"),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"], unique=False)

    op.create_table(
        "account_recovery_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("identifier", sa.String(length=120), nullable=False),
        sa.Column("contact_email", sa.String(length=120), nullable=False),
        sa.Column("created_estimate", sa.String(length=100), nullable=True),
        sa.Column("last_login_estimate", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("extra", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_recovery_requests_ref", "account_recovery_requests", ["ref"], unique=True)
    op.create_index("ix_account_recovery_requests_user_id", "account_recovery_requests", ["user_id"], unique=False)
    op.create_index("ix_account_recovery_requests_status", "account_recovery_requests", ["status"], unique=False)


def downgrade():
    op.drop_index("ix_account_recovery_requests_status", table_name="account_recovery_requests")
    op.drop_index("ix_account_recovery_requests_user_id", table_name="account_recovery_requests")
    op.drop_index("ix_account_recovery_requests_ref", table_name="account_recovery_requests")
    op.drop_table("account_recovery_requests")

    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")

    op.drop_index("ix_password_recovery_challenges_user_id", table_name="password_recovery_challenges")
    op.drop_table("password_recovery_challenges")

    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("request_fingerprint")
        batch_op.drop_column("instructions")
        batch_op.drop_column("customer_phone")
        batch_op.drop_column("customer_name")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("password_changed_at")
