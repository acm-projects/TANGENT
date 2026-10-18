import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from jinja2 import Template

from app.core.templates import INVITATION_EMAIL_HTML

FRONTEND_URL = (os.getenv("FRONTEND_URL") or "http://localhost:5173").rstrip("/")

DEFAULT_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "tangent-logo-white.png"

def send_invite_email(to_email: str, token: str, project_name: str, inviter_name: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    frontend_url = FRONTEND_URL

    if not smtp_user or not smtp_password:
        print("CRITICAL: SMTP credentials are missing from environment variables.")
        return False

    project_name = " ".join(project_name.split())
    inviter_name = " ".join(inviter_name.split())

    invite_url = f"{frontend_url}/invite/{token}"

    logo_path = Path(os.getenv("EMAIL_LOGO_PATH") or DEFAULT_LOGO_PATH)
    logo_bytes = None
    try:
        logo_bytes = logo_path.read_bytes()
        if not logo_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            print(f"WARNING: {logo_path} is not a valid PNG; sending without logo.")
            logo_bytes = None
    except OSError:
        print(f"WARNING: logo not found at {logo_path}; sending without logo.")

    logo_cid = make_msgid(domain="tangent.local")
    logo_url = f"cid:{logo_cid[1:-1]}" if logo_bytes else ""

    template = Template(INVITATION_EMAIL_HTML, autoescape=True)
    html_content = template.render(
        inviter_name=inviter_name,
        project_name=project_name,
        invite_url=invite_url,
        logo_url=logo_url,
    )

    text_fallback = f"{inviter_name} has invited you to join {project_name}. Visit {invite_url} to accept your invite."

    try:
        message = EmailMessage()
        message["Subject"] = f"Invitation to join {project_name} on Tangent"
        message["From"] = smtp_user
        message["To"] = to_email
        message.set_content(text_fallback)
        message.add_alternative(html_content, subtype="html")
        if logo_bytes:
            message.get_payload()[1].add_related(logo_bytes, "image", "png", cid=logo_cid)

        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, message.as_string())
        return True
    except Exception as e:
        print(f"SMTP Transmission Failure to {to_email}: {str(e)}")
        return False