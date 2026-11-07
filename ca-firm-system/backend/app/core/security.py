"""Password hashing, access-token (JWT) handling and refresh-token generation.

Authentication seam: ``decode_access_token`` is the only place that verifies bearer tokens. To move
to Keycloak/OIDC later, replace it (and ``services/auth.py`` login/refresh) with JWKS verification;
authorization (``services/authz.py``) is independent of how the identity was proven.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings
from app.core.errors import AuthenticationError, DomainValidationError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()  # argon2id with library defaults (RFC 9106 low-memory profile)
# Verified against when the user does not exist, to keep login timing uniform.
_DUMMY_HASH = _hasher.hash("not-a-real-password-for-timing-equalisation")


def validate_password_strength(password: str) -> None:
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise DomainValidationError(
            f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters long"
        )
    if password.strip() == "" or len(set(password)) < 5:
        raise DomainValidationError("Password is too simple")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def burn_dummy_verification(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    firm_id: uuid.UUID
    session_id: uuid.UUID  # refresh-token family; lets logout invalidate access tokens immediately


def create_access_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    firm_id: uuid.UUID,
    session_id: uuid.UUID,
    now: datetime | None = None,
) -> tuple[str, int]:
    """Returns (token, expires_in_seconds). Roles/permissions are deliberately NOT in the token:
    they are read from the database on every request so changes take effect immediately."""
    issued = now or datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(user_id),
        "firm": str(firm_id),
        "sid": str(session_id),
        "typ": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(issued.timestamp()),
        "exp": int((issued + ttl).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    return token, int(ttl.total_seconds())


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],  # explicit allow-list: rejects "none" and algorithm confusion
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "firm", "sid", "typ", "iss", "aud"]},
        )
        if payload["typ"] != "access":
            raise AuthenticationError("Invalid token")
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            firm_id=uuid.UUID(payload["firm"]),
            session_id=uuid.UUID(payload["sid"]),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthenticationError("Invalid or expired token") from exc


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hex). Only the hash is persisted."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
