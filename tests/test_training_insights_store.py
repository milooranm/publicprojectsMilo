from datetime import datetime, timedelta

from Render.training_insights import store


def test_create_and_get_session_context_roundtrip():
    store._SESSION_STORE.clear()

    session_id = store.create_session_context(
        start_date="2025-09-01",
        end_date="2025-12-01",
        zone3=150,
        zone5=180,
        activity_records=[{"activity_id": "run-1"}],
        activity_summaries=[],
    )

    ctx = store.get_session_context(session_id)
    assert ctx is not None
    assert ctx.session_id == session_id
    assert ctx.zone3 == 150
    assert ctx.zone5 == 180
    assert len(ctx.activity_records) == 1


def test_purge_expired_sessions_removes_old_contexts():
    store._SESSION_STORE.clear()
    expired_id = "expired-session"
    now = datetime.utcnow()
    store._SESSION_STORE[expired_id] = store.TrainingSessionContext(
        session_id=expired_id,
        created_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=5),
        start_date="2025-01-01",
        end_date="2025-02-01",
        zone3=150,
        zone5=180,
        activity_records=[],
        activity_summaries=[],
    )

    store.purge_expired_sessions()
    assert expired_id not in store._SESSION_STORE


def test_session_replacement_removes_old_session():
    store._SESSION_STORE.clear()

    first_id = store.create_session_context(
        start_date="2025-09-01",
        end_date="2025-12-01",
        zone3=150,
        zone5=180,
        activity_records=[{"activity_id": "run-1"}],
        activity_summaries=[],
    )
    assert store.get_session_context(first_id) is not None

    second_id = store.create_session_context(
        start_date="2025-09-01",
        end_date="2025-12-01",
        zone3=150,
        zone5=180,
        activity_records=[{"activity_id": "run-2"}],
        activity_summaries=[],
        replace_session_id=first_id,
    )

    assert second_id != first_id
    assert store.get_session_context(first_id) is None
    second_ctx = store.get_session_context(second_id)
    assert second_ctx is not None
    assert second_ctx.activity_records[0]["activity_id"] == "run-2"
