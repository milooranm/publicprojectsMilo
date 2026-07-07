from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ActivityRecord:
    activity_id: str
    date: str
    activity_type: str
    start_time_local: str
    activity_name: str = ""
    distance_km: Optional[float] = None
    duration_seconds: Optional[float] = None
    pace_min_per_km: Optional[float] = None
    avg_hr: Optional[float] = None
    max_hr: Optional[float] = None
    km_z34: Optional[float] = None
    km_z5plus: Optional[float] = None
    hours_alternative: Optional[float] = None


@dataclass
class ActivitySummary:
    summary_id: str
    activity_id: str
    date: str
    searchable: bool
    run_details: Dict[str, Any] = field(default_factory=dict)
    risk_details: Dict[str, Any] = field(default_factory=dict)
    text: str = ""


@dataclass
class TrainingSessionContext:
    session_id: str
    created_at: datetime
    expires_at: datetime
    start_date: str
    end_date: str
    zone3: int
    zone5: int
    activity_records: List[Dict[str, Any]] = field(default_factory=list)
    activity_summaries: List[ActivitySummary] = field(default_factory=list)
