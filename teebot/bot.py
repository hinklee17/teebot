"""Tee time cancellation watcher. One run = one check of every target date.

Env vars:
  CLUB_USERNAME, CLUB_PASSWORD         club login (GitHub Secrets)
  GMAIL_USER, GMAIL_APP_PASSWORD       sender for notifications
  NOTIFY_TO                            where confirmations go
  DRY_RUN=1                            find and report, never book
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import site
from .notify import send_email
from .schedule import pick_slot, target_dates

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
SHOTS = ROOT / "screenshots"


def load_json(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def main() -> int:
    cfg = load_json(ROOT / "config.json", None)
    state = load_json(STATE, {"booked": {}})
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    dry = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    # Forget bookings in the past so the file stays small.
    state["booked"] = {d: v for d, v in state["booked"].items() if d >= now.date().isoformat()}

    # Weekly heartbeat commit keeps GitHub from disabling the schedule after 60 idle days.
    week = now.strftime("%G-W%V")
    state["heartbeat"] = week

    dates = target_dates(now, cfg, state["booked"])
    print(f"{now:%Y-%m-%d %H:%M %Z} | dry_run={dry} | watching: {[d.isoformat() for d in dates]}")
    if not dates:
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        return 0

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        page = browser.new_page()
        try:
            page = site.login(page,cfg["club_url"], os.environ["CLUB_USERNAME"], os.environ["CLUB_PASSWORD"])
            for d in dates:
                start = datetime.strptime(cfg["window_start"], "%H:%M").strftime("%-I:%M %p")
                site.open_tee_sheet(page, cfg["club_url"], d, start=start, players=cfg["players"])
                slots = site.list_slots(page, cfg["players"])
                choice = pick_slot(slots, d, now, cfg)
                label = d.strftime("%a %b %-d")
                if not choice:
                    print(f"  {label}: nothing open in window ({len(slots)} slots seen)")
                    continue
                tt = choice.when.strftime("%-I:%M %p")
                if dry:
                    print(f"  {label}: WOULD BOOK {tt}")
                    page.screenshot(path=str(SHOTS / f"dry-{d}.png"), full_page=True)
                    continue
                try:
                    confirmation = site.book(page, choice, cfg["players"], d)
                except site.BookingUnverified as e:
                    # Don't risk a double booking: stop trying this date and ask you to check.
                    state["booked"][d.isoformat()] = f"{tt} (UNVERIFIED)"
                    STATE.write_text(json.dumps(state, indent=2) + "\n")
                    page.screenshot(path=str(SHOTS / f"unverified-{d}.png"), full_page=True)
                    send_email(f"❓ Please check: {label} at {tt}",
                               f"{e}\n\nPlease check My Reservations. The bot won't try {label} again. "
                               f"If it isn't booked, delete the {d.isoformat()} line from state.json to re-arm.")
                    continue
                state["booked"][d.isoformat()] = tt
                STATE.write_text(json.dumps(state, indent=2) + "\n")  # save immediately
                page.screenshot(path=str(SHOTS / f"booked-{d}.png"), full_page=True)
                send_email(
                    f"⛳ Booked: {label} at {tt}",
                    f"Tee time booked for {cfg['players']} (you + TBD/guests).\n\n"
                    f"Date: {d:%A, %B %-d, %Y}\nTime: {tt}\n\nConfirmation:\n{confirmation}\n",
                )
        except Exception:
            err = traceback.format_exc()
            print(err, file=sys.stderr)
            try:
                page.screenshot(path=str(SHOTS / "error.png"), full_page=True)
            except Exception:
                pass
            # Email about errors at most once a day so a site change doesn't spam you.
            if state.get("last_error_email") != now.date().isoformat():
                state["last_error_email"] = now.date().isoformat()
                send_email("⚠️ Tee time bot error", f"The bot hit an error and will keep retrying.\n\n{err}")
            STATE.write_text(json.dumps(state, indent=2) + "\n")
            return 1
        finally:
            browser.close()

    STATE.write_text(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
