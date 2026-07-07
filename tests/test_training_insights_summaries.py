import pandas as pd

from Render.training_insights.summaries import build_activity_summaries


def test_build_activity_summaries_includes_only_running_and_recent_window():
    activity_records = [
        {
            "activity_id": "run-1",
            "date": "10-12-2025",
            "activity_type": "running",
            "distance_km": 22.0,
            "duration_seconds": 6600,
            "pace_min_per_km": 5.0,
            "avg_hr": 152,
            "max_hr": 176,
            "km_z34": 4.0,
            "km_z5plus": 1.2,
        },
        {
            "activity_id": "bike-1",
            "date": "10-12-2025",
            "activity_type": "cycling",
            "duration_seconds": 3600,
            "hours_alternative": 1.0,
        },
        {
            "activity_id": "run-old",
            "date": "01-07-2025",
            "activity_type": "running",
            "distance_km": 8.0,
            "duration_seconds": 2400,
            "pace_min_per_km": 5.0,
        },
    ]

    scored_df = pd.DataFrame(
        [
            {
                "Date": "10-12-2025",
                "injury probabilities": 0.72,
                "ACWR": 1.41,
                "5day/3W tot km ratio": 0.35,
                "5day/3W proportion km z3+": 1.08,
                "5day/3W nr. sessions ratio": 0.30,
                "5day/3W hours alternative training ratio": 0.10,
                "Day1 total km": 22.0,
            }
        ]
    )

    summaries = build_activity_summaries(activity_records, scored_df, recent_days=90)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.activity_id == "run-1"
    assert summary.searchable is True
    assert summary.run_details["distance_km"] == 22.0
    assert summary.risk_details["injury_probability"] == 0.72
    assert "Run details:" in summary.text
    assert "Risk details:" in summary.text


def test_build_activity_summaries_missing_risk_data_sets_none_probability_note():
    activity_records = [
        {
            "activity_id": "run-2",
            "date": "11-12-2025",
            "activity_type": "running",
            "distance_km": 9.5,
            "duration_seconds": 2700,
            "pace_min_per_km": 4.74,
            "avg_hr": 148,
            "max_hr": 165,
        }
    ]
    scored_df = pd.DataFrame(columns=["Date", "injury probabilities", "ACWR"])

    summaries = build_activity_summaries(activity_records, scored_df, recent_days=90)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.risk_details["injury_probability"] is None
    assert summary.risk_details["observation"] == "No model probability available for this date"


def test_multiple_runs_same_day_share_daily_risk_context():
    activity_records = [
        {
            "activity_id": "run-am",
            "date": "14-12-2025",
            "activity_type": "running",
            "distance_km": 8.0,
            "duration_seconds": 2400,
            "pace_min_per_km": 5.0,
            "avg_hr": 145,
            "max_hr": 162,
            "km_z34": 1.5,
            "km_z5plus": 0.2,
        },
        {
            "activity_id": "run-pm",
            "date": "14-12-2025",
            "activity_type": "running",
            "distance_km": 6.0,
            "duration_seconds": 1860,
            "pace_min_per_km": 5.17,
            "avg_hr": 148,
            "max_hr": 168,
            "km_z34": 1.0,
            "km_z5plus": 0.3,
        },
    ]

    scored_df = pd.DataFrame(
        [
            {
                "Date": "14-12-2025",
                "injury probabilities": 0.63,
                "ACWR": 1.34,
                "5day/3W tot km ratio": 0.31,
                "5day/3W proportion km z3+": 1.02,
                "5day/3W nr. sessions ratio": 0.28,
                "5day/3W hours alternative training ratio": 0.11,
                "Day1 total km": 14.0,
            }
        ]
    )

    summaries = build_activity_summaries(activity_records, scored_df, recent_days=90)

    assert len(summaries) == 2
    probs = {s.activity_id: s.risk_details["injury_probability"] for s in summaries}
    acwrs = {s.activity_id: s.risk_details["acwr"] for s in summaries}
    assert probs["run-am"] == probs["run-pm"] == 0.63
    assert acwrs["run-am"] == acwrs["run-pm"] == 1.34
