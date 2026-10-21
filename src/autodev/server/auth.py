"""Single-user local login: scrypt password hash, opaque session cookie, brute-force throttling.

The dashboard can start agents and spend quota, so it is bound to localhost and still asks for a
password. First-run setup additionally needs a one-time code printed in the server's terminal, so
a web page that tries to reach localhost cannot claim the dashboard before its owner does.
"""
import hashlib
import hmac
import secrets
import time

from autodev.db import Database

COOKIE = "autodev_session"
SESSION_SECONDS = 7 * 24 * 3600
MIN_PASSWORD = 10
MAX_FAILURES = 5
WINDOW_SECONDS = 60


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    candidate = hash_password(password, bytes.fromhex(salt_hex)).split("$")[2]
    return hmac.compare_digest(candidate, digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, db: Database):
        self.db = db
        self.setup_code: str | None = None if self.configured else secrets.token_urlsafe(9)
        self._failures: list[float] = []

    @property
    def configured(self) -> bool:
        return self.db.get_setting("password_hash") is not None

    def set_password(self, password: str, code: str) -> None:
        if self.configured:
            raise PermissionError("password already set")
        if not self.setup_code or not hmac.compare_digest(code or "", self.setup_code):
            raise PermissionError("wrong setup code")
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"the password must be at least {MIN_PASSWORD} characters")
        self.db.set_setting("password_hash", hash_password(password))
        self.setup_code = None

    def retry_after(self) -> int:
        now = time.time()
        self._failures = [t for t in self._failures if now - t < WINDOW_SECONDS]
        if len(self._failures) >= MAX_FAILURES:
            return int(WINDOW_SECONDS - (now - self._failures[0])) + 1
        return 0

    def login(self, password: str) -> str | None:
        stored = self.db.get_setting("password_hash")
        if stored and verify_password(password, stored):
            self._failures.clear()
            return self.new_session()
        self._failures.append(time.time())
        return None

    def new_session(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        self.db.execute(
            "INSERT INTO sessions(token_hash, created_at, expires_at) VALUES(?, ?, ?)",
            (_token_hash(token), now, now + SESSION_SECONDS),
        )
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        row = self.db.one("SELECT expires_at FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        return bool(row and row["expires_at"] > time.time())

    def logout(self, token: str | None) -> None:
        if token:
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
