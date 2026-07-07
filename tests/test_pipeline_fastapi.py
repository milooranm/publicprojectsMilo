import io
from datetime import date

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from Render import fast_inst


class _DummyModel:
    def predict_proba(self, x):
        return np.array([[0.2, 0.8] for _ in range(len(x))])


def _mock_open_binary(*args, **kwargs):
    class _Ctx:
        def __enter__(self):
            return io.BytesIO(b"dummy")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    return _Ctx()


def test_runitall_happy_path_with_monkeypatched_pipeline(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "Date": "10-12-2025",
                "ACWR": 1.2,
                "Day1 total km": 12.0,
                "5day/3W tot km ratio": 0.32,
                "5day/3W proportion km z3+": 1.01,
                "5day/3W nr. sessions ratio": 0.30,
                "5day/3W hours alternative training ratio": 0.05,
            },
            {
                "Date": "11-12-2025",
                "ACWR": 1.1,
                "Day1 total km": 9.0,
                "5day/3W tot km ratio": 0.28,
                "5day/3W proportion km z3+": 0.97,
                "5day/3W nr. sessions ratio": 0.24,
                "5day/3W hours alternative training ratio": 0.04,
            },
        ]
    )

    fast_inst.plt.switch_backend("Agg")
    monkeypatch.setattr(fast_inst, "open", _mock_open_binary, raising=False)
    monkeypatch.setattr(fast_inst.pickle, "load", lambda _: _DummyModel())
    monkeypatch.setattr(
        fast_inst,
        "main_api_call",
        lambda *args, **kwargs: (
            date(2025, 9, 1),
            date(2025, 12, 11),
            [{"date": "10-12-2025", "nr. sessions": 1, "total_km": 12.0, "km_z34": 2.0, "km_z5plus": 0.5}],
            [{"date": "10-12-2025", "hours_alternative": 0.5}],
            [
                {
                    "activity_id": "run-1",
                    "date": "10-12-2025",
                    "activity_type": "running",
                    "distance_km": 12.0,
                    "duration_seconds": 3600,
                    "pace_min_per_km": 5.0,
                    "avg_hr": 150,
                    "max_hr": 172,
                    "km_z34": 2.0,
                    "km_z5plus": 0.5,
                }
            ],
        ),
    )
    monkeypatch.setattr(fast_inst, "main_extract_transform", lambda *args, **kwargs: df.copy())
    monkeypatch.setattr(fast_inst, "create_session_context", lambda **kwargs: "session-xyz")
    monkeypatch.setattr(
        fast_inst,
        "build_activity_summaries",
        lambda activity_records, scored_df, recent_days=90: [],
    )

    img, session_id = fast_inst.runitall("user@example.com", "pw", 150, 180)

    assert isinstance(img, io.BytesIO)
    assert img.getbuffer().nbytes > 0
    assert session_id == "session-xyz"


def test_fastapi_predict_and_visualize_returns_html(monkeypatch):
    monkeypatch.setattr(
        fast_inst,
        "runitall",
        lambda email, password, zone3, zone5: (io.BytesIO(b"pngbytes"), "session-abc"),
    )
    client = TestClient(fast_inst.app)
    response = client.post(
        "/predict_and_visualize/",
        data={
            "email": "user@example.com",
            "password": "pw",
            "zone3": "150",
            "zone5": "180",
        },
    )

    assert response.status_code == 200
    assert "Your Injury Risk Prediction" in response.text
    assert "data-training-session-id=\"session-abc\"" in response.text
