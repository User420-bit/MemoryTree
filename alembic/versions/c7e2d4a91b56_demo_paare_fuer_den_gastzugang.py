"""Gastzugang: is_demo + expires_at auf couples

Revision ID: c7e2d4a91b56
Revises: b1f4a7c9e230
Create Date: 2026-09-18

Ein Gast bekommt ein eigenes Wegwerf-Paar, das aus ``demo_data.py`` befüllt
wird. ``is_demo`` markiert diese Paare, ``expires_at`` sagt dem Aufräumlauf,
ab wann sie gelöscht werden dürfen. Bestehende Paare sind echte Paare und
bekommen über den ``server_default`` ``is_demo = false``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7e2d4a91b56"
down_revision: Union[str, Sequence[str], None] = "b1f4a7c9e230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("couples", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_demo", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )
        batch_op.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(batch_op.f("ix_couples_is_demo"), ["is_demo"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("couples", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_couples_is_demo"))
        batch_op.drop_column("expires_at")
        batch_op.drop_column("is_demo")
