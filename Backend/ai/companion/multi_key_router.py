"""
Secure Multi-API-Key Maya Router & Load Balancer for CodeMind.

Guarantees:
- Strict user isolation: every key belongs to exactly one authenticated user ID.
- User keys are decrypted ONLY at the point of request dispatch, never logged in plaintext.
- True concurrency: multiple simultaneous requests use distinct eligible keys.
- Load balancing: prefers available keys with zero/lowest in-flight requests.
- Automatic rate-limit cooldown: HTTP 429 marks the key in cooldown and routes to next key/provider.
- Provider fallback: Groq -> NVIDIA -> Gemini -> Server fallback.
- Never claims "Unlimited": capacity increases with keys, within provider quotas.
"""

from __future__ import annotations

import os
import sys
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session

from models.api_key import UserApiKey
from models.user import UserAccount
from security import decrypt_secret, mask_api_key, hash_api_key

logger = logging.getLogger("codemind.companion.multi_key_router")

# Provider priority order for fallback
DEFAULT_PROVIDER_CHAIN = ["groq", "nvidia", "gemini"]


@dataclass
class KeyLease:
    key_id: str
    user_id: str
    provider: str
    decrypted_key: str
    preview: str
    is_server_fallback: bool = False
    _released: bool = False

    def release(self) -> None:
        """Releases the in-flight reservation for this key lease."""
        if not self._released:
            multi_key_router.release_in_flight(self.key_id)
            self._released = True

    def __enter__(self) -> KeyLease:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


class MultiKeyRouter:
    """
    Centralized, thread-safe Multi-Key Router and Load Balancer.
    Tracks in-flight requests and cooldowns per key in memory with DB persistence.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # key_id -> active concurrent requests count
        self._in_flight: Dict[str, int] = {}
        # key_id -> datetime (UTC) when cooldown ends
        self._cooldowns: Dict[str, datetime] = {}
        # key_id -> status override ("INVALID", "DISABLED")
        self._status_overrides: Dict[str, str] = {}

    def release_in_flight(self, key_id: str) -> None:
        """Decrements the in-flight request counter for a key."""
        with self._lock:
            if key_id in self._in_flight:
                self._in_flight[key_id] = max(0, self._in_flight[key_id] - 1)

    def record_key_success(self, key_id: str, db: Optional[Session] = None) -> None:
        """Records a successful request completion on a key."""
        now = datetime.now(timezone.utc)
        self.release_in_flight(key_id)
        if key_id.startswith("server-env-"):
            return

        if db is not None:
            try:
                db_key = db.query(UserApiKey).filter(UserApiKey.id == key_id).first()
                if db_key:
                    db_key.last_used_at = now
                    if db_key.status in ("RATE_LIMITED", "COOLDOWN"):
                        db_key.status = "AVAILABLE"
                    db.commit()
            except Exception as e:
                logger.debug("Failed updating key %s success in DB: %s", key_id, e)

    def record_key_rate_limit(
        self,
        key_id: str,
        retry_after_seconds: Optional[float] = None,
        db: Optional[Session] = None,
        provider: str = "unknown",
        user_id: str = "unknown"
    ) -> float:
        """
        Marks a key as RATE_LIMITED / in COOLDOWN.
        Calculates appropriate cooldown duration and returns the cooldown seconds.
        """
        self.release_in_flight(key_id)
        now = datetime.now(timezone.utc)

        # Default cooldown: 30 seconds if provider header is missing or unparseable
        cooldown_secs = max(5.0, min(float(retry_after_seconds or 30.0), 300.0))
        cooldown_until = now + timedelta(seconds=cooldown_secs)

        with self._lock:
            self._cooldowns[key_id] = cooldown_until

        logger.warning(
            "API key rate limited: id=%s provider=%s user_id=%s cooldown=%.1fs",
            key_id, provider, user_id, cooldown_secs
        )

        if not key_id.startswith("server-env-") and db is not None:
            try:
                db_key = db.query(UserApiKey).filter(UserApiKey.id == key_id).first()
                if db_key:
                    db_key.status = "RATE_LIMITED"
                    db_key.last_error_at = now
                    db_key.cooldown_until = cooldown_until
                    db.commit()
            except Exception as e:
                logger.debug("Failed updating key %s rate limit in DB: %s", key_id, e)

        return cooldown_secs

    def record_key_invalid(
        self,
        key_id: str,
        db: Optional[Session] = None,
        provider: str = "unknown",
        user_id: str = "unknown",
        error_msg: str = "Authentication failed"
    ) -> None:
        """
        Marks an invalid/rejected key as INVALID so it is excluded from future selection.
        """
        self.release_in_flight(key_id)
        now = datetime.now(timezone.utc)

        with self._lock:
            self._status_overrides[key_id] = "INVALID"

        logger.error(
            "API key invalid/unauthorized: id=%s provider=%s user_id=%s reason=%s",
            key_id, provider, user_id, error_msg
        )

        if not key_id.startswith("server-env-") and db is not None:
            try:
                db_key = db.query(UserApiKey).filter(UserApiKey.id == key_id).first()
                if db_key:
                    db_key.status = "INVALID"
                    db_key.last_error_at = now
                    db.commit()
            except Exception as e:
                logger.debug("Failed updating key %s invalid status in DB: %s", key_id, e)

    def _sync_legacy_groq_key_if_needed(self, user_id: str, db: Session) -> None:
        """
        Backward compatibility: if user has a legacy groq_api_key_encrypted on UserAccount,
        ensure it is registered in user_api_keys so they don't lose their key.
        """
        try:
            user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
            if not user or not user.groq_api_key_encrypted:
                return

            decrypted = decrypt_secret(user.groq_api_key_encrypted)
            if not decrypted:
                return

            khash = hash_api_key(decrypted)
            existing = db.query(UserApiKey).filter(
                UserApiKey.user_id == user_id,
                UserApiKey.provider == "groq",
                UserApiKey.key_hash == khash
            ).first()

            if not existing:
                preview = user.groq_key_preview or mask_api_key(decrypted)
                legacy_key = UserApiKey(
                    user_id=user_id,
                    provider="groq",
                    encrypted_api_key=user.groq_api_key_encrypted,
                    key_preview=preview,
                    key_hash=khash,
                    status="AVAILABLE",
                    last_used_at=user.groq_key_last_tested_at,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(legacy_key)
                db.commit()
        except Exception as exc:
            logger.debug("Legacy Groq key sync check skipped: %s", exc)

    def get_user_keys(self, user_id: str, db: Session, provider: Optional[str] = None) -> List[UserApiKey]:
        """
        Retrieves all keys belonging strictly to the specified user_id.
        User A can never see or retrieve User B's keys.
        """
        self._sync_legacy_groq_key_if_needed(user_id, db)
        query = db.query(UserApiKey).filter(UserApiKey.user_id == user_id)
        if provider:
            query = query.filter(UserApiKey.provider == provider.lower().strip())
        return query.order_by(UserApiKey.created_at.asc()).all()

    def get_user_key_count(self, user_id: str, db: Session) -> Dict[str, int]:
        """Returns the number of active keys configured by this user per provider."""
        keys = self.get_user_keys(user_id, db)
        counts = {"groq": 0, "nvidia": 0, "gemini": 0, "total": 0}
        for k in keys:
            if k.status != "INVALID" and k.status != "DISABLED":
                p = k.provider.lower()
                counts[p] = counts.get(p, 0) + 1
                counts["total"] += 1
        return counts

    def select_key(
        self,
        user_id: Optional[str],
        db: Optional[Session],
        provider: str,
        exclude_key_ids: Optional[List[str]] = None
    ) -> Optional[KeyLease]:
        """
        Selects the best eligible available key for user_id and provider.
        Prioritizes:
        1. Keys with status AVAILABLE (not in cooldown, not INVALID/DISABLED).
        2. Lowest active in_flight count (distributes concurrent requests!).
        3. Oldest last_used_at (round-robin / least recently used).
        """
        now = datetime.now(timezone.utc)
        exclude_set = set(exclude_key_ids or [])
        prov_norm = provider.lower().strip()

        if user_id and db is not None:
            user_keys = self.get_user_keys(user_id, db, provider=prov_norm)

            candidates: List[Tuple[int, float, UserApiKey]] = []

            with self._lock:
                for k in user_keys:
                    if k.id in exclude_set:
                        continue

                    # Check in-memory status overrides
                    if self._status_overrides.get(k.id) in ("INVALID", "DISABLED"):
                        continue
                    if k.status in ("INVALID", "DISABLED"):
                        continue

                    # Check cooldown
                    cd_end = self._cooldowns.get(k.id) or (
                        k.cooldown_until.replace(tzinfo=timezone.utc)
                        if (k.cooldown_until and k.cooldown_until.tzinfo is None)
                        else k.cooldown_until
                    )
                    if cd_end and now < cd_end:
                        # Key is still in cooldown
                        continue
                    elif cd_end and now >= cd_end:
                        # Cooldown has expired, restore key
                        if k.id in self._cooldowns:
                            del self._cooldowns[k.id]
                        if k.status in ("RATE_LIMITED", "COOLDOWN"):
                            k.status = "AVAILABLE"

                    inflight = self._in_flight.get(k.id, 0)
                    last_used_ts = k.last_used_at.timestamp() if k.last_used_at else 0.0
                    candidates.append((inflight, last_used_ts, k))

                if candidates:
                    # Sort primarily by lowest in_flight count, then oldest last_used timestamp
                    candidates.sort(key=lambda item: (item[0], item[1]))
                    best_candidate = candidates[0][2]

                    decrypted = decrypt_secret(best_candidate.encrypted_api_key)
                    if decrypted:
                        self._in_flight[best_candidate.id] = self._in_flight.get(best_candidate.id, 0) + 1
                        logger.info(
                            "Selected user key id=%s provider=%s user_id=%s (in_flight=%d)",
                            best_candidate.id, prov_norm, user_id, self._in_flight[best_candidate.id]
                        )
                        return KeyLease(
                            key_id=best_candidate.id,
                            user_id=user_id,
                            provider=prov_norm,
                            decrypted_key=decrypted,
                            preview=best_candidate.key_preview,
                            is_server_fallback=False
                        )

        return None

    def get_server_fallback_key(self, provider: str) -> Optional[KeyLease]:
        """Provides server environment key fallback if configured and permitted."""
        prov_norm = provider.lower().strip()
        env_map = {
            "groq": "GROQ_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY"
        }
        env_var = env_map.get(prov_norm)
        if not env_var:
            return None

        val = os.environ.get(env_var, "").strip()
        if not val:
            return None

        fake_id = f"server-env-{prov_norm}"
        with self._lock:
            cd_end = self._cooldowns.get(fake_id)
            if cd_end and datetime.now(timezone.utc) < cd_end:
                return None
            self._in_flight[fake_id] = self._in_flight.get(fake_id, 0) + 1

        return KeyLease(
            key_id=fake_id,
            user_id="server",
            provider=prov_norm,
            decrypted_key=val,
            preview=mask_api_key(val),
            is_server_fallback=True
        )

    def resolve_key_for_request(
        self,
        user_id: Optional[str],
        db: Optional[Session],
        preferred_provider: Optional[str] = None,
        allow_server_fallback: bool = True
    ) -> Tuple[Optional[KeyLease], List[str]]:
        """
        Resolves the primary key lease for an incoming request across the provider chain.
        Returns (KeyLease, chain_of_providers_to_try).
        """
        # Determine provider priority chain
        chain = list(DEFAULT_PROVIDER_CHAIN)
        if preferred_provider and preferred_provider in chain:
            chain.remove(preferred_provider)
            chain.insert(0, preferred_provider)

        # 1. Try user keys in priority order
        if user_id and db is not None:
            for prov in chain:
                lease = self.select_key(user_id=user_id, db=db, provider=prov)
                if lease:
                    return lease, chain

        # 2. If no user keys, try server fallback if allowed
        if allow_server_fallback:
            for prov in chain:
                lease = self.get_server_fallback_key(prov)
                if lease:
                    return lease, chain

        return None, chain


multi_key_router = MultiKeyRouter()
