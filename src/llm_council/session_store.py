import json
import uuid
import time
from pathlib import Path
from typing import Any, Dict

SESSIONS_DIR = Path.home() / ".llm-council" / "sessions"
SESSION_TTL_HOURS = 24

def _session_path(session_id: str) -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f"{session_id}.json"

def create_session(query: str, tier: str, **kwargs) -> str:
    """Create a new council session and persist it to disk."""
    session_id = str(uuid.uuid4())[:12]
    data = {
        "session_id": session_id,
        "query": query,
        "tier": tier,
        "created_at": time.time(),
        "stage": "created",
        **kwargs,
    }
    _session_path(session_id).write_text(json.dumps(data, indent=2))
    return session_id

def load_session(session_id: str) -> Dict[str, Any]:
    """Load an existing council session from disk."""
    path = _session_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session {session_id} not found. It may have expired.")
    return json.loads(path.read_text())

def save_session(session_id: str, updates: Dict[str, Any]) -> None:
    """Update and save an existing council session."""
    data = load_session(session_id)
    data.update(updates)
    _session_path(session_id).write_text(json.dumps(data, indent=2))

def close_session(session_id: str) -> None:
    """Delete a council session from disk."""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()

def purge_expired_sessions() -> int:
    """Clean up sessions older than TTL (24 hours)."""
    cutoff = time.time() - (SESSION_TTL_HOURS * 3600)
    count = 0
    if not SESSIONS_DIR.exists():
        return 0
        
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("created_at", 0) < cutoff:
                f.unlink()
                count += 1
        except Exception:
            # Best effort cleanup
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
    return count
