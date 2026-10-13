import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from db.base import Base


class UserApiKey(Base):
    """
    Secure per-user multi-API key model for Maya AI providers (Groq, NVIDIA, Gemini).
    Keys are strictly encrypted at rest and never shared across users.
    """
    __tablename__ = "user_api_keys"

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"key-{uuid.uuid4().hex[:12]}")
    user_id = Column(String(100), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)  # Normalized: "groq", "nvidia", "gemini"
    encrypted_api_key = Column(String(1024), nullable=False)
    key_preview = Column(String(50), nullable=False)  # Safe masked representation, e.g. "••••••••7X9A"
    key_hash = Column(String(64), nullable=False, index=True)  # SHA-256 for fast duplicate detection per user
    status = Column(String(50), nullable=False, default="AVAILABLE", index=True)  # AVAILABLE, IN_USE, RATE_LIMITED, COOLDOWN, INVALID, DISABLED
    last_used_at = Column(DateTime, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_user_api_keys_user_provider", "user_id", "provider"),
        Index("ix_user_api_keys_user_provider_status", "user_id", "provider", "status"),
        Index("ix_user_api_keys_user_hash", "user_id", "provider", "key_hash"),
    )

    def to_dict(self):
        """Safe dictionary representation — never returns encrypted_api_key or plaintext."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "key_preview": self.key_preview,
            "status": self.status,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<UserApiKey(id='{self.id}', user_id='{self.user_id}', provider='{self.provider}', preview='{self.key_preview}', status='{self.status}')>"
