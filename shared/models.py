"""SQLAlchemy 2.0 модели - общие для бота и админки.

БД - SQLite, хранится в общем volume /app/data/travobot.db.
Бот читает (и пишет логи), админка читает/пишет всё.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="")
    subcategory: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")  # HTML, санитайзится в админке
    keywords: Mapped[str] = mapped_column(Text, default="")
    image: Mapped[str] = mapped_column(String(255), default="")  # имя файла в static/images/
    button_text: Mapped[str] = mapped_column(String(64), default="")  # текст кнопки перехода (если пусто - дефолт "Перейти →")
    position: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # скрытые не показываются в боте
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_content_section_pos", "section", "position"),
    )


class AutoComment(Base):
    __tablename__ = "auto_comments"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    topic: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text, default="")  # HTML
    buttons_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{"title","url"}]
    image: Mapped[str] = mapped_column(String(255), default="")  # имя файла в static/images/
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Channel(Base):
    __tablename__ = "channels"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(64), default="все")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Section(Base):
    """Раздел верхнего уровня (Сайт, Соцсети, ...). Связь с ContentItem - по имени (мягкая)."""
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")  # HTML, очищается санитайзером
    image: Mapped[str] = mapped_column(String(255), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # скрытые не показываются в боте, в админке доступны
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Category(Base):
    """Описание/картинка для категории или подкатегории. Связь с ContentItem мягкая - по тройке (section, category, subcategory).

    Если subcategory == "" - это category верхнего уровня (например "Telegram" в Соцсетях).
    Если subcategory заполнен - это конкретная подкатегория (например Соцсети→Telegram→Dota 2).
    """
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subcategory: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_categories_lookup", "section", "category", "subcategory", unique=True),
    )


class User(Base):
    """Юзеры админки (не путать с юзерами Telegram-бота - тут только те у кого есть доступ к админке)."""
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    first_name: Mapped[str] = mapped_column(String(128), default="")
    photo_url: Mapped[str] = mapped_column(String(512), default="")
    role: Mapped[str] = mapped_column(String(16), default="editor")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('admin','editor')", name="ck_users_role"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32))  # create/update/delete/login
    entity: Mapped[str] = mapped_column(String(32))  # content/auto_comment/channel/setting/user
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User")


class Event(Base):
    """Сырые события активности бота. Хранятся 30 дней, потом удаляются демоном.
    Свёрнутая статистика лежит в DailyStat."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # click_section / click_category / click_subcategory / click_leaf / search / auto_comment
    target: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_events_created", "created_at"),
        Index("ix_events_type", "event_type"),
    )


class DailyStat(Base):
    """Свёрнутая статистика по дням. Хранится вечно."""
    __tablename__ = "daily_stats"

    date: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    unique_users: Mapped[int] = mapped_column(Integer, default=0)
    total_clicks: Mapped[int] = mapped_column(Integer, default=0)
    searches: Mapped[int] = mapped_column(Integer, default=0)
    auto_comments: Mapped[int] = mapped_column(Integer, default=0)
    by_section: Mapped[str] = mapped_column(Text, default="{}")    # JSON {section: count}
    by_category: Mapped[str] = mapped_column(Text, default="{}")
    by_link: Mapped[str] = mapped_column(Text, default="[]")        # JSON [[url, count], ...]
    by_hour: Mapped[str] = mapped_column(Text, default="{}")        # JSON {0..23: count}
    top_searches: Mapped[str] = mapped_column(Text, default="[]")   # JSON [[term, count], ...]
