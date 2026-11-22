"""Shared check/book logic, plus a one-shot entry point (`python -m teebot.bot`).

The always-on server loop lives in runner.py and reuses these functions.

Env vars:
  CLUB_USERNAME, CLUB_PASSWORD         club login
  MAIL_WEBHOOK_URL, MAIL_SECRET        email relay (server/email-relay.gs); or
  GMAIL_USER, GMAIL_APP_PASSWORD       direct Gmail SMTP (not on cloud servers)
  HEALTHCHECK_URL                      optional healthchecks.io ping URL (runner only)
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


def load_cfg() -> dict:
    return load_json(ROOT / "config.json", None)


def load_state(now: datetime) -> dict:
    state = load_json(STATE, {"booked": {}})
    state.setdefault("booked", {})
    # Forget bookings in the past so the file stays small.
    state["booked"] = {d: v for d, v in state["booked"].items() if d >= now.date().isoformat()}
    return state


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE)


def is_dry() -> bool:
    return os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")


def now_local(cfg: dict) -> datetime:
    return datetime.now(ZoneInfo(cfg["timezone"]))


def check_dates(page, cfg: dict, state: dict, now: datetime, dry: bool, dates) -> list[str]:
    """Search each date; book the best qualifying slot. Returns short status strings.

    A date whose search fails is reported and skipped, so one bad date never stops the
    others from being checked. The furthest-out date is often not open for booking yet
    (the club releases it at some point that day), so failures there are just "not open
    yet". Raises only if every other date failed too (e.g. the session expired), so the
    caller can log in again and retry."""
    SHOTS.mkdir(exist_ok=True)
    start = datetime.strptime(cfg["window_start"], "%H:%M").strftime("%-I:%M %p")
    edge = max(dates) if dates else None
    out, tried, failed = [], 0, []
    for d in dates:
        if d.isoformat() in state["booked"]:
            continue  # booked earlier in this same cycle/run
        label = d.strftime("%a %b %-d")
        if d != edge:
            tried += 1
        try:
            site.open_tee_sheet(page, cfg["club_url"], d, start=start, players=cfg["players"])
            slots = site.list_slots(page, cfg["players"])
        except Exception as e:
            if d == edge:
                out.append(f"{label}: not open yet")
            else:
                failed.append(e)
                out.append(f"{label}: search failed ({str(e).splitlines()[0][:80]})")
            if not _reset_to_search(page, cfg):
                raise RuntimeError("Search page didn't come back after a failed search "
                                   "(session expired?)") from e
            continue
        choice = pick_slot(slots, d, now, cfg)
        if not choice:
            out.append(f"{label}: none ({len(slots)} later)")
            continue
        tt = choice.when.strftime("%-I:%M %p")
        if dry:
            out.append(f"{label}: WOULD BOOK {tt}")
            page.screenshot(path=str(SHOTS / f"dry-{d}.png"), full_page=True)
            continue
        try:
            confirmation = site.book(page, choice, cfg["players"], d)
        except site.BookingUnverified as e:
            # Don't risk a double booking: stop trying this date and ask you to check.
            state["booked"][d.isoformat()] = f"{tt} (UNVERIFIED)"
            save_state(state)
            _shot(page, f"unverified-{d}.png")
            send_email(f"❓ Please check: {label} at {tt}",
                       f"{e}\n\nPlease check My Reservations. The bot won't try {label} again.\n"
                       f"If it isn't booked, re-arm it on the server with:\n"
                       f"  sudo teebot-rearm {d.isoformat()}\n")
            out.append(f"{label}: UNVERIFIED {tt}")
            continue
        state["booked"][d.isoformat()] = tt
        save_state(state)  # save immediately
        _shot(page, f"booked-{d}.png")
        send_email(
            f"⛳ Booked: {label} at {tt}",
            f"Tee time booked for {cfg['players']} (you + TBD/guests).\n\n"
            f"Date: {d:%A, %B %-d, %Y}\nTime: {tt}\n\nConfirmation:\n{confirmation}\n",
        )
        out.append(f"{label}: BOOKED {tt}")
    if failed and len(failed) == tried:
        raise failed[0]
    return out


def _reset_to_search(page, cfg: dict) -> bool:
    """After a failed search, reload the search page so the next date starts clean.
    Returns False if the search form doesn't come back (e.g. we've been logged out)."""
    try:
        page.goto(cfg["club_url"], wait_until="domcontentloaded")
        page.locator("xpath=//*[normalize-space(text())='Date:']").first.wait_for(timeout=8000)
        return True
    except Exception:
        return False


def _shot(page, name: str) -> None:
    try:
        SHOTS.mkdir(exist_ok=True)
        page.screenshot(path=str(SHOTS / name), full_page=True)
    except Exception:
        pass


def report_error(state: dict, now: datetime, err: str, page=None) -> None:
    print(err, file=sys.stderr, flush=True)
    if page is not None:
        _shot(page, "error.png")
    # Email about errors at most once a day so a site change doesn't spam you.
    if state.get("last_error_email") != now.date().isoformat():
        state["last_error_email"] = now.date().isoformat()
        save_state(state)
        send_email("⚠️ Tee time bot error", f"The bot hit an error and will keep retrying.\n\n{err}")


def main() -> int:
    """One check of every target date (used for the installer's dry-run test)."""
    cfg = load_cfg()
    now = now_local(cfg)
    state = load_state(now)
    dry = is_dry()
    dates = target_dates(now, cfg, state["booked"])
    print(f"{now:%Y-%m-%d %H:%M %Z} | dry_run={dry} | watching: {[d.isoformat() for d in dates]}")
    if not dates:
        save_state(state)
        return 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        page = browser.new_page()
        try:
            page = site.login(page, cfg["club_url"], os.environ["CLUB_USERNAME"], os.environ["CLUB_PASSWORD"])
            for line in check_dates(page, cfg, state, now, dry, dates):
                print("  " + line)
        except Exception:
            report_error(state, now, traceback.format_exc(), page)
            return 1
        finally:
            browser.close()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
