"""
RDS PostgreSQL connection via psycopg2 with SSL (verify-full).

Password resolution order:
  1. RDS_DB_PASSWORD env var (plaintext, dev/test only)
  2. AWS Secrets Manager secret named by RDS_SECRET_NAME env var (production)

Call `get_connection()` to obtain a live psycopg2 connection.
Call `get_cursor()` as a context manager for auto-commit + auto-close.
"""

import json
import os
import ssl
from contextlib import contextmanager
from typing import Generator

import boto3
import psycopg2
import psycopg2.extras

# ── Connection parameters ─────────────────────────────────────────────────────

RDS_HOST = os.getenv("RDS_HOST", "pg-database.cxekc0wmoulk.ap-south-1.rds.amazonaws.com")
RDS_PORT = int(os.getenv("RDS_PORT", "5432"))
RDS_DB = os.getenv("RDS_DB", "postgres")
RDS_USER = os.getenv("RDS_USER", "postgres")
RDS_SSL_CERT = os.getenv("RDS_SSL_CERT", "./global-bundle.pem")
RDS_SECRET_NAME = os.getenv("RDS_SECRET_NAME", "")   # AWS Secrets Manager secret name
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")


# ── Password resolution ───────────────────────────────────────────────────────

def _resolve_password() -> str:
    """
    Fetch the DB password from env var or AWS Secrets Manager.
    Secrets Manager is preferred in production (RDS_SECRET_NAME set).
    """
    plaintext = os.getenv("RDS_DB_PASSWORD", "")
    if plaintext:
        return plaintext

    if not RDS_SECRET_NAME:
        raise RuntimeError(
            "No DB password found. Set RDS_DB_PASSWORD or RDS_SECRET_NAME."
        )

    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=RDS_SECRET_NAME)

    secret_str = response.get("SecretString", "")
    if not secret_str:
        raise RuntimeError(f"Secret '{RDS_SECRET_NAME}' has no SecretString value.")

    # Secrets Manager stores RDS secrets as JSON: {"username": ..., "password": ...}
    try:
        secret_dict = json.loads(secret_str)
        return secret_dict["password"]
    except (json.JSONDecodeError, KeyError):
        # Plain-text secret (not JSON)
        return secret_str


# ── Connection factory ────────────────────────────────────────────────────────

def get_connection() -> psycopg2.extensions.connection:
    """
    Open and return a new psycopg2 connection to the RDS instance.

    SSL mode is always `verify-full`; the RDS global CA bundle must exist at
    RDS_SSL_CERT (default: ./global-bundle.pem).

    The caller is responsible for closing the connection.
    """
    password = _resolve_password()

    conn = psycopg2.connect(
        host=RDS_HOST,
        port=RDS_PORT,
        database=RDS_DB,
        user=RDS_USER,
        password=password,
        sslmode="verify-full",
        sslrootcert=RDS_SSL_CERT,
        cursor_factory=psycopg2.extras.RealDictCursor,  # rows as dicts
    )
    return conn


@contextmanager
def get_cursor(
    autocommit: bool = False,
) -> Generator[psycopg2.extensions.cursor, None, None]:
    """
    Context manager that yields a cursor, commits on success, rolls back on
    error, and always closes the connection.

    Usage::

        with get_cursor() as cur:
            cur.execute("SELECT 1")
    """
    conn = get_connection()
    try:
        conn.autocommit = autocommit
        with conn.cursor() as cur:
            yield cur
        if not autocommit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Health check ──────────────────────────────────────────────────────────────

def check_rds_connection() -> bool:
    """Ping the RDS instance. Returns True on success, False on failure."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()
            print(f"[RDS] Connected — {version['version']}")
        return True
    except Exception as exc:
        print(f"[RDS] Connection failed: {exc}")
        return False
