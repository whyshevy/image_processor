import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config:
    """Base configuration."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    PROCESSED_FOLDER = os.path.join(BASE_DIR, "processed")
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB max upload

    SUPPORTED_EXTENSIONS = (
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".mpo",
        ".nef", ".cr2", ".psd", ".cr3", ".arw", ".dng", ".rw2",
    )
    JPEG_QUALITY = 92
    TRY_RAWPY = True

    PREVIEW_LIMIT = 300
    KEYWORDS_LIMIT = 20

    # MS SQL Server
    DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    DB_SERVER = os.getenv("DB_SERVER", "192.168.1.100,1433")
    DB_NAME = os.getenv("DB_NAME", "ProcessedMedia")
    DB_USER = os.getenv("DB_USER", "sa")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Media root — for Synology deployments, set to the mount point (e.g. /media).
    # Empty string means local/Windows mode (tkinter picker + drive search).
    MEDIA_ROOT = os.getenv("MEDIA_ROOT", "")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
