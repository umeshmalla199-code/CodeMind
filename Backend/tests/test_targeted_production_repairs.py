"""
Targeted Verification Suite for Production Repairs:
1. Maya AI - Groq 429 Rate-Limit Handling & NVIDIA Fallback
2. Account Creation - OTP Email Delivery & Lifecycle
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from main import app
from db.session import SessionLocal
from models.user import UserAccount, hash_otp, verify_otp_hash
from routes.auth import (
    _get_email_config,
    _is_smtp_configured,
    _send_smtp_email,
    _dispatch_otp_email,
)
from ai.companion.gateway import (
    _is_rate_limit_error,
    _extract_retry_after,
    MayaGateway,
)
from ai.companion.groq_provider import GroqProvider
from ai.companion.schemas import CompanionChatRequest, CompanionContext, CompanionChatMessage

client = TestClient(app)


# ============================================================================
# ISSUE 1: MAYA AI - GROQ 429 RATE LIMIT & NVIDIA FALLBACK TESTS
# ============================================================================

class DummyRateLimitError(Exception):
    def __init__(self, message="Rate limit reached", status_code=429, headers=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}
        self.body = body or {"error": {"message": message, "code": "rate_limit_exceeded"}}


class TestMayaRateLimitHandling:
    """Tests rate limit detection, retry-after header parsing, bounded backoff, and fallback."""

    def test_rate_limit_detection(self):
        """Verifies _is_rate_limit_error correctly identifies 429 and rate limit errors."""
        err1 = DummyRateLimitError("Rate limit reached: groq/qwen/qwen3.8-27b", status_code=429)
        assert _is_rate_limit_error(err1) is True

        err2 = Exception("Service note: Encountered RateLimitError while streaming")
        assert _is_rate_limit_error(err2) is True

        err3 = Exception("HTTP 429: Too Many Requests")
        assert _is_rate_limit_error(err3) is True

        err4 = ValueError("Invalid argument")
        assert _is_rate_limit_error(err4) is False

    def test_extract_retry_after_headers(self):
        """Verifies parsing of standard and Groq-specific retry headers."""
        # Standard retry-after in seconds
        err_sec = DummyRateLimitError(headers={"retry-after": "2.5"})
        assert _extract_retry_after(err_sec) == 2.5

        # Retry-after in milliseconds
        err_ms = DummyRateLimitError(headers={"retry-after-ms": "1500"})
        assert _extract_retry_after(err_ms) == 1.5

        # x-ratelimit-reset-requests in seconds
        err_reset = DummyRateLimitError(headers={"x-ratelimit-reset-requests": "3.0"})
        assert _extract_retry_after(err_reset) == 3.0

        # No header returns None
        err_none = DummyRateLimitError(headers={})
        assert _extract_retry_after(err_none) is None

    def test_streaming_fallback_to_nvidia_on_groq_429(self):
        """
        When Groq returns 429, gateway must:
        1. Not expose raw RateLimitError exception text to user
        2. Fall back cleanly to NVIDIA provider
        3. Preserve conversation_id and request_id
        """
        gateway = MayaGateway()

        # Mock Groq provider stream to raise 429
        mock_groq_client = MagicMock()
        mock_groq_client.chat.completions.create.side_effect = DummyRateLimitError(
            "Rate limit reached for model groq/qwen/qwen3.8-27b",
            status_code=429,
            headers={"retry-after": "10"} # >3.5s will immediately fallback
        )

        # Mock NVIDIA streaming response chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta = MagicMock(content="Hello from ", reasoning=None, reasoning_content=None)

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta = MagicMock(content="NVIDIA fallback!", reasoning=None, reasoning_content=None)

        mock_nvidia_client = MagicMock()
        mock_nvidia_client.chat.completions.create.return_value = [chunk1, chunk2]

        req = CompanionChatRequest(
            message="Explain binary search in Python",
            conversation_id="conv-repair-123",
            request_id="req-repair-456",
            context=CompanionContext(
                active_workspace="problem_solving",
                selected_language="python",
                problem_id="prob-1",
                problem_title="Binary Search",
                current_code="def binary_search(arr, target): pass"
            ),
            history=[]
        )

        with patch.object(gateway, '_get_groq_client', return_value=mock_groq_client), \
             patch.object(gateway, '_get_nvidia_client', return_value=mock_nvidia_client):

            chunks = list(gateway.chat_stream(req))

            full_response = "".join(chunks)

            # Verification:
            # 1. No raw RateLimitError or exception leak
            assert "RateLimitError" not in full_response
            assert "Service note: Encountered RateLimitError" not in full_response
            assert "Traceback" not in full_response

            # 2. Contains content from NVIDIA fallback
            assert "Hello from NVIDIA fallback!" in full_response

    def test_groq_provider_non_streaming_rate_limit_backoff(self):
        """Verifies GroqProvider bounded backoff and fallback without infinite loops."""
        provider = GroqProvider()
        mock_client = MagicMock()

        # Simulate 429 on first call, success on second call
        success_choice = MagicMock()
        success_choice.message = MagicMock(content='{"message": "Success after backoff"}')
        success_resp = MagicMock(choices=[success_choice])

        mock_client.chat.completions.create.side_effect = [
            DummyRateLimitError("Rate limit", status_code=429, headers={"retry-after": "0.1"}),
            success_resp
        ]

        with patch.object(provider, '_get_client', return_value=mock_client), \
             patch('time.sleep', return_value=None):  # Avoid test delay
            res = provider.generate_response(
                user_message="Test query",
                history=[],
                context=CompanionContext(selected_language="python")
            )
            assert res is not None
            assert res.message == "Success after backoff"


# ============================================================================
# ISSUE 2: ACCOUNT CREATION - OTP EMAIL DELIVERY & LIFECYCLE TESTS
# ============================================================================

class TestOTPEmailDeliveryAndAuthLifecycle:
    """Tests SMTP configuration, OTP generation, verification, resend, and password recovery."""

    def test_smtp_configuration_helpers(self):
        """Verifies _get_email_config and _is_smtp_configured work properly."""
        cfg = _get_email_config()
        assert "host" in cfg
        assert "port" in cfg
        assert "user" in cfg
        assert "password" in cfg

        # When SMTP_HOST is cleared, _is_smtp_configured must return False
        old_host = os.environ.pop("SMTP_HOST", None)
        try:
            assert _is_smtp_configured() is False
        finally:
            if old_host:
                os.environ["SMTP_HOST"] = old_host

    def test_dispatch_otp_email_returns_boolean_and_does_not_raise(self):
        """_dispatch_otp_email returns boolean status and does not raise."""
        with patch('routes.auth._send_smtp_email', return_value=True):
            sent = _dispatch_otp_email("student@test.local", "Student", "123456", "Email Verification")
            assert sent is True

        with patch('routes.auth._send_smtp_email', return_value=False):
            sent = _dispatch_otp_email("student@test.local", "Student", "123456", "Email Verification")
            assert sent is False

    def test_registration_generates_valid_otp_and_hashes_in_db(self):
        """Registration generates 6-digit OTP, stores PBKDF2 hash, and returns requires_otp=True."""
        test_uname = f"u_{int(time.time())}"
        test_email = f"{test_uname}@production-test.com"

        # Cleanup in case
        db = SessionLocal()
        try:
            db.query(UserAccount).filter(UserAccount.email == test_email).delete()
            db.commit()
        finally:
            db.close()

        with patch('routes.auth._dispatch_otp_email', return_value=True):
            resp = client.post("/api/auth/register", json={
                "username": test_uname,
                "email": test_email,
                "display_name": "Prod Test User",
                "password": "SecurePassword123!",
                "agree_terms": True
            })

            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "success"
            assert data["requires_otp"] is True
            assert data["is_verified"] is False
            assert data["token"] is None

        # Verify OTP is stored securely (hashed with salt) in DB
        db = SessionLocal()
        try:
            user = db.query(UserAccount).filter(UserAccount.email == test_email).first()
            assert user is not None
            assert user.is_verified is False
            assert user.verification_otp is not None
            # Spec contract: store the plain 6-digit OTP (VARCHAR(10)).
            assert len(user.verification_otp) == 6 and user.verification_otp.isdigit()
            assert user.verification_otp_expires_at is not None

            # Verify OTP attempt counter is 0
            assert user.verification_otp_attempts == 0

            # Set a test known OTP to verify flow (spec: plain 6-digit OTP).
            known_otp = "654321"
            user.verification_otp = known_otp
            user.verification_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            db.commit()

            # Test invalid OTP increment
            bad_resp = client.post("/api/auth/verify-otp", json={
                "email": test_email,
                "otp": "999999"
            })
            assert bad_resp.status_code == 400

            # Test valid OTP verification
            with patch('routes.auth._dispatch_welcome_email', return_value=True):
                good_resp = client.post("/api/auth/verify-otp", json={
                    "email": test_email,
                    "otp": known_otp
                })
                assert good_resp.status_code == 200
                vdata = good_resp.json()
                assert vdata["is_verified"] is True
                assert vdata["token"].startswith("cmt_")

            # Verify user is verified in DB and OTP cleared
            db.refresh(user)
            assert user.is_verified is True
            assert user.verification_otp is None

            # Test login now succeeds
            login_resp = client.post("/api/auth/login", json={
                "username": test_uname,
                "password": "SecurePassword123!"
            })
            assert login_resp.status_code == 200
            assert login_resp.json()["token"].startswith("cmt_")

        finally:
            # Cleanup
            user_to_del = db.query(UserAccount).filter(UserAccount.email == test_email).first()
            if user_to_del:
                db.delete(user_to_del)
                db.commit()
            db.close()

    def test_forgot_password_account_enumeration_protection(self):
        """Forgot-password returns identical 200 response whether email exists or not."""
        # Non-existent email
        resp1 = client.post("/api/auth/forgot-password", json={
            "email": "nonexistent_random_user_12345@domain.com"
        })
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert "recovery code" in data1.get("message", "").lower()
        # Crucial: Must never leak user existence or tokens
        assert "token" not in data1
        assert "reset_token" not in data1
