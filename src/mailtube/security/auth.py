from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from mailtube.config import Settings
from mailtube.db import Database


class LoginLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window_seconds:
                events.popleft()
            return len(events) < self.attempts

    def failure(self, key: str) -> None:
        with self._lock:
            self._events[key].append(time.monotonic())

    def success(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


class AuthService:
    cookie_name = "mailtube_session"

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
        self.limiter = LoginLimiter()

    @staticmethod
    def hash_password(password: str) -> str:
        return PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(password)

    def authenticate(self, username: str, password: str, client_key: str) -> tuple[str, str, str]:
        if not self.limiter.allowed(client_key):
            raise PermissionError("Too many login attempts. Try again in a few minutes.")
        configured_username = self.settings.admin_username
        configured_hash = self.settings.admin_password_hash.get_secret_value()
        try:
            valid_password = bool(configured_hash) and self.hasher.verify(configured_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            valid_password = False
        valid_username = hmac.compare_digest(username, configured_username)
        if not (valid_username and valid_password):
            self.limiter.failure(client_key)
            raise PermissionError("Invalid username or password")
        self.limiter.success(client_key)
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        expires = self.db.create_session(token, csrf, username, self.settings.session_hours)
        return token, csrf, expires

    def session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        return self.db.get_session(token)
