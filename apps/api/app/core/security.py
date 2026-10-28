"""Password hashing (Argon2id), session tokens, and credential encryption (Fernet)."""
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings

_hasher = PasswordHasher()  # argon2-cffi defaults: Argon2id, RFC 9106 low-memory profile


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# A fixed dummy hash lets login spend equal time whether or not the user exists.
DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-real-password")


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Sessions are stored by SHA-256 of the token, so a DB leak does not leak live tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


class CredentialCipher:
    def __init__(self, keys: str):
        parsed = [k.strip() for k in keys.split(",") if k.strip()]
        if not parsed:
            # Development fallback: an ephemeral key. Stored secrets will be unreadable after
            # restart, which is surfaced as a clear error instead of silently failing.
            parsed = [Fernet.generate_key().decode()]
            self.ephemeral = True
        else:
            self.ephemeral = False
        self._f = MultiFernet([Fernet(k.encode()) for k in parsed])

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Credential cannot be decrypted with the configured ENCRYPTION_KEYS") from exc


_cipher: CredentialCipher | None = None


def get_cipher() -> CredentialCipher:
    global _cipher
    if _cipher is None:
        _cipher = CredentialCipher(get_settings().encryption_keys)
    return _cipher
