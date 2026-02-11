
import json
import logging
import mimetypes
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_credentials() -> tuple[str, str, str]:
    """Load email credentials from env vars or credentials.json file.

    Environment variables take precedence:
        EMAIL, PASSWORD, RECIPIENT

    Falls back to credentials.json in the same directory as this module.

    Returns:
        (email_address, email_password, recipient)

    Raises:
        ValueError: If any required field is missing.
    """
    email_address = os.environ.get("EMAIL", "")
    email_password = os.environ.get("PASSWORD", "")
    recipient = os.environ.get("RECIPIENT", "")

    if email_address and email_password and recipient:
        return email_address, email_password, recipient

    credentials_path = Path(__file__).with_name("credentials.json")
    if credentials_path.exists():
        with credentials_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        email_address = email_address or data.get("email", "")
        email_password = email_password or data.get("password", "")
        recipient = recipient or data.get("recipient", "")

    if not email_address:
        raise ValueError(
            "Missing 'email': set the EMAIL env var or 'email' in credentials.json"
        )
    if not email_password:
        raise ValueError(
            "Missing 'password': set the PASSWORD env var or 'password' in credentials.json"
        )
    if not recipient:
        raise ValueError(
            "Missing 'recipient': set the RECIPIENT env var or 'recipient' in credentials.json"
        )

    return email_address, email_password, recipient


def SendMail(screenshot_dir: str = "./screenshot") -> None:
    email_address, email_password, recipient = _load_credentials()

    msg = EmailMessage()
    msg["Subject"] = "Service Started"
    msg["From"] = email_address
    msg["To"] = recipient

    msg.set_content('This is a plain text email')
    screenshot_path = Path(screenshot_dir)
    for image_path in sorted(screenshot_path.iterdir()):
        if not image_path.is_file():
            continue
        logger.debug("%s attached", image_path.name)
        file_data = image_path.read_bytes()
        mime_type, _ = mimetypes.guess_type(image_path.name)
        if mime_type:
            maintype, subtype = mime_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            file_data,
            maintype=maintype,
            subtype=subtype,
            filename=image_path.name,
        )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(email_address, email_password)
            smtp.send_message(msg)
    except TimeoutError:
        logger.error("SMTP connection timed out connecting to smtp.gmail.com:465")
        raise
    except smtplib.SMTPException:
        logger.exception("SMTP error while sending mail")
        raise


if __name__ == "__main__":
    SendMail()
