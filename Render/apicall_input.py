import datetime
import logging
import os
import requests
import pandas as pd

from io import BytesIO
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional, Tuple

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def init_api(email: str, password: str) -> Optional[Garmin]:
    """Initialize Garmin API with your credentials."""
    garmin: Optional[Garmin] = None
    try:
        garmin = Garmin(email, password)
        garmin.login()
        print("Login successful!")
    except Exception as e:
        logger.error(e)
        print(f"An error occurred during login: {e}")

    return garmin


def _duration_to_seconds(time_str: str) -> float:
    """Convert Garmin CSV time strings to total seconds."""
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S"):
        try:
            time_obj = datetime.datetime.strptime(time_str, fmt).time()
            return float(
                time_obj.hour * 3600
                + time_obj.minute * 60
                + time_obj.second
                + (getattr(time_obj, "microsecond", 0) / 1_000_000)
            )
        except ValueError:
            continue
    return 0.0


def get_activities(
    api: Garmin,
    start_date: datetime.date,
    end_date: datetime.date,
    Z3_min: int = 135,
    Z5_min: int = 172,
    include_activity_records: bool = False,
) -> Any:
    """
    Retrieves activity data within a date range and returns two lists of per-day dicts:
    - run_daily: [{ 'date': DD-MM-YYYY, 'total_km': float, 'km_z34': float, 'km_z5plus': float }]
    - other_daily: [{ 'date': DD-MM-YYYY, 'hours_alternative': float }]
    """
    run_by_date: Dict[str, Dict] = {}
    other_by_date: Dict[str, Dict] = {}
    activity_records: List[Dict[str, Any]] = []
    run_cols = ['Distance', 'Avg HR','Time']
    other_cols = ['Time']
    try:
        activities = api.get_activities_by_date(
            start_date.isoformat(), end_date.isoformat()
        )

        for activity in activities:
            activity_start_date = datetime.datetime.strptime(
                activity["startTimeLocal"], "%Y-%m-%d %H:%M:%S"
            ).strftime("%d-%m-%Y")
            activity_type = activity.get('activityType', {}).get('typeKey', 'unknown')
            activity_id = activity["activityId"]
            activity_name = activity.get("activityName", "")
            start_time_local = activity.get("startTimeLocal", "")
            csv_data = api.download_activity(
                activity_id, dl_fmt=api.ActivityDownloadFormat.CSV
            )
            # Is it a running activity?
            if activity_type and activity_type.lower() == 'running':
                run_df = pd.read_csv(BytesIO(csv_data), usecols = run_cols)
                total_km = float(run_df['Distance'].iloc[-1])
                segment = run_df.iloc[:-1]
                hr = segment['Avg HR']
                distance = segment['Distance']
                z34_sum = float(distance[(hr >= Z3_min) & (hr < Z5_min)].sum())
                z5_sum  = float(distance[hr >= Z5_min].sum())
                duration_seconds = _duration_to_seconds(str(run_df['Time'].iloc[-1]))
                pace_min_per_km = (duration_seconds / 60 / total_km) if total_km > 0 else None
                avg_hr = float(hr.mean()) if not hr.empty else None
                max_hr = float(hr.max()) if not hr.empty else None

                # Aggregate into per-day dict
                if activity_start_date not in run_by_date:
                    run_by_date[activity_start_date] = {'total_km': 0.0,'km_z34': 0.0,'km_z5plus': 0.0, 'nr. sessions': 0}
                run_by_date[activity_start_date]['total_km'] += total_km
                run_by_date[activity_start_date]['km_z34'] += z34_sum
                run_by_date[activity_start_date]['km_z5plus'] += z5_sum
                run_by_date[activity_start_date]['nr. sessions'] += 1

                if include_activity_records:
                    activity_records.append(
                        {
                            "activity_id": str(activity_id),
                            "date": activity_start_date,
                            "activity_type": str(activity_type).lower(),
                            "start_time_local": str(start_time_local),
                            "activity_name": str(activity_name),
                            "distance_km": total_km,
                            "duration_seconds": duration_seconds,
                            "pace_min_per_km": pace_min_per_km,
                            "avg_hr": avg_hr,
                            "max_hr": max_hr,
                            "km_z34": z34_sum,
                            "km_z5plus": z5_sum,
                        }
                    )
            else: 
                other_df = pd.read_csv(BytesIO(csv_data), usecols = other_cols)
                # Parse to hours and aggregate per-day
                time_str = other_df['Time'].iloc[-1]
                duration_seconds = _duration_to_seconds(str(time_str))
                time_delta = datetime.timedelta(seconds=duration_seconds)
                hours_alternative = round(time_delta.total_seconds() / 3600, 2)

                if activity_start_date not in other_by_date:
                    other_by_date[activity_start_date] = {'hours_alternative': 0.0,}
                other_by_date[activity_start_date]['hours_alternative'] += hours_alternative

                if include_activity_records:
                    activity_records.append(
                        {
                            "activity_id": str(activity_id),
                            "date": activity_start_date,
                            "activity_type": str(activity_type).lower(),
                            "start_time_local": str(start_time_local),
                            "activity_name": str(activity_name),
                            "duration_seconds": duration_seconds,
                            "hours_alternative": hours_alternative,
                        }
                    )
    except (
        GarminConnectConnectionError,
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError,
        requests.exceptions.HTTPError,
    ) as err:
        logger.error(f'error in get_activity_dataframes :{err}')
        if include_activity_records:
            return [], [], []
        return [], []

    # Convert aggregated maps to lists of single dicts per date
    run_daily: List[Dict] = [{'date': d, **vals} for d, vals in run_by_date.items()]
    other_daily: List[Dict] = [{'date': d, **vals} for d, vals in other_by_date.items()]
    if include_activity_records:
        return run_daily, other_daily, activity_records
    return run_daily, other_daily


def main_api_call(
    email: Optional[str] = None,
    password: Optional[str] = None,
    Z3_min: int = 135,
    Z5_min: int = 172,
    include_activity_records: bool = False,
) -> Any:
    """Main function to download Garmin Connect activities."""
    print("Garmin Connect API - Activity Downloader")

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=120)

    if not email or not password:
        logger.error("Email and password are required for authentication.")
        print("Email and password are required for authentication.")
        if include_activity_records:
            return None, None, [], [], []
        return None, None, [], []

    api = init_api(email, password)

    if not api:
        logger.error("Failed to initialize Garmin API. Exiting.")
        print("Failed to initialize Garmin API. Exiting.")
        if include_activity_records:
            return None, None, [], [], []
        return None, None, [], []

    if include_activity_records:
        runs, alt, activity_records = get_activities(
            api,
            start_date,
            end_date,
            Z3_min=Z3_min,
            Z5_min=Z5_min,
            include_activity_records=True,
        )
        return start_date, end_date, runs, alt, activity_records

    runs, alt = get_activities(
        api,
        start_date,
        end_date,
        Z3_min=Z3_min,
        Z5_min=Z5_min,
        include_activity_records=False,
    )

    return start_date, end_date, runs, alt

if __name__ == "__main__":
    email = os.getenv('EMAIL')
    password = os.getenv('PASSWORD')
    start_date ,end_date, runs, alt = main_api_call(email or "", password or "")
    print(runs)
