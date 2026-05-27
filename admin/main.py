"""FastAPI app админки Травобота."""
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.db import async_session, init_db
from shared.models import User

from .auth import (
    EMAIL_CODE_TTL_MINUTES,
    RedirectToLogin,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    create_email_code,
    current_user,
    find_user_by_email,
    make_session_token,
    normalize_email,
    upsert_user_from_tg,
    verify_email_code,
    verify_telegram_auth,
)
from .common import ensure_default_sections, get_section_names
from .config import config
from .routes import analytics, auto_comments, categories, channels, content, sections, settings_routes, users

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("admin")

BASE_DIR = Path(__file__).parent

app = FastAPI(title="Травобот - админка")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# Картинки контента раздаём через тот же путь что бот их видит
app.mount("/uploads", StaticFiles(directory=config.images_dir), name="uploads")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
async def startup():
    await init_db()
    await ensure_default_sections()
    log.info(f"Админка запущена. Bot: @{config.bot_username}, домен: {config.admin_domain}")


@app.exception_handler(RedirectToLogin)
async def handle_redirect_to_login(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url=f"/login?next={exc.next_url}", status_code=307)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "bot_username": config.bot_username,
            "auth_url": "/auth/callback",
            "next": next,
        },
    )


@app.get("/auth/callback")
async def auth_callback(request: Request):
    """Telegram Login Widget шлёт сюда GET с параметрами id, first_name, username, photo_url, auth_date, hash."""
    payload = dict(request.query_params)
    next_url = payload.pop("next", "/") or "/"

    if not verify_telegram_auth(payload.copy()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad Telegram signature")

    try:
        user = await upsert_user_from_tg(payload)
    except HTTPException:
        return RedirectResponse(url="/access-denied", status_code=303)

    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(user.telegram_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@app.get("/access-denied", response_class=HTMLResponse)
async def access_denied(request: Request):
    return templates.TemplateResponse(
        "access_denied.html",
        {"request": request, "bot_username": config.bot_username},
    )


# ── Login по email + коду ─────────────────────────────────

class EmailRequestIn(BaseModel):
    email: str


class EmailVerifyIn(BaseModel):
    email: str
    code: str


@app.post("/auth/email/request")
async def email_request(data: EmailRequestIn):
    """Шлёт код на email если этот email есть в whitelist (= User с заполненным email)."""
    email = normalize_email(data.email)
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Некорректный email")

    # bootstrap: если в БД вообще нет юзеров - разрешаем войти первому
    from sqlalchemy import select as _select, func as _func
    from shared.models import User as _User
    async with async_session() as s:
        total = (await s.execute(_select(_func.count()).select_from(_User))).scalar_one()
    has_any = (total or 0) > 0

    if has_any:
        user = await find_user_by_email(email)
        if not user:
            # антиперебор: не палим что email не в whitelist
            return {"ok": True, "expires_in": EMAIL_CODE_TTL_MINUTES * 60}

    code = await create_email_code(email)
    try:
        from shared.email_sender import send_login_code
        send_login_code(email, code, brand="Травобот")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось отправить письмо: {e}")
    return {"ok": True, "expires_in": EMAIL_CODE_TTL_MINUTES * 60}


@app.post("/auth/email/verify")
async def email_verify(data: EmailVerifyIn):
    """Проверяет код, ставит session cookie. Bootstrap: первый email-юзер становится admin."""
    email = normalize_email(data.email)
    await verify_email_code(email, data.code.strip())

    from sqlalchemy import select as _select, func as _func
    from shared.models import User as _User
    async with async_session() as s:
        total = (await s.execute(_select(_func.count()).select_from(_User))).scalar_one()
        has_any = (total or 0) > 0
        if not has_any:
            # первый юзер - admin. telegram_id = -1 заглушка
            new_user = _User(telegram_id=-1, email=email, role="admin", first_name=email)
            s.add(new_user)
            await s.commit()
            await s.refresh(new_user)
            user_tg_id = new_user.telegram_id
        else:
            user = (await s.execute(_select(_User).where(_User.email == email))).scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=403, detail="Email не в списке разрешённых")
            user_tg_id = user.telegram_id

    response = JSONResponse({"ok": True, "email": email})
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(user_tg_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(current_user)):
    names = await get_section_names()
    if not names:
        return RedirectResponse(url="/sections-manage", status_code=303)
    return RedirectResponse(url=f"/section/{names[0]}", status_code=303)


# Роутеры
app.include_router(content.router)
app.include_router(categories.router)
app.include_router(sections.router)
app.include_router(analytics.router)
app.include_router(auto_comments.router)
app.include_router(channels.router)
app.include_router(settings_routes.router)  # legacy, скрыто из меню
app.include_router(users.router)
