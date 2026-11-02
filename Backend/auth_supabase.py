"""
Supabase Auth Integration Module for CodeMind.
Provides integration with Supabase GoTrue Auth service using official REST APIs.
- Registers users through GoTrue
- Dispatches verification emails & 6-digit OTPs via custom SMTP configured in Supabase
- Verifies 6-digit email OTPs and confirmation links
- Syncs existing accounts to Supabase Auth seamlessly without forcing password resets
- Keeps service role credentials strictly server-side
"""
import os
import json
import base64
import logging
from typing import Optional, Dict, Any, Tuple
import httpx
try:
    import config
except ImportError:
    pass

logger = logging.getLogger("codemind.auth.supabase")

def _get_supabase_config() -> Dict[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    anon_key = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    jwt_secret = (os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
    return {
        "url": url,
        "anon_key": anon_key,
        "service_key": service_key,
        "jwt_secret": jwt_secret,
    }

def is_supabase_auth_enabled() -> bool:
    """Returns True if full Supabase Auth credentials are configured."""
    cfg = _get_supabase_config()
    return bool(cfg["url"] and cfg["anon_key"] and cfg["service_key"])

def _anon_headers() -> Dict[str, str]:
    cfg = _get_supabase_config()
    return {
        "apikey": cfg["anon_key"],
        "Authorization": f"Bearer {cfg['anon_key']}",
        "Content-Type": "application/json",
    }

def _admin_headers() -> Dict[str, str]:
    cfg = _get_supabase_config()
    return {
        "apikey": cfg["service_key"],
        "Authorization": f"Bearer {cfg['service_key']}",
        "Content-Type": "application/json",
    }

def supabase_signup(
    email: str,
    password: str,
    username: str,
    display_name: str,
    redirect_to: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers a new user in Supabase Auth GoTrue.
    Supabase dispatches the 6-digit OTP and/or confirmation link via the configured custom SMTP.
    """
    if not is_supabase_auth_enabled():
        return {"success": False, "error": "Supabase Auth is not enabled in environment."}

    cfg = _get_supabase_config()
    url = f"{cfg['url']}/auth/v1/signup"
    params = {}
    if redirect_to:
        params["redirect_to"] = redirect_to

    payload = {
        "email": email.strip().lower(),
        "password": password,
        "data": {
            "username": username.strip(),
            "display_name": display_name.strip(),
        }
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=_anon_headers(), params=params)
            data = resp.json() if resp.content else {}

            if resp.status_code in (200, 201):
                # When email confirmation is enabled, GoTrue returns the created user
                uid = data.get("id")
                identities = data.get("identities", [])
                # If identities list is empty, GoTrue indicates user already exists in auth.users
                if identities == [] and not data.get("created_at"):
                    return {
                        "success": False,
                        "already_registered": True,
                        "error": "A user with this email address has already been registered."
                    }
                return {
                    "success": True,
                    "supabase_uid": uid,
                    "user": data,
                    "confirmation_sent": bool(data.get("confirmation_sent_at"))
                }
            elif resp.status_code == 429:
                return {
                    "success": False,
                    "rate_limited": True,
                    "error": "Email delivery rate limit reached. Please wait a few moments before requesting another code."
                }
            else:
                err_msg = data.get("msg") or data.get("message") or data.get("error_description") or "Failed to register with Supabase Auth."
                return {"success": False, "error": err_msg, "status_code": resp.status_code}
    except Exception as exc:
        logger.error("Supabase signup request error: %s", exc)
        return {"success": False, "error": f"Supabase Auth connection error: {str(exc)}"}

def supabase_verify_otp(
    email: str,
    token: str,
    otp_type: str = "signup"
) -> Dict[str, Any]:
    """
    Verifies a 6-digit numerical OTP code with Supabase GoTrue Auth.
    Tries 'signup' type first, then 'email' type if needed.
    """
    if not is_supabase_auth_enabled():
        return {"success": False, "error": "Supabase Auth is not enabled in environment."}

    cfg = _get_supabase_config()
    url = f"{cfg['url']}/auth/v1/verify"
    clean_email = email.strip().lower()
    clean_token = token.strip()

    candidate_types = [otp_type]
    if otp_type == "signup":
        candidate_types.append("email")

    for candidate_type in candidate_types:
        payload = {
            "type": candidate_type,
            "email": clean_email,
            "token": clean_token,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload, headers=_anon_headers())
                data = resp.json() if resp.content else {}

                if resp.status_code in (200, 201):
                    user_data = data.get("user", {})
                    return {
                        "success": True,
                        "access_token": data.get("access_token"),
                        "refresh_token": data.get("refresh_token"),
                        "supabase_uid": user_data.get("id"),
                        "user": user_data,
                    }
                elif resp.status_code == 429:
                    return {
                        "success": False,
                        "error": "Too many verification attempts. Please wait a minute before trying again."
                    }
        except Exception as exc:
            logger.error("Supabase verify-otp attempt error (%s): %s", candidate_type, exc)

    return {
        "success": False,
        "error": "The verification code is invalid, incorrect, or has expired. Please check your email or request a new code."
    }

def supabase_resend_otp(email: str, otp_type: str = "signup") -> Dict[str, Any]:
    """
    Resends a 6-digit email OTP via Supabase Auth custom SMTP.
    """
    if not is_supabase_auth_enabled():
        return {"success": False, "error": "Supabase Auth is not enabled in environment."}

    cfg = _get_supabase_config()
    clean_email = email.strip().lower()

    if otp_type == "recovery":
        return supabase_recover_password(clean_email)

    url = f"{cfg['url']}/auth/v1/resend"
    payload = {
        "type": otp_type,
        "email": clean_email,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=_anon_headers())
            data = resp.json() if resp.content else {}

            if resp.status_code in (200, 201):
                return {"success": True, "message": "Verification code resent successfully."}
            elif resp.status_code == 429:
                return {
                    "success": False,
                    "rate_limited": True,
                    "error": "For security purposes, you can only request this once every 60 seconds. Please wait before requesting another code."
                }
            else:
                err_msg = data.get("msg") or data.get("message") or "Failed to resend verification code."
                return {"success": False, "error": err_msg}
    except Exception as exc:
        logger.error("Supabase resend-otp request error: %s", exc)
        return {"success": False, "error": f"Supabase Auth connection error: {str(exc)}"}

def supabase_recover_password(email: str, redirect_to: Optional[str] = None) -> Dict[str, Any]:
    """
    Triggers password recovery in Supabase GoTrue Auth.
    GoTrue dispatches the 6-digit recovery OTP and/or recovery link via the configured custom SMTP.
    """
    if not is_supabase_auth_enabled():
        return {"success": False, "error": "Supabase Auth is not enabled in environment."}

    cfg = _get_supabase_config()
    clean_email = email.strip().lower()

    # Ensure user exists in Supabase auth.users before triggering recovery,
    # otherwise GoTrue silently ignores the recovery request.
    existing = supabase_admin_get_user_by_email(clean_email)
    if not existing:
        uid = supabase_admin_sync_user(email=clean_email, is_verified=True)
        if not uid:
            logger.warning("Could not sync user %s to Supabase Auth for recovery.", clean_email)

    url = f"{cfg['url']}/auth/v1/recover"
    params = {}
    if redirect_to:
        params["redirect_to"] = redirect_to

    payload = {"email": clean_email}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=_anon_headers(), params=params)
            data = resp.json() if resp.content else {}

            if resp.status_code in (200, 201):
                return {"success": True, "message": "Password recovery email dispatched successfully."}
            elif resp.status_code == 429:
                return {
                    "success": False,
                    "rate_limited": True,
                    "error": "Password recovery rate limit reached. Please wait a few moments before trying again."
                }
            else:
                err_msg = data.get("msg") or data.get("message") or "Failed to dispatch password recovery email."
                return {"success": False, "error": err_msg, "status_code": resp.status_code}
    except Exception as exc:
        logger.error("Supabase recover password request error: %s", exc)
        return {"success": False, "error": f"Supabase Auth connection error: {str(exc)}"}

def supabase_login(email: str, password: str) -> Dict[str, Any]:
    """
    Authenticates email and password against Supabase GoTrue Auth.
    """
    if not is_supabase_auth_enabled():
        return {"success": False, "error": "Supabase Auth is not enabled in environment."}

    cfg = _get_supabase_config()
    url = f"{cfg['url']}/auth/v1/token?grant_type=password"
    payload = {
        "email": email.strip().lower(),
        "password": password,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=_anon_headers())
            data = resp.json() if resp.content else {}

            if resp.status_code in (200, 201):
                return {
                    "success": True,
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "user": data.get("user", {}),
                    "supabase_uid": data.get("user", {}).get("id")
                }
            else:
                err_msg = data.get("msg") or data.get("message") or data.get("error_description") or "Invalid credentials."
                return {"success": False, "error": err_msg, "status_code": resp.status_code}
    except Exception as exc:
        logger.error("Supabase login request error: %s", exc)
        return {"success": False, "error": f"Supabase Auth connection error: {str(exc)}"}

def supabase_admin_get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Queries Supabase Auth admin API to locate a user by email.
    Uses service-role key strictly on the backend.
    """
    if not is_supabase_auth_enabled():
        return None

    cfg = _get_supabase_config()
    clean_email = email.strip().lower()
    url = f"{cfg['url']}/auth/v1/admin/users"

    try:
        with httpx.Client(timeout=15.0) as client:
            # Query users
            resp = client.get(url, headers=_admin_headers(), params={"per_page": 50})
            if resp.status_code == 200:
                data = resp.json()
                users = data.get("users", [])
                for u in users:
                    if (u.get("email") or "").strip().lower() == clean_email:
                        return u
    except Exception as exc:
        logger.error("Supabase admin_get_user_by_email error: %s", exc)
    return None

def supabase_admin_sync_user(
    email: str,
    password: Optional[str] = None,
    username: Optional[str] = None,
    display_name: Optional[str] = None,
    is_verified: bool = True,
    role: str = "student"
) -> Optional[str]:
    """
    Syncs an existing CodeMind user into Supabase Auth via Admin API.
    - If user does not exist in auth.users, creates them as confirmed.
    - If user exists, updates their password or metadata.
    - Returns the supabase_uid (UUID string).
    """
    if not is_supabase_auth_enabled():
        return None

    cfg = _get_supabase_config()
    clean_email = email.strip().lower()
    existing = supabase_admin_get_user_by_email(clean_email)

    try:
        with httpx.Client(timeout=15.0) as client:
            if existing:
                uid = existing.get("id")
                update_payload: Dict[str, Any] = {
                    "email_confirm": is_verified,
                    "user_metadata": {
                        "username": username or existing.get("user_metadata", {}).get("username"),
                        "display_name": display_name or existing.get("user_metadata", {}).get("display_name"),
                        "role": role,
                    }
                }
                if password:
                    update_payload["password"] = password
                client.put(f"{cfg['url']}/auth/v1/admin/users/{uid}", json=update_payload, headers=_admin_headers())
                return uid
            else:
                create_payload: Dict[str, Any] = {
                    "email": clean_email,
                    "email_confirm": is_verified,
                    "user_metadata": {
                        "username": username or clean_email.split("@")[0],
                        "display_name": display_name or username or "Learner",
                        "role": role,
                    }
                }
                if password:
                    create_payload["password"] = password
                resp = client.post(f"{cfg['url']}/auth/v1/admin/users", json=create_payload, headers=_admin_headers())
                if resp.status_code in (200, 201):
                    return resp.json().get("id")
    except Exception as exc:
        logger.error("Supabase admin sync user error (%s): %s", clean_email, exc)

    return None

def supabase_decode_jwt_sub(token: str) -> Optional[Dict[str, Any]]:
    """
    Safely inspects the payload of a JWT without verifying secret
    (for initial subject resolution before DB validation).
    """
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        # Pad base64 string
        rem = len(payload_b64) % 4
        if rem > 0:
            payload_b64 += "=" * (4 - rem)
        decoded = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
        if isinstance(data, dict) and ("sub" in data or "email" in data):
            return data
    except Exception:
        pass
    return None
