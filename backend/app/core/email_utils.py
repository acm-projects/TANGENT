import os
from dotenv import load_dotenv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template

from app.core.templates import INVITATION_EMAIL_HTML

load_dotenv()

is_production = os.getenv("IS_PRODUCTION") == "1"
FRONTEND_URL = (
    os.getenv("FRONTEND_URL")
    if is_production
    else "http://localhost:5173"
)

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

    template = Template(INVITATION_EMAIL_HTML, autoescape=True)
    html_content = template.render(
        inviter_name=inviter_name,
        project_name=project_name,
        invite_url=invite_url
    )

    message = MIMEMultipart("alternative")
    message["Subject"] = f"Invitation to join {project_name} on Tangent"
    message["From"] = smtp_user
    message["To"] = to_email

    text_fallback = f"{inviter_name} has invited you to join {project_name}. Visit {invite_url} to accept your invite."

    message.attach(MIMEText(text_fallback, "plain"))
    message.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, message.as_string())
        return True
    except Exception as e:
        print(f"SMTP Transmission Failure to {to_email}: {str(e)}")
        return False