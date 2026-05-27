"""SMTP-отправитель кодов входа. Читает SMTP_* из env."""
import os
import smtplib
import ssl
from email.message import EmailMessage


def send_login_code(to_email: str, code: str, brand: str = "Травобот") -> None:
    """Отправляет 6-значный код на email. Бросает исключение если SMTP не настроен."""
    smtp_host = os.environ.get("SMTP_HOST", "smtp.mail.ru")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_password:
        raise RuntimeError("SMTP не настроен (SMTP_USER/SMTP_PASSWORD)")

    msg = EmailMessage()
    msg["Subject"] = f"Код входа в {brand}: {code}"
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(
        f"Ваш код для входа в {brand}: {code}\n\n"
        f"Код действителен 5 минут. Если вы не запрашивали вход - просто проигнорируйте письмо."
    )
    msg.add_alternative(
        f"""<html><body style="font-family:sans-serif">
<h2 style="color:#10b981">{brand}</h2>
<p>Код для входа:</p>
<div style="font-size:32px;font-weight:bold;letter-spacing:6px;background:#f3f4f6;padding:16px 24px;border-radius:8px;display:inline-block">{code}</div>
<p style="color:#666;margin-top:24px">Код действителен 5 минут.<br>Если вы не запрашивали вход - просто проигнорируйте письмо.</p>
</body></html>""",
        subtype="html",
    )

    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=15) as srv:
            srv.login(smtp_user, smtp_password)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as srv:
            srv.starttls(context=context)
            srv.login(smtp_user, smtp_password)
            srv.send_message(msg)
