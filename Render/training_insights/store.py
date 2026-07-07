import uuid

from datetime import datetime, timedelta
from typing import Dict, Optional

from .models import TrainingSessionContext


_SESSION_STORE: Dict[str, TrainingSessionContext] = {}
SESSION_TTL_MINUTES = 10


def _utcnow() -> datetime:
    return datetime.utcnow()


def purge_expired_sessions() -> None:
    now = _utcnow()
    expired_ids = [sid for sid, ctx in _SESSION_STORE.items() if ctx.expires_at <= now]
    for sid in expired_ids:
        _SESSION_STORE.pop(sid, None)


def create_session_context(
    start_date: str,
    end_date: str,
    zone3: int,
    zone5: int,
    activity_records,
    activity_summaries,
    replace_session_id: Optional[str] = None,
) -> str:
    purge_expired_sessions()
    if replace_session_id:
        _SESSION_STORE.pop(replace_session_id, None)
    created_at = _utcnow()
    session_id = str(uuid.uuid4())
    _SESSION_STORE[session_id] = TrainingSessionContext(
        session_id=session_id,
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=SESSION_TTL_MINUTES),
        start_date=str(start_date),
        end_date=str(end_date),
        zone3=int(zone3),
        zone5=int(zone5),
        activity_records=list(activity_records),
        activity_summaries=list(activity_summaries),
    )
    return session_id


def get_session_context(session_id: str) -> Optional[TrainingSessionContext]:
    purge_expired_sessions()
    return _SESSION_STORE.get(session_id)
