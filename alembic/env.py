import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Projektverzeichnis zum Python-Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import DATABASE_URL, IS_SQLITE, Base  # noqa: E402
from models import *  # noqa: E402, F401, F403 — alle Modelle importieren für Autogenerate

# Alembic Config-Objekt
config = context.config

# DB-URL aus Settings übernehmen (bereits auf den psycopg-Treiber normalisiert).
# %-Zeichen escapen: ConfigParser würde sie sonst als Interpolation deuten —
# in URL-kodierten Passwörtern (%2F o. ä.) ein realer Stolperstein.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

# Logging konfigurieren
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadaten für Autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Migrationen im Offline-Modus ausführen."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=IS_SQLITE,  # batch-Modus nur für SQLite nötig
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migrationen im Online-Modus ausführen."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=IS_SQLITE,  # batch-Modus nur für SQLite nötig
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
