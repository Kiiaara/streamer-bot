import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    sheets_id: str
    google_credentials: str
    groq_api_key: str
    groq_model: str
    redis_url: str
    cache_ttl: int
    log_level: str


def load_config() -> Config:
    # Все переменные обязательны кроме модели и log_level (есть дефолты)
    return Config(
        bot_token=os.environ["BOT_TOKEN"],
        sheets_id=os.environ["SHEETS_ID"],
        google_credentials=os.environ.get("GOOGLE_CREDENTIALS", "/app/credentials.json"),
        groq_api_key=os.environ["GROQ_API_KEY"],
        groq_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        cache_ttl=int(os.environ.get("CACHE_TTL", "300")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )


config = load_config()
