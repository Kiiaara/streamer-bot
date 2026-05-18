"""Конфиг админки. Читает .env."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str          # для проверки Telegram-подписи
    bot_username: str       # для виджета (без @)
    admin_secret: str       # для подписи cookie
    admin_domain: str       # admin.travobot-workflow.ru
    initial_admins: list[str]  # whitelist Telegram username которым выдаём роль admin при первом входе
    images_dir: str         # /app/static/images
    db_path: str


def _split_admins(raw: str) -> list[str]:
    return [u.strip().lstrip("@").lower() for u in raw.split(",") if u.strip()]


def load_config() -> Config:
    return Config(
        bot_token=os.environ["BOT_TOKEN"],
        bot_username=os.environ.get("TG_BOT_USERNAME", "").lstrip("@"),
        admin_secret=os.environ["ADMIN_SECRET"],
        admin_domain=os.environ.get("ADMIN_DOMAIN", ""),
        initial_admins=_split_admins(os.environ.get("INITIAL_ADMINS", "")),
        images_dir=os.environ.get("IMAGES_DIR", "/app/static/images"),
        db_path=os.environ.get("DB_PATH", "/app/data/travobot.db"),
    )


config = load_config()
