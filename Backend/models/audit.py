import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text
from db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"aud-{uuid.uuid4().hex[:10]}")
    actor_id = Column(String(100), nullable=False, index=True)
    actor_email = Column(String(255), nullable=True)
    actor_role = Column(String(50), nullable=False, default="student", index=True)
    
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(String(100), nullable=True, index=True)
    ip_address = Column(String(100), nullable=True)
    result = Column(String(50), nullable=False, default="SUCCESS", index=True)  # SUCCESS, DENIED, FAILED
    details = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_email": self.actor_email or "",
            "actor_role": self.actor_role,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id or "",
            "ip_address": self.ip_address or "",
            "result": self.result,
            "details": self.details or "",
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<AuditLog(id='{self.id}', action='{self.action}', actor='{self.actor_id}', result='{self.result}')>"
