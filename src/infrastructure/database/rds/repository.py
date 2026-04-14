"""
Repository layer for the three RDS auth tables.

All methods use `get_cursor()` so each call gets a fresh connection from the
RDS module — no persistent connection is held between calls.

Password hashing/verification is delegated to bcrypt (passlib).
JWT token hashing uses SHA-256 so raw tokens are never stored.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from passlib.context import CryptContext

from .connection import get_cursor

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_token(raw_token: str) -> str:
    """SHA-256 hex digest of a raw JWT string."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── User Credentials ──────────────────────────────────────────────────────────

def create_user(
    tenant_id: str,
    email: str,
    plain_password: str,
    role: str = "CLIENT_USER",
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> dict:
    """
    Insert a new user and return the created row.
    Raises psycopg2.errors.UniqueViolation if (tenant_id, email) already exists.
    """
    password_hash = _pwd_ctx.hash(plain_password)
    sql = """
        INSERT INTO user_credentials
            (tenant_id, email, password_hash, role, first_name, last_name)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *;
    """
    with get_cursor() as cur:
        cur.execute(sql, (tenant_id, email, password_hash, role, first_name, last_name))
        return dict(cur.fetchone())


def get_user_by_email(tenant_id: str, email: str) -> Optional[dict]:
    """Return user row or None if not found."""
    sql = """
        SELECT * FROM user_credentials
        WHERE tenant_id = %s AND email = %s AND is_active = TRUE;
    """
    with get_cursor() as cur:
        cur.execute(sql, (tenant_id, email))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Return user row by primary key."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM user_credentials WHERE id = %s;", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if plain_password matches the stored bcrypt hash."""
    return _pwd_ctx.verify(plain_password, password_hash)


def update_last_login(user_id: str) -> None:
    """Stamp last_login_at with the current UTC time."""
    sql = "UPDATE user_credentials SET last_login_at = %s WHERE id = %s;"
    with get_cursor() as cur:
        cur.execute(sql, (_now_utc(), user_id))


def deactivate_user(user_id: str) -> None:
    """Soft-delete: set is_active = FALSE."""
    with get_cursor() as cur:
        cur.execute(
            "UPDATE user_credentials SET is_active = FALSE WHERE id = %s;", (user_id,)
        )


# ── JWT Tokens ────────────────────────────────────────────────────────────────

def store_token(
    user_id: str,
    raw_token: str,
    expires_at: datetime,
    token_type: str = "refresh",
) -> dict:
    """
    Hash raw_token with SHA-256 and persist the record.
    Returns the inserted row (token_hash, not the raw token).
    """
    sql = """
        INSERT INTO jwt_tokens (user_id, token_hash, token_type, expires_at)
        VALUES (%s, %s, %s, %s)
        RETURNING *;
    """
    with get_cursor() as cur:
        cur.execute(sql, (user_id, _hash_token(raw_token), token_type, expires_at))
        return dict(cur.fetchone())


def get_token(raw_token: str) -> Optional[dict]:
    """Look up a token record by the raw token value (hashed internally)."""
    sql = """
        SELECT * FROM jwt_tokens
        WHERE token_hash = %s AND revoked = FALSE AND expires_at > NOW();
    """
    with get_cursor() as cur:
        cur.execute(sql, (_hash_token(raw_token),))
        row = cur.fetchone()
        return dict(row) if row else None


def revoke_token(raw_token: str) -> None:
    """Mark a single token as revoked (logout / rotation)."""
    sql = "UPDATE jwt_tokens SET revoked = TRUE WHERE token_hash = %s;"
    with get_cursor() as cur:
        cur.execute(sql, (_hash_token(raw_token),))


def revoke_all_user_tokens(user_id: str) -> None:
    """Revoke every active token for a user (force logout from all devices)."""
    sql = "UPDATE jwt_tokens SET revoked = TRUE WHERE user_id = %s AND revoked = FALSE;"
    with get_cursor() as cur:
        cur.execute(sql, (user_id,))


def purge_expired_tokens() -> int:
    """Delete expired token rows. Returns count of deleted rows."""
    sql = "DELETE FROM jwt_tokens WHERE expires_at <= NOW() RETURNING id;"
    with get_cursor() as cur:
        cur.execute(sql)
        return cur.rowcount


# ── User Sessions ─────────────────────────────────────────────────────────────

def create_session(
    user_id: str,
    tenant_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """Open a new session and return its row."""
    sql = """
        INSERT INTO user_sessions (user_id, tenant_id, ip_address, user_agent)
        VALUES (%s, %s, %s, %s)
        RETURNING *;
    """
    with get_cursor() as cur:
        cur.execute(sql, (user_id, tenant_id, ip_address, user_agent))
        return dict(cur.fetchone())


def get_session(session_id: str) -> Optional[dict]:
    """Return a session row or None."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM user_sessions WHERE id = %s;", (session_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def touch_session(session_id: str) -> None:
    """Update last_active_at to now (call on every authenticated request)."""
    sql = "UPDATE user_sessions SET last_active_at = NOW() WHERE id = %s;"
    with get_cursor() as cur:
        cur.execute(sql, (session_id,))


def end_session(session_id: str) -> None:
    """Mark a session as ended (explicit logout)."""
    sql = """
        UPDATE user_sessions
        SET status = 'ended', ended_at = NOW()
        WHERE id = %s AND status = 'active';
    """
    with get_cursor() as cur:
        cur.execute(sql, (session_id,))


def expire_idle_sessions(idle_minutes: int = 30) -> int:
    """
    Mark sessions as expired when last_active_at is older than idle_minutes.
    Returns count of expired rows.
    """
    sql = """
        UPDATE user_sessions
        SET status = 'expired', ended_at = NOW()
        WHERE status = 'active'
          AND last_active_at < NOW() - INTERVAL '%s minutes'
        RETURNING id;
    """
    with get_cursor() as cur:
        cur.execute(sql, (idle_minutes,))
        return cur.rowcount


def list_active_sessions(user_id: str) -> list[dict]:
    """Return all active sessions for a user (useful for device management UI)."""
    sql = """
        SELECT * FROM user_sessions
        WHERE user_id = %s AND status = 'active'
        ORDER BY last_active_at DESC;
    """
    with get_cursor() as cur:
        cur.execute(sql, (user_id,))
        return [dict(r) for r in cur.fetchall()]
