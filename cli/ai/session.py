"""AI session management — multi-turn conversation persistence."""

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

from ..config import SessionConfig, load_config


class Session:
    """A single AI conversation session."""

    def __init__(self, session_id: str, created_at: float, messages: list[dict], last_active: float):
        self.session_id = session_id
        self.created_at = created_at
        self.messages = messages  # list of {"role": "user"|"assistant", "content": str}
        self.last_active = last_active

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "messages": self.messages,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            session_id=data["session_id"],
            created_at=data["created_at"],
            messages=data.get("messages", []),
            last_active=data.get("last_active", data["created_at"]),
        )

    def is_expired(self, ttl_hours: int) -> bool:
        last_touch = max(self.created_at, self.last_active)
        age_hours = (time.time() - last_touch) / 3600
        return age_hours > ttl_hours

    def add_turn(self, user_message: str, assistant_message: str, max_history: int) -> None:
        """Add a conversation turn, trimming to max_history."""
        self.messages.append({"role": "user", "content": user_message})
        self.messages.append({"role": "assistant", "content": assistant_message})
        self.last_active = time.time()
        # Keep only the last max_history turns (each turn = 2 messages)
        max_messages = max_history * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def get_history(self) -> list[dict]:
        """Return messages suitable for injection into AI API calls."""
        return list(self.messages)


class SessionStore:
    """Persists AI sessions to disk as JSON files."""

    def __init__(self, config: SessionConfig | None = None):
        if config is None:
            config = load_config().session
        self._config = config
        self._sessions_dir = Path(config.sessions_dir)
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        # Allowlist validation: only alphanumeric, dash, underscore (prevents path traversal)
        if not _SESSION_ID_RE.match(session_id):
            raise ValueError(f"Invalid session ID format: {session_id!r}")
        return self._sessions_dir / f"{session_id}.json"

    def new_session(self) -> "Session":
        """Create a new session with a unique ID."""
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%dT%H%M%S")
        uid = uuid.uuid4().hex[:8]
        session_id = f"{ts}-{uid}"
        now_ts = now.timestamp()
        session = Session(
            session_id=session_id,
            created_at=now_ts,
            messages=[],
            last_active=now_ts,
        )
        self.save(session)
        return session

    def load(self, session_id: str) -> Optional["Session"]:
        """Load a session by ID. Returns None if not found, expired, or invalid ID."""
        try:
            path = self._session_path(session_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            session = Session.from_dict(data)
            if session.is_expired(self._config.ttl_hours):
                path.unlink(missing_ok=True)
                return None
            return session
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def save(self, session: "Session") -> None:
        """Persist session to disk (atomic write via temp file)."""
        path = self._session_path(session.session_id)
        tmp_path = path.with_suffix(".tmp")
        try:
            fd = os.open(str(tmp_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False)
            tmp_path.replace(path)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise

    def list_sessions(self) -> list[dict]:
        """List all non-expired sessions (summary only)."""
        sessions = []
        for p in self._sessions_dir.glob("*.json"):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                created_at = data["created_at"]
                last_active = data.get("last_active", created_at)
                last_touch = max(created_at, last_active)
                age_hours = (time.time() - last_touch) / 3600
                if age_hours > self._config.ttl_hours:
                    p.unlink(missing_ok=True)
                    continue
                sessions.append({
                    "session_id": data["session_id"],
                    "created_at": datetime.fromtimestamp(created_at, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_active": datetime.fromtimestamp(data.get("last_active", created_at), tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    "turns": len(data.get("messages", [])) // 2,
                })
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return sessions

    def clear(self, session_id: str | None = None) -> int:
        """Clear one session or all sessions. Returns count of removed files."""
        if session_id:
            try:
                path = self._session_path(session_id)
            except ValueError:
                return 0
            if path.exists():
                path.unlink()
                return 1
            return 0
        count = 0
        for p in self._sessions_dir.glob("*.json"):
            p.unlink(missing_ok=True)
            count += 1
        return count

    def purge_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        count = 0
        for p in self._sessions_dir.glob("*.json"):
            if p.suffix == ".tmp":
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                if session.is_expired(self._config.ttl_hours):
                    p.unlink(missing_ok=True)
                    count += 1
            except (json.JSONDecodeError, KeyError, OSError):
                p.unlink(missing_ok=True)
                count += 1
        return count
