"""Pure date/time logic: which dates to watch and which slots qualify.

No browser or network code here, so it's easy to test.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_hhmm(s: str) -> time:
    h, m = s.strip().split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class Slot:
    when: time          # tee time
    open_spots: int     # how many player spots are free
    ref: object = None  # site-specific handle used to click/book it


def target_dates(now: datetime, cfg: dict, booked: dict) -> list[date]:
    """Weekend dates inside the look-ahead window that still need a booking."""
    wanted = {DAY_NAMES.index(d) for d in cfg["days"]}
    window_end = parse_hhmm(cfg["window_end"])
    out = []
    for i in range(cfg["days_ahead"] + 1):
        d = now.date() + timedelta(days=i)
        if d.weekday() not in wanted:
            continue
        if d.isoformat() in booked:
            continue  # already have a time that day
        if d == now.date() and now.time() >= window_end:
            continue  # today's window is over
        out.append(d)
    return out


def pick_slot(slots: list[Slot], d: date, now: datetime, cfg: dict) -> Slot | None:
    """Best qualifying slot: inside the window, enough spots, not in the past."""
    start, end = parse_hhmm(cfg["window_start"]), parse_hhmm(cfg["window_end"])
    ok = [
        s for s in slots
        if start <= s.when <= end
        and s.open_spots >= cfg["players"]
        and not (d == now.date() and s.when <= now.time())
    ]
    if not ok:
        return None
    ok.sort(key=lambda s: s.when, reverse=(cfg.get("prefer") == "latest"))
    return ok[0]
