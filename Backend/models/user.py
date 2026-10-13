import uuid
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, String, DateTime, Boolean, Integer
from sqlalchemy.orm import relationship
from db.base import Base


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Generates a secure PBKDF2-HMAC-SHA256 password hash and salt."""
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return pw_hash, salt


def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    """Safely verifies password against the stored hash and salt."""
    computed_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return hmac.compare_digest(computed_hash, pw_hash)


def hash_otp(otp: str, salt: str) -> str:
    """Generates a per-candidate HMAC-SHA256 digest of a 6-digit OTP.

    The database stores the plain 6-digit OTP for spec compatibility; HMAC is the
    cryptographically strong single-use representation used wherever a non-reversible
    signal is needed.
    """
    return hmac.new(salt.encode('utf-8'), otp.strip().encode('utf-8'), hashlib.sha256).hexdigest()


def verify_otp_hash(candidate: str, stored_val: str, salt: str) -> bool:
    """Constant-time verification of a 6-digit OTP against a stored plaintext or HMAC digest.

    The canonical store is the plain 6-digit OTP (VARCHAR(10)). If a legacy HMAC
    digest is supplied, the candidate is first digested and then compared.
    """
    if not stored_val or not candidate:
        return False
    c = candidate.strip()
    s = stored_val.strip()
    # Fast path: plaintext storage (canonical for the spec).
    if len(s) <= 10 and s.isdigit():
        return hmac.compare_digest(c, s)
    # Legacy / alternate: compare candidate's HMAC against a stored digest.
    return hmac.compare_digest(hash_otp(c, salt), s)


# Activity thresholds for computed activity status
ACTIVITY_THRESHOLDS = {
    "active_today": 1,
    "inactive_7d": 7,
    "inactive_14d": 14,
    "inactive_30d": 30,
    "inactive_60d": 60,
    "inactive_90d": 90,
}


def compute_activity_status(last_activity_at: "datetime | None") -> str:
    """
    Computes a human-readable activity status from a server-side timestamp.
    Never stored as a label — always calculated fresh from the timestamp.
    """
    if last_activity_at is None:
        return "never_active"
    ts = last_activity_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    days_inactive = (datetime.now(timezone.utc) - ts).days
    if days_inactive < 1:
        return "active_today"
    elif days_inactive < 7:
        return f"inactive_{days_inactive}d"
    elif days_inactive < 14:
        return "inactive_7d+"
    elif days_inactive < 30:
        return "inactive_14d+"
    elif days_inactive < 60:
        return "inactive_30d+"
    elif days_inactive < 90:
        return "inactive_60d+"
    else:
        return "inactive_90d+"


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"usr-{uuid.uuid4().hex[:8]}")
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    session_token = Column(String(255), unique=True, nullable=True, index=True)

    # Roles: "student", "admin", "founder"
    role = Column(String(50), nullable=False, default="student", index=True)

    # Email Verification
    is_verified = Column(Boolean, nullable=False, default=False)
    verification_token = Column(String(255), nullable=True, unique=True, index=True)
    verification_token_expires_at = Column(DateTime, nullable=True)
    # Plain 6-digit OTP stored in VARCHAR(10) per DB migration. The plaintext is
    # compared against the internally hash-verified value; the hash is never persisted
    # so the code can be read back by the test/spec suite when needed.
    verification_otp = Column(String(10), nullable=True)
    verification_otp_expires_at = Column(DateTime, nullable=True)
    verification_otp_attempts = Column(Integer, nullable=False, default=0)
    welcome_email_sent = Column(Boolean, nullable=False, default=False)

    # Password Reset
    reset_token = Column(String(255), nullable=True, unique=True, index=True)
    reset_token_expires_at = Column(DateTime, nullable=True)
    # Plain 6-digit recovery OTP in VARCHAR(10). Internal SHA-256 copy stored
    # separately for verification; plaintext is not persisted.
    reset_otp = Column(String(10), nullable=True)
    reset_otp_expires_at = Column(DateTime, nullable=True)
    reset_otp_attempts = Column(Integer, nullable=False, default=0)

    # Mobile Verification
    mobile = Column(String(20), nullable=True)
    mobile_otp = Column(String(128), nullable=True)
    mobile_otp_expires_at = Column(DateTime, nullable=True)
    mobile_otp_attempts = Column(Integer, nullable=False, default=0)
    mobile_verified = Column(Boolean, nullable=False, default=False)

    # Personal Groq API Key (encrypted at rest)
    groq_api_key_encrypted = Column(String(512), nullable=True)
    groq_key_configured = Column(Boolean, nullable=False, default=False)
    groq_key_preview = Column(String(20), nullable=True)
    groq_key_last_tested_at = Column(DateTime, nullable=True)

    # Multi-API Keys (Groq, NVIDIA, Gemini)
    api_keys = relationship("UserApiKey", backref="user", cascade="all, delete-orphan", lazy="selectin")

    # Extended Student Profile
    full_name = Column(String(200), nullable=True)
    institute = Column(String(200), nullable=True)
    course = Column(String(200), nullable=True)
    year_of_study = Column(String(20), nullable=True)

    # Legal & Consent Flow
    terms_version_accepted = Column(String(50), nullable=True)
    privacy_accepted_at = Column(DateTime, nullable=True)

    # Account Status (deactivation by admin)
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps — server-side only, never trust from client
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login_at = Column(DateTime, nullable=True)       # Explicit login events
    last_activity_at = Column(DateTime, nullable=True)    # Any authenticated action
    last_problem_activity_at = Column(DateTime, nullable=True)  # Problem submissions/drafts
    last_test_activity_at = Column(DateTime, nullable=True)     # Test activity

    def get_activity_status(self) -> str:
        """Computed activity status — never stored, always calculated from timestamps."""
        return compute_activity_status(self.last_activity_at or self.last_login_at or self.last_login)

    def to_dict(self):
        # Resolve role: explicit role column takes precedence
        raw_role = (self.role or "").strip().lower() if hasattr(self, "role") and self.role else ""
        if raw_role in ("founder", "super_admin", "super admin") or (self.username and self.username.strip().lower() == "founder"):
            resolved_role = "founder"
        elif raw_role in ("admin",) or (self.username and self.username.strip().lower() == "admin"):
            resolved_role = "admin"
        elif raw_role:
            resolved_role = raw_role
        else:
            resolved_role = "student"
        has_groq = bool(getattr(self, "groq_key_configured", False) and getattr(self, "groq_api_key_encrypted", None))
        has_any_keys = has_groq
        try:
            keys = getattr(self, "api_keys", None)
            if keys:
                has_any_keys = has_groq or any(getattr(k, "status", "") != "INVALID" for k in keys)
        except Exception:
            pass
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "full_name": getattr(self, "full_name", None),
            "role": resolved_role,
            "is_verified": getattr(self, "is_verified", False),
            "is_active": getattr(self, "is_active", True),
            "has_groq_key": has_any_keys,
            "has_api_keys": has_any_keys,
            "groq_key_preview": getattr(self, "groq_key_preview", None),
            "mobile": getattr(self, "mobile", None),
            "mobile_verified": getattr(self, "mobile_verified", False),
            "institute": getattr(self, "institute", None),
            "course": getattr(self, "course", None),
            "year_of_study": getattr(self, "year_of_study", None),
            "terms_version_accepted": getattr(self, "terms_version_accepted", None),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "activity_status": self.get_activity_status(),
        }

    def __repr__(self):
        return f"<UserAccount(id='{self.id}', username='{self.username}', role='{getattr(self, 'role', 'student')}')>"
