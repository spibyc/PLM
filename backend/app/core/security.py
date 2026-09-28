import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()  # Argon2id with library defaults (RFC 9106 recommended profile)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_password_policy(password: str, min_length: int) -> None:
    from app.core.errors import DomainError

    if len(password) < min_length:
        raise DomainError(f"Password must be at least {min_length} characters", "weak_password")
    if password.lower() == password or password.upper() == password:
        raise DomainError("Password must mix upper and lower case", "weak_password")
    if not any(c.isdigit() for c in password):
        raise DomainError("Password must contain a digit", "weak_password")
