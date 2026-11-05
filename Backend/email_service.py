"""
CodeMind Email Service
Integrates Brevo's official Transactional Email API (https://api.brevo.com/v3/smtp/email)
with fallback to SMTP and mock test handling. Never exposes API keys, tokens, or OTP codes.
"""

import os
import re
import logging
from typing import Dict, Any, Optional, Tuple
import httpx

logger = logging.getLogger("codemind.email")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def is_brevo_configured() -> bool:
    """Returns True if the BREVO_API_KEY environment variable is present and non-empty."""
    return bool(os.environ.get("BREVO_API_KEY", "").strip())


def get_brevo_config() -> Dict[str, str]:
    """
    Reads Brevo configuration strictly from backend environment variables.
    Never exposes API keys in frontend responses or logs.
    """
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender_email = (
        os.environ.get("BREVO_SENDER_EMAIL", "").strip()
        or os.environ.get("SMTP_FROM", "").strip()
        or "codemind.verify@gmail.com"
    )
    sender_name = (
        os.environ.get("BREVO_SENDER_NAME", "").strip()
        or "CodeMind"
    )
    return {
        "api_key": api_key,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "api_url": BREVO_API_URL,
    }


def send_brevo_email(
    to_email: str,
    recipient_name: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> Dict[str, Any]:
    """
    Sends a transactional email via Brevo's official v3 API endpoint.

    Returns:
        dict: {"success": bool, "message_id": Optional[str], "error": Optional[str], "status_code": Optional[int]}
    """
    cfg = get_brevo_config()
    if not cfg["api_key"]:
        return {
            "success": False,
            "error": "BREVO_API_KEY is not configured.",
            "status_code": 500,
        }

    clean_email = to_email.strip().lower()
    clean_name = (recipient_name or clean_email.split("@")[0]).strip()

    payload = {
        "sender": {
            "name": cfg["sender_name"],
            "email": cfg["sender_email"],
        },
        "to": [
            {
                "email": clean_email,
                "name": clean_name,
            }
        ],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }

    headers = {
        "api-key": cfg["api_key"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=BREVO_TIMEOUT) as client:
            resp = client.post(BREVO_API_URL, json=payload, headers=headers)
            status_code = resp.status_code
            data = resp.json() if resp.content else {}

            if 200 <= status_code < 300:
                msg_id = data.get("messageId")
                logger.info(
                    "Brevo transactional email sent successfully to %s: '%s' (messageId: %s)",
                    clean_email,
                    subject,
                    msg_id,
                )
                return {
                    "success": True,
                    "message_id": msg_id,
                    "status_code": status_code,
                    "error": None,
                }
            else:
                raw_err = data.get("message") or data.get("code") or resp.text
                safe_err = f"Brevo HTTP {status_code}: {raw_err}"
                # Redact any accidental secret reflection
                if cfg["api_key"] and cfg["api_key"] in safe_err:
                    safe_err = safe_err.replace(cfg["api_key"], "[REDACTED_API_KEY]")
                logger.warning(
                    "Brevo transactional email rejected for %s (subject: '%s'): %s",
                    clean_email,
                    subject,
                    safe_err,
                )
                return {
                    "success": False,
                    "error": safe_err,
                    "status_code": status_code,
                    "message_id": None,
                }
    except httpx.ConnectTimeout:
        logger.error("Connection timeout while contacting Brevo API for %s", clean_email)
        return {
            "success": False,
            "error": "Connection timeout contacting email delivery provider.",
            "status_code": 504,
        }
    except httpx.ReadTimeout:
        logger.error("Read timeout from Brevo API for %s", clean_email)
        return {
            "success": False,
            "error": "Read timeout from email delivery provider.",
            "status_code": 504,
        }
    except httpx.RequestError as exc:
        logger.error("Network request error communicating with Brevo API: %s", type(exc).__name__)
        return {
            "success": False,
            "error": f"Network error contacting email provider: {type(exc).__name__}",
            "status_code": 502,
        }
    except Exception as exc:
        logger.error("Unexpected error in Brevo email delivery: %s", exc, exc_info=True)
        return {
            "success": False,
            "error": f"Internal email delivery error: {type(exc).__name__}",
            "status_code": 500,
        }


# ---------------------------------------------------------------------------
# Branded Templates (Preserving CodeMind Design & Formatting)
# ---------------------------------------------------------------------------

def build_otp_email_template(
    display_name: str,
    otp: str,
    purpose: str = "Email Verification",
) -> Tuple[str, str, str]:
    """
    Builds subject, HTML body, and plain-text body for an OTP verification email.
    Preserves CodeMind's dark and gold branded typography.
    """
    subject = f"CodeMind {purpose} Code"
    clean_name = display_name or "Learner"

    text_body = (
        f"Hello {clean_name},\n\n"
        f"Your CodeMind {purpose} code is: {otp}\n\n"
        f"This code expires in 10 minutes. Do not share it with anyone.\n\n"
        f"— The CodeMind Team"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>CodeMind {purpose}</title>
</head>
<body style="margin:0;padding:0;background-color:#08090d;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#f8fafc;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#08090d;padding:40px 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:540px;background:#0f172a;border:1px solid rgba(212,175,55,0.3);border-radius:12px;padding:32px 28px;box-shadow:0 8px 32px rgba(0,0,0,0.4);">
          <tr>
            <td align="center" style="padding-bottom:24px;">
              <div style="font-size:26px;font-weight:800;letter-spacing:1px;color:#f8fafc;">
                Code<span style="color:#d4af37;">Mind</span>
              </div>
              <div style="font-size:12px;color:#94a3b8;margin-top:4px;">Master Algorithms with Maya AI Tutor</div>
            </td>
          </tr>
          <tr>
            <td style="font-size:15px;line-height:1.6;color:#e2e8f0;padding-bottom:16px;">
              Hello <strong style="color:#f8fafc;">{clean_name}</strong>,
            </td>
          </tr>
          <tr>
            <td style="font-size:14px;line-height:1.6;color:#cbd5e1;padding-bottom:20px;">
              Your 6-digit <strong>{purpose}</strong> verification code is:
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:16px 0 24px 0;">
              <div style="display:inline-block;background:rgba(212,175,55,0.1);border:1px solid rgba(212,175,55,0.4);border-radius:8px;padding:14px 28px;font-family:'Courier New',Courier,monospace;font-size:36px;font-weight:800;letter-spacing:10px;color:#d4af37;">
                {otp}
              </div>
            </td>
          </tr>
          <tr>
            <td style="font-size:13px;line-height:1.6;color:#94a3b8;padding-bottom:24px;text-align:center;">
              ⏰ This verification code is valid for <strong>10 minutes</strong>.<br>
              For your account security, never share this code with anyone.
            </td>
          </tr>
          <tr>
            <td style="border-top:1px solid #1e293b;padding-top:18px;font-size:11px;color:#64748b;text-align:center;">
              If you did not request this verification code, you can safely ignore this email.<br>
              © CodeMind Platform. All rights reserved.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, html_body, text_body


def build_welcome_email_template(
    display_name: str,
    app_base_url: str = "https://codemind-frontend-rosy.vercel.app",
) -> Tuple[str, str, str]:
    """Builds subject and bodies for a one-time welcome email upon verification."""
    subject = "Welcome to CodeMind! 🎉"
    clean_name = display_name or "Learner"

    text_body = (
        f"Hello {clean_name},\n\n"
        f"🎉 Your CodeMind account is now fully verified and active!\n\n"
        f"You are ready to begin learning data structures, solving algorithmic problems, "
        f"and pairing with Maya, your dedicated AI tutor.\n\n"
        f"Access CodeMind: {app_base_url}\n\n"
        f"Happy coding!\n— The CodeMind Team"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#08090d;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#f8fafc;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#08090d;padding:40px 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:540px;background:#0f172a;border:1px solid rgba(212,175,55,0.3);border-radius:12px;padding:32px 28px;">
          <tr>
            <td align="center" style="padding-bottom:20px;">
              <div style="font-size:26px;font-weight:800;color:#f8fafc;">Code<span style="color:#d4af37;">Mind</span></div>
            </td>
          </tr>
          <tr>
            <td style="font-size:16px;line-height:1.6;color:#e2e8f0;padding-bottom:12px;">
              🎉 Welcome aboard, <strong>{clean_name}</strong>!
            </td>
          </tr>
          <tr>
            <td style="font-size:14px;line-height:1.6;color:#cbd5e1;padding-bottom:20px;">
              Your account has been verified successfully. You now have full access to our curated problem library, live code execution engine, and Maya AI companion.
            </td>
          </tr>
          <tr>
            <td align="center" style="padding-bottom:24px;">
              <a href="{app_base_url}" style="background:#d4af37;color:#08090d;padding:12px 28px;text-decoration:none;border-radius:6px;font-weight:700;font-size:14px;display:inline-block;">
                Launch CodeMind Workspace →
              </a>
            </td>
          </tr>
          <tr>
            <td style="border-top:1px solid #1e293b;padding-top:16px;font-size:11px;color:#64748b;text-align:center;">
              Happy coding! — The CodeMind Team
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, html_body, text_body
