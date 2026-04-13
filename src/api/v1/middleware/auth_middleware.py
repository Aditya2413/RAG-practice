from fastapi import Request

from src.core.exceptions import AuthError


def extract_token_from_header(request: Request) -> str | None:
    """Extract raw JWT from Authorization: Bearer <token> header. Returns None if absent."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):]
    return token if token else None
