"""Account email through Azure Communication Services. No PHI: only a link or a code."""

from app.core.config import get_settings

APP_URL = "https://ileracare.app"  # verification links open the web app
FROM_EMAIL = "noreply@ileracare.app"  # a verified ACS sender domain


def _send(email: str, subject: str, html: str) -> None:
    from azure.communication.email import EmailClient

    settings = get_settings()
    EmailClient.from_connection_string(settings.acs_email_connection_string).begin_send({
        "senderAddress": FROM_EMAIL,
        "recipients": {"to": [{"address": email}]},
        "content": {"subject": subject, "html": html},
    })


def send_login_code(email: str, code: str) -> None:
    _send(email, f"{code} is your Ilera login code", (
        f"<p>Your Ilera login code is: <strong>{code}</strong></p>"
        "<p>This code expires in 10 minutes and can only be used once.</p>"
        "<p>If you did not attempt to sign in, please change your password immediately.</p>"
    ))


def send_verification_link(email: str, token: str) -> None:
    verify_url = f"{APP_URL}/verify-email?token={token}"
    _send(email, "Verify your Ilera account", (
        "<p>Thanks for creating an Ilera account.</p>"
        "<p>Click the link below to verify your email address. "
        "This link expires in 1 hour and can only be used once.</p>"
        f'<p><a href="{verify_url}">Verify my email</a></p>'
        "<p>If you did not create an Ilera account, you can safely ignore this email.</p>"
    ))
