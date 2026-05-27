"""Async SQLAlchemy engine + session factory. Используется и ботом, и админкой."""
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base

DB_PATH = os.environ.get("DB_PATH", "/app/data/travobot.db")
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DB_URL, echo=False, future=True)
async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def _ensure_column(conn, table: str, column: str, ddl_type: str, default_sql: str):
    """Добавляет колонку в существующую таблицу если её ещё нет (для SQLite, без alembic)."""
    rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).all()
    existing = {r[1] for r in rows}
    if column not in existing:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type} DEFAULT {default_sql}"))


async def init_db():
    """Создаёт таблицы если их ещё нет. Вызывается при старте бота и админки."""
    # Убедимся что папка существует
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Лёгкие миграции: добавляем колонки которых может не быть в старой БД
        await _ensure_column(conn, "sections", "hidden", "BOOLEAN", "0")
        await _ensure_column(conn, "content_items", "hidden", "BOOLEAN", "0")
        await _ensure_column(conn, "auto_comments", "image", "VARCHAR(255)", "''")
        await _ensure_column(conn, "users", "email", "VARCHAR(255)", "''")
