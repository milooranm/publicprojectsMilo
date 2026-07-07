import pytest
import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv


from Render.apicall_input import init_api, get_activities 
load_dotenv()

# the input of this function is ones email and password, plus start and end dates, plus hr zones
# the output is two lists of dictionaries, one for runs and one for other activities
# okay, so what I see here is that it's creating a new line in the dict every time and not adding to 
# the previous one, not sure how to stop. also note that the matching isn't working. maybe write a pytest for it?


def test_init_api():
    email = os.getenv('EMAIL')
    password = os.getenv('PASSWORD')
    api = init_api(email, password)
    assert api is not None

def test_get_activities_format():
    email = os.getenv('EMAIL')
    password = os.getenv('PASSWORD')
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    Z3_min = 135
    Z5_min = 172
    api = init_api(email, password)
    runs, alt = get_activities(api, start_date, end_date, Z3_min, Z5_min)
    assert isinstance(runs, list)
    assert isinstance(alt, list)

def test_get_activities_content():
    email = os.getenv('EMAIL')
    password = os.getenv('PASSWORD')
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    Z3_min = 135
    Z5_min = 172
    api = init_api(email, password)
    runs, alt = get_activities(api, start_date, end_date, Z3_min, Z5_min)
    for run in runs:
        assert 'date'in run
        assert 'total_km' in run
        assert 'km_z34' in run
        assert 'km_z5plus' in run
        assert isinstance(run, dict)
        #for date_key, data in run.items():
        #    assert isinstance(date_key, str)
        #    assert 'hours_in_Z3' in data
        #    assert 'hours_in_Z5' in data
    for activity in alt:
        assert 'date' in activity
        assert 'hours_alternative' in activity
        assert isinstance(activity, dict)
        
    #    for date_key, data in activity.items():
    #        assert isinstance(date_key, str)
    #        assert 'hours_alternative' in data


class _FakeAPI:
    class ActivityDownloadFormat:
        CSV = "csv"

    def get_activities_by_date(self, start, end):
        return [
            {
                "startTimeLocal": "2025-12-10 07:30:00",
                "activityType": {"typeKey": "running"},
                "activityId": 123,
                "activityName": "Morning Run",
            }
        ]

    def download_activity(self, activity_id, dl_fmt=None):
        # Missing "Avg HR" header on purpose to cover malformed schema behavior.
        return b"Distance,Time\n1.0,00:05:00\n2.0,00:10:00\n"


def test_get_activities_malformed_running_csv_schema_raises_value_error():
    api = _FakeAPI()
    with pytest.raises(ValueError):
        get_activities(api, date(2025, 12, 1), date(2025, 12, 10), 135, 172)