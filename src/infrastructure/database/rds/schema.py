"""
DDL for the three auth tables stored in RDS PostgreSQL:

  • user_credentials  — login email + bcrypt password hash + role
  • jwt_tokens        — hashed refresh tokens with expiry + revocation flag
  • user_sessions     — session lifecycle (active / ended / expired)

Run `python -m src.infrastructure.database.rds.schema` once to bootstrap the
schema (idempotent — uses CREATE TABLE IF NOT EXISTS).
"""

from .connection import get_cursor

# ── DDL statements ────────────────────────────────────────────────────────────

_CREATE_USER_CREDENTIALS = """
CREATE TABLE IF NOT EXISTS user_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(30)  NOT NULL DEFAULT 'CLIENT_USER',
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_credentials_tenant_email UNIQUE (tenant_id, email)
);

CREATE INDEX IF NOT EXISTS idx_user_credentials_email     ON user_credentials (email);
CREATE INDEX IF NOT EXISTS idx_user_credentials_tenant_id ON user_credentials (tenant_id);
"""

_CREATE_JWT_TOKENS = """
CREATE TABLE IF NOT EXISTS jwt_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL REFERENCES user_credentials (id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,   -- SHA-256 of the raw token
    token_type  VARCHAR(20)  NOT NULL DEFAULT 'refresh',  -- 'refresh' | 'access'
    expires_at  TIMESTAMPTZ  NOT NULL,
    revoked     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jwt_tokens_user_id    ON jwt_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_jwt_tokens_token_hash ON jwt_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_jwt_tokens_expires_at ON jwt_tokens (expires_at);
"""

_CREATE_USER_SESSIONS = """
CREATE TABLE IF NOT EXISTS user_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES user_credentials (id) ON DELETE CASCADE,
    tenant_id       UUID        NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',  -- active | ended | expired
    ip_address      VARCHAR(45),          -- IPv4 or IPv6
    user_agent      TEXT,
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id   ON user_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_tenant_id ON user_sessions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_status    ON user_sessions (status);
"""

# Auto-update updated_at on user_credentials
_CREATE_UPDATED_AT_TRIGGER = """
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_user_credentials_updated_at'
    ) THEN
        CREATE TRIGGER trg_user_credentials_updated_at
        BEFORE UPDATE ON user_credentials
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END;
$$;
"""

# ── Bootstrap ─────────────────────────────────────────────────────────────────

def create_tables() -> None:
    """Create all auth tables if they do not already exist (idempotent)."""
    with get_cursor() as cur:
        cur.execute(_CREATE_USER_CREDENTIALS)
        cur.execute(_CREATE_JWT_TOKENS)
        cur.execute(_CREATE_USER_SESSIONS)
        cur.execute(_CREATE_UPDATED_AT_TRIGGER)
    print("[RDS] Auth schema bootstrap complete.")


if __name__ == "__main__":
    create_tables()
