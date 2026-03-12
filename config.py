# Anwendungskonfiguration – lädt Einstellungen aus der .env-Datei

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Zentrale Konfigurationsklasse für Memory Tree."""

    SECRET_KEY: str = "dein-geheimer-schluessel-hier-aendern"
    DATABASE_URL: str = "sqlite:///./memory_tree.db"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    UPLOAD_DIR: str = "static/uploads"
    MAX_IMAGE_SIZE: int = 1920

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
