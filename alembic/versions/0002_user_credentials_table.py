"""user credentials table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "service", name="uq_user_credentials_user_service"),
    )
    op.create_index("ix_user_credentials_user_id", "user_credentials", ["user_id"])
    op.create_index("ix_user_credentials_user_service", "user_credentials", ["user_id", "service"])


def downgrade() -> None:
    op.drop_index("ix_user_credentials_user_service", table_name="user_credentials")
    op.drop_index("ix_user_credentials_user_id", table_name="user_credentials")
    op.drop_table("user_credentials")
