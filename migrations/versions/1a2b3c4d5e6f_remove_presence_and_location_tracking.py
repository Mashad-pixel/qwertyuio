"""remove QR/GPS presence verification tables

Revision ID: 1a2b3c4d5e6f
Revises: d8e9f0a1b2c3
Create Date: 2026-11-25

"""
from alembic import op
import sqlalchemy as sa


revision = "1a2b3c4d5e6f"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    # Drop dependent sessions first, then their redemptions and source tokens.
    op.drop_table("presence_sessions")
    op.drop_table("presence_redemptions")
    op.drop_table("presence_tokens")


def downgrade():
    # Restore the former schema only when explicitly downgrading this migration.
    op.create_table(
        "presence_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_by_id", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["issued_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_presence_tokens_expires_at", "presence_tokens", ["expires_at"], unique=False)
    op.create_index("ix_presence_tokens_issued_by_id", "presence_tokens", ["issued_by_id"], unique=False)
    op.create_index("ix_presence_tokens_token_hash", "presence_tokens", ["token_hash"], unique=True)

    op.create_table(
        "presence_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=False),
        sa.Column("accuracy_meters", sa.Integer(), nullable=False),
        sa.CheckConstraint("accuracy_meters >= 0", name="ck_presence_redemptions_accuracy_non_negative"),
        sa.CheckConstraint("distance_meters >= 0", name="ck_presence_redemptions_distance_non_negative"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["token_id"], ["presence_tokens.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id", "student_id", name="uq_presence_redemptions_token_student"),
    )
    op.create_index("ix_presence_redemptions_student_id", "presence_redemptions", ["student_id"], unique=False)
    op.create_index("ix_presence_redemptions_token_id", "presence_redemptions", ["token_id"], unique=False)

    op.create_table(
        "presence_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("redemption_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["redemption_id"], ["presence_redemptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_presence_sessions_order"),
        sa.UniqueConstraint("redemption_id", name="uq_presence_sessions_redemption"),
    )
    op.create_index("ix_presence_sessions_expires_at", "presence_sessions", ["expires_at"], unique=False)
    op.create_index("ix_presence_sessions_session_hash", "presence_sessions", ["session_hash"], unique=True)
    op.create_index("ix_presence_sessions_student_id", "presence_sessions", ["student_id"], unique=False)
