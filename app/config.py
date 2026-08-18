import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    admin_str = os.getenv("ADMIN_USER_IDS", "")
    ADMIN_IDS = [int(uid.strip()) for uid in admin_str.split(",") if uid.strip()]

    # UI language
    LANG = os.getenv("LANG", "ar").lower()
    if LANG not in ("ar", "en"):
        LANG = "ar"

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./store.db")

    # Provider
    STORE_PROVIDER = os.getenv("STORE_PROVIDER", "world4card").lower()
    PROVIDER_BASE_URL = os.getenv("PROVIDER_BASE_URL", "https://api.world4card.com").rstrip("/")
    PROVIDER_API_TOKEN = os.getenv("PROVIDER_API_TOKEN")
    PROVIDER_LOW_BALANCE_THRESHOLD = float(os.getenv("PROVIDER_LOW_BALANCE_THRESHOLD", "5.0"))

    # Pricing
    MARGIN_PERCENT = float(os.getenv("MARGIN_PERCENT", "20"))

    # Jobs
    CATALOG_SYNC_MINUTES = int(os.getenv("CATALOG_SYNC_MINUTES", "60"))

    # Dashboard (optional addon)
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    ADMIN_ACCESS_CODE = os.getenv("ADMIN_ACCESS_CODE")
    ADMIN_HOST = os.getenv("ADMIN_HOST", "127.0.0.1")
    ADMIN_PORT = int(os.getenv("ADMIN_PORT", "5000"))

    # Paths
    MEDIA_ROOT = "media"
    MEDIA_PRODUCTS = "media/products"
    MEDIA_SCREENSHOTS = "media/screenshots"


settings = Settings()
