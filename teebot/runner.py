"""Always-on server loop: log in once, re-check every INTERVAL seconds.

  python -m teebot.runner

- Keeps one browser session logged in (gentle on the club site, ~seconds per check).
- If a check fails (e.g. the session expired), starts a fresh browser, logs in again
  and retries once in the same cycle.
- Restarts the browser every few hours to keep memory in check.
- Pings HEALTHCHECK_URL (e.g. healthchecks.io) after every good cycle, so you're
  emailed if the bot ever goes silent. Pings <url>/fail on errors.
- Re-reads config.json every cycle, so edits take effect without a restart.
"""
from __future__ import annotations

import os
import random
import signal
import sys
import time
import traceback
import urllib.request

from . import site
from .bot import check_dates, is_dry, load_cfg, load_state, now_local, report_error, save_state
from .schedule import target_dates

INTERVAL = int(os.environ.get("INTERVAL", "60"))
BROWSER_MAX_AGE = 6 * 3600
MAX_BACKOFF = 15 * 60

_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True


def ping(suffix: str = "") -> None:
    url = os.environ.get("HEALTHCHECK_URL", "").strip()
    if not url:
        return
    try:
        urllib.request.urlopen(url.rstrip("/") + suffix, timeout=10).read()
    except Exception as e:
        print(f"healthcheck ping failed: {e}", flush=True)


def log(msg: str) -> None:
    print(msg, flush=True)


class Session:
    """One browser + logged-in page, recreated on demand."""

    def __init__(self, pw):
        self.pw = pw
        self.browser = None
        self.page = None
        self.started = 0.0

    def close(self):
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        self.browser = self.page = None

    def fresh(self, cfg):
        self.close()
        self.browser = self.pw.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        self.started = time.monotonic()
        page = self.browser.new_page()
        page.set_default_timeout(15000)
        self.page = site.login(page, cfg["club_url"], os.environ["CLUB_USERNAME"], os.environ["CLUB_PASSWORD"])
        log("  logged in")

    def ensure(self, cfg):
        if self.page is None or time.monotonic() - self.started > BROWSER_MAX_AGE:
            self.fresh(cfg)


def cycle(sess: Session) -> str:
    cfg = load_cfg()
    now = now_local(cfg)
    state = load_state(now)
    dry = is_dry()
    dates = target_dates(now, cfg, state["booked"])
    if not dates:
        sess.close()  # nothing to watch right now; free the memory
        save_state(state)
        return f"{now:%a %H:%M} | all target days booked"
    try:
        sess.ensure(cfg)
        results = check_dates(sess.page, cfg, state, now, dry, dates)
    except site.BookingUnverified:
        raise
    except Exception as first:
        log(f"  check failed ({first.__class__.__name__}); logging in again and retrying")
        sess.fresh(cfg)
        results = check_dates(sess.page, cfg, state, now, dry, dates)
    save_state(state)
    return f"{now:%a %H:%M} | {'DRY | ' if dry else ''}" + " | ".join(results)


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    from playwright.sync_api import sync_playwright

    log(f"teebot runner starting: every {INTERVAL}s, dry_run={is_dry()}")
    fails = 0
    with sync_playwright() as pw:
        sess = Session(pw)
        while not _stop:
            t0 = time.monotonic()
            try:
                log(cycle(sess))
                fails = 0
                ping()
            except Exception:
                fails += 1
                err = traceback.format_exc()
                try:
                    cfg = load_cfg()
                    now = now_local(cfg)
                    report_error(load_state(now), now, err, sess.page)
                except Exception:
                    print(err, file=sys.stderr, flush=True)
                ping("/fail")
                sess.close()
            # Wait for the next cycle (back off after repeated failures), with a little jitter.
            wait = INTERVAL if fails == 0 else min(INTERVAL * 2 ** fails, MAX_BACKOFF)
            wait = max(5, wait - (time.monotonic() - t0)) + random.uniform(0, 5)
            end = time.monotonic() + wait
            while not _stop and time.monotonic() < end:
                time.sleep(1)
        sess.close()
    log("teebot runner stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
