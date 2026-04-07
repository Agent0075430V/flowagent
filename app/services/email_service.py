from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from app.config import get_settings


class EmailService:
    def __init__(self):
        self.settings = get_settings()

    def can_send_email(self) -> bool:
        return bool(
            self.settings.smtp_host
            and self.settings.smtp_port
            and self.settings.smtp_from_email
        )

    def send_otp_email(self, to_email: str, otp: str, purpose: str) -> bool:
        if not self.can_send_email():
            return False

        subject = "FlowAgent Verification Code"
        if purpose == "password_reset":
            subject = "FlowAgent Password Reset Code"

        body = (
            "Your FlowAgent OTP code is: "
            f"{otp}\n\n"
            "This code expires in 10 minutes."
        )

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.settings.smtp_from_email
        msg["To"] = to_email

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as client:
            if self.settings.smtp_use_tls:
                client.starttls()
            if self.settings.smtp_user:
                client.login(self.settings.smtp_user, self.settings.smtp_password)
            client.sendmail(self.settings.smtp_from_email, [to_email], msg.as_string())

        return True
