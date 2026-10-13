"""
New models for CodeMind Admin Portal:
- ProblemReport: Student-submitted problem reports
- ProblemVersion: Version history for problem edits
- Announcement: Platform announcements
- FeatureFlag: Feature toggles
- EmailEvent: Email monitoring (status tracking, no OTP content)
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from db.base import Base


class ProblemReport(Base):
    """Student-reported issues with problems."""
    __tablename__ = "problem_reports"

    id = Column(String(100), primary_key=True, index=True,
                default=lambda: f"rpt-{uuid.uuid4().hex[:8]}")
    problem_id = Column(String(100), ForeignKey("problems.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    reporter_id = Column(String(100), nullable=False, index=True)  # user_accounts.id
    reporter_email = Column(String(255), nullable=True)
    problem_version = Column(String(50), nullable=True)  # version at time of report

    # Report content
    category = Column(String(100), nullable=False, index=True)
    # Categories: incorrect_statement, incorrect_input_format, incorrect_output_format,
    #   incorrect_example, incorrect_constraints, incorrect_expected_answer,
    #   broken_test_case, typo_grammar, duplicate_problem, wrong_topic_difficulty,
    #   starter_code_issue, other
    description = Column(Text, nullable=True)

    # Admin review
    status = Column(String(50), nullable=False, default="pending", index=True)
    # Statuses: pending, under_review, confirmed, fixed, rejected, duplicate
    reviewed_by = Column(String(100), nullable=True)   # admin user id
    reviewed_at = Column(DateTime, nullable=True)
    admin_note = Column(Text, nullable=True)
    duplicate_of = Column(String(100), nullable=True)  # report id if marked duplicate

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        nullable=False, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    problem = relationship("Problem", lazy="joined")

    def to_dict(self):
        prob = self.problem
        return {
            "id": self.id,
            "problem_id": self.problem_id,
            "problem_title": prob.title if prob else self.problem_id,
            "problem_version": self.problem_version,
            "reporter_id": self.reporter_id,
            "reporter_email": self.reporter_email or "",
            "category": self.category,
            "description": self.description or "",
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "admin_note": self.admin_note or "",
            "duplicate_of": self.duplicate_of,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<ProblemReport(id='{self.id}', problem='{self.problem_id}', status='{self.status}')>"


class ProblemVersion(Base):
    """Version history snapshot of a Problem's editable fields."""
    __tablename__ = "problem_versions"

    id = Column(String(100), primary_key=True, index=True,
                default=lambda: f"pv-{uuid.uuid4().hex[:8]}")
    problem_id = Column(String(100), ForeignKey("problems.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1)
    changed_by = Column(String(100), nullable=False)   # admin user id
    changed_by_email = Column(String(255), nullable=True)
    change_summary = Column(Text, nullable=True)

    # Full snapshot of all editable fields at this version
    snapshot = Column(JSON, nullable=False, default=dict)
    # {title, description, difficulty, input_format, output_format, constraints,
    #  examples, starter_code, test_cases, supported_languages, is_active}

    is_published = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        nullable=False, index=True)

    # Relationship
    problem = relationship("Problem", lazy="joined")

    def to_dict(self):
        prob = self.problem
        return {
            "id": self.id,
            "problem_id": self.problem_id,
            "problem_title": prob.title if prob else self.problem_id,
            "version_number": self.version_number,
            "changed_by": self.changed_by,
            "changed_by_email": self.changed_by_email or "",
            "change_summary": self.change_summary or "",
            "snapshot": self.snapshot,
            "is_published": self.is_published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return (f"<ProblemVersion(problem='{self.problem_id}', "
                f"v={self.version_number}, by='{self.changed_by}')>")


class Announcement(Base):
    """Platform announcements targeted to users/institutes/groups."""
    __tablename__ = "announcements"

    id = Column(String(100), primary_key=True, index=True,
                default=lambda: f"ann-{uuid.uuid4().hex[:8]}")
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    announcement_type = Column(String(50), nullable=False, default="general", index=True)
    # Types: general, test, maintenance, feature, urgent

    # Targeting
    target = Column(String(50), nullable=False, default="everyone", index=True)
    # Targets: everyone, institute, group, selected_users, test_participants
    target_ids = Column(JSON, nullable=False, default=list)
    # For institute: [institute_name], for test: [test_id], for users: [user_id, ...]

    # Lifecycle
    status = Column(String(50), nullable=False, default="draft", index=True)
    # Statuses: draft, published, scheduled, expired, archived
    scheduled_at = Column(DateTime, nullable=True)    # when to auto-publish
    expires_at = Column(DateTime, nullable=True)      # when to auto-expire

    created_by = Column(String(100), nullable=False)
    created_by_email = Column(String(255), nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        nullable=False, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "announcement_type": self.announcement_type,
            "target": self.target,
            "target_ids": self.target_ids or [],
            "status": self.status,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_by": self.created_by,
            "created_by_email": self.created_by_email or "",
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Announcement(id='{self.id}', title='{self.title}', status='{self.status}')>"


class FeatureFlag(Base):
    """Server-side feature flag toggle table."""
    __tablename__ = "feature_flags"

    id = Column(String(100), primary_key=True, index=True,
                default=lambda: f"ff-{uuid.uuid4().hex[:8]}")
    key = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    value = Column(JSON, nullable=True)   # Optional typed value (e.g., model name)
    changed_by = Column(String(100), nullable=True)
    changed_by_email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "description": self.description or "",
            "enabled": self.enabled,
            "value": self.value,
            "changed_by": self.changed_by,
            "changed_by_email": self.changed_by_email or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<FeatureFlag(key='{self.key}', enabled={self.enabled})>"


class EmailEvent(Base):
    """
    Email delivery tracking — status monitoring only.
    NEVER stores OTP values or security-sensitive content.
    """
    __tablename__ = "email_events"

    id = Column(String(100), primary_key=True, index=True,
                default=lambda: f"email-{uuid.uuid4().hex[:8]}")
    recipient_id = Column(String(100), nullable=True, index=True)   # user_accounts.id
    recipient_email = Column(String(255), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    # Types: email_verification, welcome, password_recovery, mobile_otp,
    #        announcement, notification
    subject = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="sent", index=True)
    # Statuses: sent, failed, skipped (SMTP not configured)
    error_message = Column(Text, nullable=True)   # Error detail if failed; no secrets
    smtp_configured = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "recipient_id": self.recipient_id,
            "recipient_email": self.recipient_email,
            "event_type": self.event_type,
            "subject": self.subject or "",
            "status": self.status,
            "error_message": self.error_message or "",
            "smtp_configured": self.smtp_configured,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return (f"<EmailEvent(type='{self.event_type}', to='{self.recipient_email}', "
                f"status='{self.status}')>")
