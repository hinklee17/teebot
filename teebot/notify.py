"""Notifications. Never raises: a failed email must not interrupt booking.

Two ways to send, tried in order:
  1. MAIL_WEBHOOK_URL + MAIL_SECRET: a Google Apps Script web app in your Gmail account
     (server/email-relay.gs). Works on cloud servers, which block email ports.
  2. GMAIL_USER + GMAIL_APP_PASSWORD: direct Gmail SMTP (fine on GitHub Actions / home PCs).
"""
from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage


def _via_webhook(subject: str, body: str) -> bool:
    url = os.environ.get("MAIL_WEBHOOK_URL", "").strip()
    if not url:
        return False
    data = json.dumps({"secret": os.environ.get("MAIL_SECRET", ""), "subject": subject,
                       "body": body}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # follows Google's redirect
        reply = r.read().decode(errors="replace").strip()
    if reply != "ok":
        raise RuntimeError(f"email relay replied: {reply[:200]}")
    return True


def _via_smtp(subject: str, body: str) -> bool:
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pw):
        return False
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = os.environ.get("NOTIFY_TO") or user
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
        s.login(user, pw)
        s.send_message(msg)
    return True


def send_email(subject: str, body: str) -> bool:
    for how in (_via_webhook, _via_smtp):
        try:
            if how(subject, body):
                print(f"[notify] sent: {subject}", flush=True)
                return True
        except Exception as e:
            print(f"[notify] {how.__name__} failed: {e}", flush=True)
    print(f"[notify] NOT sent (no working email method): {subject}\n{body}", flush=True)
    return False


if __name__ == "__main__":  # used by the installer to send a test email
    import sys
    sys.exit(0 if send_email("⛳ Tee time bot: test email",
                             "If you're reading this, booking emails will reach you.") else 1)
