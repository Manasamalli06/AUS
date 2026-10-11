import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

USERS_DB_PATH = settings.DB_DIR / "users.json"
SECRET_KEY = "geospatial-measurement-api-secret-key-salt-2026"


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hashes password with PBKDF2-HMAC-SHA256 and unique salt."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return key.hex(), salt


def verify_password(password: str, hashed_hex: str, salt: str) -> bool:
    """Verifies a password against the stored PBKDF2 hash."""
    expected_hex, _ = hash_password(password, salt)
    return hmac.compare_digest(expected_hex, hashed_hex)


def generate_token(user_id: str, username: str) -> str:
    """Generates a signed URL-safe bearer token with expiration timestamp."""
    exp = int(time.time()) + (24 * 3600)  # 24 hours validity
    payload = f"{user_id}:{username}:{exp}"
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies signature and expiration of a bearer token."""
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        user_id, username, exp_str, signature = parts
        exp = int(exp_str)
        if time.time() > exp:
            return None  # expired
        payload = f"{user_id}:{username}:{exp}"
        expected_sig = hmac.new(
            SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected_sig, signature):
            return {"user_id": user_id, "username": username, "expires_at": exp}
        return None
    except Exception:
        return None


class UserManager:
    """Thread-safe persistent user manager."""

    def __init__(self, db_path: Path = USERS_DB_PATH):
        self.db_path = db_path
        self._lock = Lock()
        self._users: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        with self._lock:
            if self.db_path.exists():
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        self._users = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load users from {self.db_path}: {e}")

    def _save(self):
        try:
            temp = self.db_path.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(self._users, f, indent=2)
            temp.replace(self.db_path)
        except Exception as e:
            logger.error(f"Failed to save users: {e}")

    def create_user(
        self, username: str, email: str, password: str, full_name: Optional[str] = None
    ) -> Dict[str, Any]:
        with self._lock:
            username_clean = username.strip().lower()
            email_clean = email.strip().lower()

            # Check duplicates
            for u in self._users.values():
                if u["username"].lower() == username_clean:
                    raise ValueError(f"Username '{username}' is already taken.")
                if u["email"].lower() == email_clean:
                    raise ValueError(f"Email '{email}' is already registered.")

            user_id = secrets.token_hex(8)
            password_hash, salt = hash_password(password)

            user_data = {
                "id": user_id,
                "username": username.strip(),
                "email": email_clean,
                "full_name": full_name or username.strip(),
                "password_hash": password_hash,
                "salt": salt,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._users[user_id] = user_data
            self._save()
            return user_data

    def authenticate_user(self, username_or_email: str, password: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            lookup = username_or_email.strip().lower()
            user = None
            for u in self._users.values():
                if u["username"].lower() == lookup or u["email"].lower() == lookup:
                    user = u
                    break

            if not user:
                return None

            if verify_password(password, user["password_hash"], user["salt"]):
                return user
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._users.get(user_id)


user_manager = UserManager()
