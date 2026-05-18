"""Telegram Login Widget авторизация + сессии через подписанные cookie + RBAC."""
import hashlib
import hmac
import time
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select

from shared.db import async_session
from shared.models import User

from .config import config

SESSION_COOKIE = "travobot_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 дней
TG_AUTH_MAX_AGE = 60 * 60 * 24       # 24 часа на принятие подписи

_signer = URLSafeTimedSerializer(config.admin_secret, salt="travobot-session")


def make_session_token(telegram_id: int) -> str:
    return _signer.dumps({"tg": telegram_id})


def verify_session_token(token: str) -> Optional[int]:
    try:
        data = _signer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    return int(data.get("tg")) if data and "tg" in data else None


def verify_telegram_auth(payload: dict) -> bool:
    """Проверка подписи Telegram Login Widget. Документация:
    https://core.telegram.org/widgets/login#checking-authorization
    """
    received_hash = payload.pop("hash", None)
    if not received_hash:
        return False

    auth_date = int(payload.get("auth_date", 0))
    if auth_date <= 0 or time.time() - auth_date > TG_AUTH_MAX_AGE:
        return False

    data_check_string = "\n".join(
        f"{k}={payload[k]}" for k in sorted(payload.keys())
    )
    secret_key = hashlib.sha256(config.bot_token.encode()).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(calc_hash, received_hash)


async def upsert_user_from_tg(payload: dict) -> User:
    """Создаёт юзера по данным от Telegram Login Widget или обновляет существующего."""
    tg_id = int(payload["id"])
    username = (payload.get("username") or "").lstrip("@").lower()

    async with async_session() as s:
        existing = (
            await s.execute(select(User).where(User.telegram_id == tg_id))
        ).scalar_one_or_none()

        if existing is None:
            # Юзера в БД нет. Создаём его автоматически только если он в whitelist
            # INITIAL_ADMINS из .env. Все остальные должны быть добавлены админом
            # вручную через /users перед первым логином.
            if username and username in config.initial_admins:
                role = "admin"
            else:
                raise HTTPException(status_code=403, detail="Access denied")

            new_user = User(
                telegram_id=tg_id,
                username=username,
                first_name=payload.get("first_name", ""),
                photo_url=payload.get("photo_url", ""),
                role=role,
            )
            s.add(new_user)
            await s.commit()
            await s.refresh(new_user)
            return new_user

        # Обновим то что могло поменяться
        existing.username = username or existing.username
        existing.first_name = payload.get("first_name", existing.first_name)
        existing.photo_url = payload.get("photo_url", existing.photo_url)
        await s.commit()
        await s.refresh(existing)
        return existing


class RedirectToLogin(Exception):
    def __init__(self, next_url: str):
        self.next_url = next_url


async def current_user(
    request: Request,
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    """FastAPI dependency - возвращает текущего юзера или бросает RedirectToLogin
    (превращается в редирект через exception_handler в main.py)."""
    next_url = str(request.url.path)
    if not session:
        raise RedirectToLogin(next_url)

    tg_id = verify_session_token(session)
    if tg_id is None:
        raise RedirectToLogin(next_url)

    async with async_session() as s:
        user = (
            await s.execute(select(User).where(User.telegram_id == tg_id))
        ).scalar_one_or_none()
    if user is None:
        raise RedirectToLogin(next_url)
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user
