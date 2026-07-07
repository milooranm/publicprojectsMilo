from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from .models import ActivitySummary


DATE_FMT = "%d-%m-%Y"


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(date_text: str) -> Optional[datetime]:
    try:
        return datetime.strptime(str(date_text), DATE_FMT)
    except (TypeError, ValueError):
        return None


def _context_note(distance_km: Optional[float], pace_min_per_km: Optional[float], max_hr: Optional[float]) -> str:
    notes: List[str] = []
    if distance_km is not None and distance_km >= 18:
        notes.append("Long run volume session")
    if pace_min_per_km is not None and pace_min_per_km < 4.5:
        notes.append("Relatively fast pace session")
    if max_hr is not None and max_hr >= 175:
        notes.append("High cardiovascular strain signal")
    if not notes:
        notes.append("Steady session profile")
    return "; ".join(notes)


def _risk_note(risk_probability: Optional[float], acwr: Optional[float]) -> str:
    if risk_probability is None:
        return "No model probability available for this date"
    if risk_probability >= 0.6:
        return "Elevated daily injury probability context"
    if acwr is not None and acwr >= 1.3:
        return "Higher acute-to-chronic load context"
    return "Lower relative daily injury risk context"


def _build_risk_index(scored_df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    if scored_df.empty or "Date" not in scored_df.columns:
        return {}

    keep_cols = [
        "Date",
        "injury probabilities",
        "ACWR",
        "5day/3W tot km ratio",
        "5day/3W proportion km z3+",
        "5day/3W nr. sessions ratio",
        "5day/3W hours alternative training ratio",
        "Day1 total km",
    ]
    keep_cols = [c for c in keep_cols if c in scored_df.columns]
    risk_subset = scored_df[keep_cols].copy()
    risk_subset = risk_subset.drop_duplicates(subset=["Date"], keep="last")
    return {str(row["Date"]): row.to_dict() for _, row in risk_subset.iterrows()}


def build_activity_summaries(
    activity_records: List[Dict[str, Any]],
    scored_daily_df: pd.DataFrame,
    recent_days: int = 90,
) -> List[ActivitySummary]:
    """Build one summary per running activity, enriched with same-day risk context."""

    if not activity_records:
        return []

    risk_index = _build_risk_index(scored_daily_df)

    dated_records = [r for r in activity_records if _parse_date(r.get("date")) is not None]
    if not dated_records:
        return []

    max_date = max(_parse_date(r["date"]) for r in dated_records if _parse_date(r.get("date")) is not None)
    lower_bound = max_date - timedelta(days=int(recent_days))

    summaries: List[ActivitySummary] = []
    for record in dated_records:
        activity_type = str(record.get("activity_type", "")).lower()
        if activity_type != "running":
            continue

        run_date = _parse_date(record.get("date"))
        if run_date is None or run_date < lower_bound:
            continue

        risk_row = risk_index.get(record["date"], {})
        risk_probability = _safe_float(risk_row.get("injury probabilities"))
        acwr = _safe_float(risk_row.get("ACWR"))

        run_details = {
            "date": record.get("date"),
            "distance_km": _safe_float(record.get("distance_km")),
            "duration_seconds": _safe_float(record.get("duration_seconds")),
            "pace_min_per_km": _safe_float(record.get("pace_min_per_km")),
            "avg_hr": _safe_float(record.get("avg_hr")),
            "max_hr": _safe_float(record.get("max_hr")),
            "km_z34": _safe_float(record.get("km_z34")),
            "km_z5plus": _safe_float(record.get("km_z5plus")),
        }
        run_details["observation"] = _context_note(
            run_details.get("distance_km"),
            run_details.get("pace_min_per_km"),
            run_details.get("max_hr"),
        )

        risk_details = {
            "injury_probability": risk_probability,
            "acwr": acwr,
            "5day_3w_tot_km_ratio": _safe_float(risk_row.get("5day/3W tot km ratio")),
            "5day_3w_proportion_km_z3plus": _safe_float(risk_row.get("5day/3W proportion km z3+")),
            "5day_3w_nr_sessions_ratio": _safe_float(risk_row.get("5day/3W nr. sessions ratio")),
            "5day_3w_hours_alt_ratio": _safe_float(risk_row.get("5day/3W hours alternative training ratio")),
            "day1_total_km": _safe_float(risk_row.get("Day1 total km")),
        }
        risk_details["observation"] = _risk_note(risk_probability, acwr)

        text = (
            f"Run details: date={run_details['date']}, distance_km={run_details['distance_km']}, "
            f"duration_seconds={run_details['duration_seconds']}, pace_min_per_km={run_details['pace_min_per_km']}, "
            f"avg_hr={run_details['avg_hr']}, max_hr={run_details['max_hr']}, "
            f"km_z34={run_details['km_z34']}, km_z5plus={run_details['km_z5plus']}, "
            f"note={run_details['observation']}. "
            f"Risk details: injury_probability={risk_details['injury_probability']}, acwr={risk_details['acwr']}, "
            f"5day_3w_tot_km_ratio={risk_details['5day_3w_tot_km_ratio']}, "
            f"5day_3w_proportion_km_z3plus={risk_details['5day_3w_proportion_km_z3plus']}, "
            f"5day_3w_nr_sessions_ratio={risk_details['5day_3w_nr_sessions_ratio']}, "
            f"5day_3w_hours_alt_ratio={risk_details['5day_3w_hours_alt_ratio']}, "
            f"day1_total_km={risk_details['day1_total_km']}, note={risk_details['observation']}."
        )

        summaries.append(
            ActivitySummary(
                summary_id=f"summary-{record.get('activity_id')}",
                activity_id=str(record.get("activity_id")),
                date=str(record.get("date")),
                searchable=True,
                run_details=run_details,
                risk_details=risk_details,
                text=text,
            )
        )

    return summaries
