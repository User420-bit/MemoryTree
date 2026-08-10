"""Mandantentrennung: couples + invites, couple_id auf allen Datentabellen

Revision ID: b1f4a7c9e230
Revises: d85c3a73c2a2
Create Date: 2026-08-09

Bis hierher war die Datenbank für genau ein Paar ausgelegt: alle Zeilen waren
global, ``couple_settings`` ein Singleton. Diese Revision führt ``couples`` als
Mandanten-Einheit ein und hängt jede bestehende Zeile an ein Standard-Paar, das
hier angelegt wird — bestehende Installationen (Pi wie Vercel) migrieren damit
ohne Datenverlust.

``photos`` und ``places`` bekommen bewusst kein eigenes ``couple_id``: sie
hängen über ``memory_id`` an einer Erinnerung und erben deren Zugehörigkeit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1f4a7c9e230"
down_revision: Union[str, Sequence[str], None] = "d85c3a73c2a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabellen, die ein couple_id bekommen. couple_settings kaskadiert, weil eine
# Einstellungszeile ohne ihr Paar bedeutungslos ist; users/memories/milestones
# bleiben bewusst ohne ON DELETE, damit ein Paar nicht versehentlich samt
# Inhalten verschwindet.
_TENANT_TABLES: tuple[tuple[str, str | None], ...] = (
    ("users", None),
    ("memories", None),
    ("milestones", None),
    ("couple_settings", "CASCADE"),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "couples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("couples", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_couples_id"), ["id"], unique=False)

    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("couple_id", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["couple_id"], ["couples.id"], name="fk_invites_couple_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invites_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_invites_code"), ["code"], unique=True)
        batch_op.create_index(batch_op.f("ix_invites_couple_id"), ["couple_id"], unique=False)

    # Standard-Paar für den vorhandenen Datenbestand. Wird auch auf einer
    # frischen Datenbank angelegt, damit scripts/seed.py ein Ziel-Paar vorfindet.
    op.execute(
        sa.text(
            "INSERT INTO couples (id, name, created_at) "
            "VALUES (1, 'Standard', CURRENT_TIMESTAMP)"
        )
    )

    # Die explizite id=1 umgeht die Postgres-Sequenz — ohne setval vergäbe der
    # nächste INSERT erneut die 1 und liefe in einen Primärschlüssel-Konflikt.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence('couples', 'id'), 1, true)"
            )
        )

    # couple_id in drei Schritten: nullable anlegen → backfillen → NOT NULL.
    # Ein direktes NOT-NULL-ADD würde auf jeder nicht-leeren Tabelle scheitern.
    for table, ondelete in _TENANT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("couple_id", sa.Integer(), nullable=True))

        op.execute(sa.text(f"UPDATE {table} SET couple_id = 1"))

        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "couple_id", existing_type=sa.Integer(), nullable=False
            )
            batch_op.create_foreign_key(
                f"fk_{table}_couple_id", "couples", ["couple_id"], ["id"],
                ondelete=ondelete,
            )
            batch_op.create_index(
                f"ix_{table}_couple_id",
                ["couple_id"],
                # Genau eine Einstellungszeile pro Paar — die frühere
                # Singleton-Invariante, jetzt pro Mandant durchgesetzt.
                unique=(table == "couple_settings"),
            )


def downgrade() -> None:
    """Downgrade schema."""
    for table, _ondelete in reversed(_TENANT_TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(f"ix_{table}_couple_id")
            batch_op.drop_constraint(f"fk_{table}_couple_id", type_="foreignkey")
            batch_op.drop_column("couple_id")

    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invites_couple_id"))
        batch_op.drop_index(batch_op.f("ix_invites_code"))
        batch_op.drop_index(batch_op.f("ix_invites_id"))
    op.drop_table("invites")

    with op.batch_alter_table("couples", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_couples_id"))
    op.drop_table("couples")
