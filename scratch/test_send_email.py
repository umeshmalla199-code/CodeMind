import os
import sys

# Ensure Backend is on sys.path
sys.path.insert(0, os.path.abspath("Backend"))

from routes.auth import _get_email_config, _send_smtp_email

cfg = _get_email_config()
print("Host:", cfg["host"])
print("Port:", cfg["port"])
print("User:", cfg["user"])
print("Password set:", bool(cfg["password"]), "len=", len(cfg["password"]))
print("From:", cfg["from_address"])

# Test sending to codemind.verify@gmail.com itself (which is the account)
success = _send_smtp_email(
    to_email="codemind.verify@gmail.com",
    subject="CodeMind SMTP Test Verification",
    html_body="<p>This is a test OTP: <strong>123456</strong></p>",
    text_body="This is a test OTP: 123456"
)
print("Send result:", success)
