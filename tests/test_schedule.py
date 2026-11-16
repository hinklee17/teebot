from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from teebot.schedule import Slot, pick_slot, target_dates

CFG = {"days": ["Saturday", "Sunday"], "window_start": "07:00", "window_end": "11:00",
       "players": 4, "days_ahead": 7, "prefer": "earliest"}
TZ = ZoneInfo("America/New_York")


def test_targets_two_weekends_skip_booked():
    now = datetime(2026, 11, 16, 15, 0, tzinfo=TZ)  # Monday
    got = target_dates(now, CFG, {"2026-11-21": "7:40 AM"})
    assert got == [date(2026, 11, 22), ]


def test_today_skipped_after_window():
    now = datetime(2026, 11, 21, 11, 30, tzinfo=TZ)  # Saturday, late
    assert date(2026, 11, 21) not in target_dates(now, CFG, {})


def test_pick_earliest_valid():
    now = datetime(2026, 11, 16, 15, 0, tzinfo=TZ)
    d = date(2026, 11, 21)
    slots = [Slot(time(6, 50), 4), Slot(time(9, 0), 4), Slot(time(8, 0), 3),
             Slot(time(8, 30), 4), Slot(time(11, 10), 4)]
    assert pick_slot(slots, d, now, CFG).when == time(8, 30)


def test_no_past_slots_today():
    now = datetime(2026, 11, 21, 8, 0, tzinfo=TZ)
    slots = [Slot(time(7, 30), 4), Slot(time(9, 0), 4)]
    assert pick_slot(slots, date(2026, 11, 21), now, CFG).when == time(9, 0)


def test_none_when_full():
    now = datetime(2026, 11, 16, 15, 0, tzinfo=TZ)
    assert pick_slot([Slot(time(8, 0), 2)], date(2026, 11, 21), now, CFG) is None
