import os
import tempfile
import time
from datetime import datetime

os.environ["REMINDER_DB"] = os.path.join(tempfile.mkdtemp(), "r.db")

from core import reminders


def ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").timestamp()


def test_once_future_and_past():
    after = ts("2026-11-28 10:00")
    assert reminders.compute_next("10:30", "2026-11-28", "", after) == ts("2026-11-28 10:30")
    assert reminders.compute_next("09:30", "2026-11-28", "", after) is None


def test_daily_rolls_to_tomorrow():
    after = ts("2026-11-28 10:00")
    assert reminders.compute_next("09:00", None, "0,1,2,3,4,5,6", after) == ts("2026-11-29 09:00")


def test_weekdays_skip_weekend():
    after = ts("2026-11-28 10:00")
    assert datetime.fromtimestamp(after).weekday() == 5
    assert reminders.compute_next("08:00", None, "0,1,2,3,4", after) == ts("2026-11-30 08:00")


def test_crud_and_validation():
    future = datetime.fromtimestamp(time.time() + 86400 * 2)
    item = reminders.create_reminder({"text": "吃藥", "time": "08:00", "date": future.date().isoformat()})
    assert item["enabled"] and item["next_at"]
    off = reminders.update_reminder(item["id"], {"enabled": False})
    assert off["next_at"] is None and not off["enabled"]
    daily = reminders.update_reminder(item["id"], {"enabled": True, "days": [0, 1, 2, 3, 4, 5, 6]})
    assert daily["date"] is None and daily["days"] == "0,1,2,3,4,5,6"
    for bad in ({"text": "", "time": "08:00", "days": [1]}, {"text": "x", "time": "25:00", "days": [1]}, {"text": "x", "time": "08:00"}):
        try:
            reminders.create_reminder(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert reminders.delete_reminder(item["id"])
    assert reminders.list_reminders() == []
