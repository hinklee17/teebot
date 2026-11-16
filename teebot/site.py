"""IBS WebRes site adapter -- the ONLY file that knows the club website's layout.

Flow (confirmed from screenshots):
  thefederalclub.com/members-only-login -> LOG IN -> Member Portal
  -> goibsvision.com .../Browse: Date (calendar), Time, Players, Holes -> Search
  -> results (time + Book) -> Book -> Enter Details (/ReservationDetails) -> Finish Booking
"""
from __future__ import annotations

import re
from datetime import date, datetime

from playwright.sync_api import Page

from .schedule import Slot

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*([AP]M)?\b", re.I)


LOGIN_URL = "https://thefederalclub.com/members-only-login/"


def login(page: Page, base_url: str, username: str, password: str) -> Page:
    """Log in on the club website (WordPress-style form, confirmed from screenshot):
    'Username or Email Address', 'Password', 'Remember Me', 'LOG IN'.
    """
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    user = page.get_by_label(re.compile(r"Username or Email", re.I)).or_(page.locator("#user_login")).first
    pw = page.get_by_label(re.compile(r"^Password", re.I)).or_(page.locator("#user_pass")).first
    user.fill(username)
    pw.fill(password)
    page.get_by_role("button", name=re.compile(r"log ?in", re.I)).or_(page.locator("#wp-submit")).first.click()
    page.wait_for_load_state("networkidle")
    if page.locator("#login_error, .login-error, .wp-login-error").count() or \
       page.get_by_text(re.compile(r"incorrect|unknown (user|email)|error:", re.I)).count():
        raise RuntimeError("Club login rejected -- check CLUB_USERNAME / CLUB_PASSWORD")
    return go_to_tee_times(page, base_url)


def go_to_tee_times(page: Page, base_url: str) -> Page:
    """Confirmed: after login the club page shows a 'Member Portal' button, which hands
    the login over to IBS WebRes. It may open in a new tab, so return whichever page we end on.
    """
    portal = page.get_by_role("link", name=re.compile(r"Member Portal", re.I)).or_(
        page.get_by_text("Member Portal", exact=True)).first
    portal.wait_for(timeout=15000)
    try:
        with page.context.expect_page(timeout=5000) as new_tab:
            portal.click()
        page = new_tab.value
    except Exception:
        pass  # opened in the same tab
    page.wait_for_load_state("networkidle")
    if "/Browse" not in page.url:
        nav = page.get_by_role("link", name="Browse Tee Times").first
        if nav.count():
            nav.click()
            page.wait_for_load_state("networkidle")
        else:
            page.goto(base_url, wait_until="networkidle")
    if not page.get_by_text("Browse Tee Times").count() or not page.get_by_role("button", name="Search").or_(
            page.get_by_text("Search", exact=True)).count():
        raise RuntimeError(f"Not on the tee sheet after Member Portal (landed on {page.url})")
    return page


def _choose(page: Page, label_text: str, chooser) -> str:
    """Pick an option in the dropdown after a label like 'Time:'.

    `chooser` gets the list of option texts and returns the one to pick (or a plain string).
    The site's dropdowns are styled widgets (confirmed for Time); many such widgets keep a
    hidden native <select> underneath, so try that first, then click through the widget.
    """
    pick = chooser if callable(chooser) else (lambda opts, c=chooser: c)
    label = page.locator(f"xpath=//*[normalize-space(text())='{label_text}']").first
    sel = label.locator("xpath=following::select[1]")
    widget = label.locator("xpath=following::*[self::button or self::a or self::span or self::div]"
                           "[normalize-space(.)!=''][1]")
    if sel.count():
        opts = [o.strip() for o in sel.locator("option").all_inner_texts()]
        choice = pick(opts)
        sel.select_option(label=choice, force=True)
        # keep a styled widget's display in sync if it reads the select on change
        sel.evaluate("el => el.dispatchEvent(new Event('change', {bubbles: true}))")
        return choice
    widget.click()
    items = page.get_by_role("option").or_(page.locator("li:visible"))
    opts = [t.strip() for t in items.all_inner_texts() if t.strip()]
    choice = pick(opts)
    items.filter(has_text=re.compile(rf"^\s*{re.escape(choice)}\s*$")).first.click()
    return choice


def _earliest_time_at_or_before(start: str):
    """Chooser: latest option <= start (e.g. 7:00 AM); if none, the earliest option."""
    target = _parse_time(start)

    def choose(opts):
        timed = [(t, o) for o in opts if (t := _parse_time(o))]
        if not timed:
            raise RuntimeError(f"No times in Time dropdown: {opts[:5]}")
        before = [x for x in timed if x[0] <= target]
        return (max(before) if before else min(timed))[1]
    return choose


MONTH_RE = re.compile(r"^(January|February|March|April|May|June|July|August|September|"
                      r"October|November|December) \d{4}$")


def _type_date(date_input, date_text: str) -> None:
    date_input.evaluate(
        """(el, v) => { el.removeAttribute('readonly'); el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true})); }""", date_text)
    date_input.press("Tab")


def _pick_date(page: Page, d: date, date_text: str) -> None:
    """Date box (default = today) with a calendar button.
    Typing the date is what works on the real site (confirmed in the GitHub dry run),
    so do that first; only fall back to clicking the calendar if the typed value doesn't stick.
    The results header ('Showing N results for <date>') is checked afterwards either way.
    """
    date_input = page.locator(
        "xpath=//*[normalize-space(text())='Date:']/following::input[1]").first
    if date_input.input_value().strip() == date_text:
        return
    _type_date(date_input, date_text)
    if date_input.input_value().strip() == date_text:
        return
    print("  typed date didn't stick; trying the calendar")
    try:
        btn = date_input.locator(
            "xpath=following::*[self::a or self::button or self::span or self::img]"
            "[contains(translate(@class,'CALENDRICONPKT','calendricon pkt'),'calendar') or "
            "contains(@class,'icon') or contains(@class,'picker') or contains(@class,'select') or "
            "contains(@title,'alendar') or contains(@aria-label,'alendar')][1]")
        (btn if btn.count() else date_input).click()
        header = page.get_by_text(MONTH_RE).locator("visible=true").first
        header.wait_for(timeout=5000)
        for _ in range(2):  # at most one month forward (7-day window)
            if header.inner_text().strip() == f"{d:%B %Y}":
                break
            header.locator("xpath=following::*[self::a or self::button or self::span][1]").click()
            page.wait_for_timeout(300)
        grid = header.locator("xpath=ancestor::*[.//*[normalize-space(text())='Su']][1]")
        cells = grid.get_by_text(str(d.day), exact=True)
        (cells.last if d.day >= 15 else cells.first).click()  # avoid spill-over days
        page.wait_for_timeout(500)
    except Exception as e:
        raise RuntimeError(f"Couldn't set the date to {date_text} ({e.__class__.__name__})") from e


def open_tee_sheet(page: Page, base_url: str, d: date, start: str = "7:00 AM",
                   players: int = 4, holes: int = 18) -> None:
    """Fill the Browse Tee Times search form (Date / Time / Players / Holes) and Search.

    Confirmed from screenshot: URL stays /Browse; results only list times that fit
    the chosen player count, starting at the chosen time, earliest first.
    """
    if "/Browse" not in page.url:
        nav = page.get_by_role("link", name="Browse Tee Times").first
        if nav.count():
            nav.click()
            page.wait_for_load_state("networkidle")
        else:
            page.goto(base_url, wait_until="domcontentloaded")
    date_text = f"{d:%b} {d.day}, {d.year}"  # site format: "Nov 22, 2026"
    try:
        page.locator("xpath=//*[normalize-space(text())='Date:']").first.wait_for(timeout=8000)
    except Exception:
        raise RuntimeError(f"Tee sheet search form not found (session expired?) at {page.url}")
    _pick_date(page, d, date_text)
    picked = _choose(page, "Time:", _earliest_time_at_or_before(start))
    print(f"  search {date_text} from {picked}")
    _choose(page, "Players:", str(players))
    _choose(page, "Holes:", str(holes))
    page.get_by_role("button", name="Search").or_(page.get_by_text("Search", exact=True)).first.click()
    page.wait_for_load_state("networkidle")
    _wait_for_results(page, date_text)


def _wait_for_results(page: Page, date_text: str, timeout_s: float = 10) -> None:
    """Wait until the results header names THIS date (not a stale header from the previous
    search), or a 'no tee times' style message appears. If neither shows up but the date box
    holds the right date and there are no Book buttons, treat it as zero results."""
    import time
    ok = page.get_by_text(re.compile(rf"Showing \d+ results? for {re.escape(date_text)}", re.I))
    none_msg = page.get_by_text(re.compile(
        r"\b(no|0) (results|tee ?times|times)|nothing (is )?available|no availability", re.I))
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if ok.count() or none_msg.count():
            return
        page.wait_for_timeout(500)
    date_input = page.locator("xpath=//*[normalize-space(text())='Date:']/following::input[1]").first
    books = page.get_by_role("button", name="Book", exact=True).or_(
        page.get_by_role("link", name="Book", exact=True))
    if date_input.count() and date_input.input_value().strip() == date_text and books.count() == 0:
        print(f"  no results header for {date_text}; treating as 0 open times")
        return
    raise RuntimeError(f"Search results for {date_text} didn't load")


def _parse_time(text: str):
    m = TIME_RE.search(text)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return datetime.strptime(f"{h}:{mi:02d}", "%H:%M").time()


def list_slots(page: Page, players: int = 4) -> list[Slot]:
    """Each result card = facility name, time (e.g. '1:20 PM'), 'Players: You + 3', Book button.

    The search already filtered to times that fit `players`, so every card qualifies.
    """
    slots = []
    book_buttons = page.get_by_role("button", name="Book", exact=True).or_(
        page.get_by_role("link", name="Book", exact=True))
    for btn in book_buttons.all():
        card = btn.locator("xpath=ancestor::*[contains(., 'Players:')][1]")
        t = _parse_time(card.inner_text())
        if t:
            slots.append(Slot(when=t, open_spots=players, ref=btn))
    return slots


class BookingUnverified(Exception):
    """Finish Booking was clicked but the reservation couldn't be confirmed."""


def book(page: Page, slot: Slot, players: int, d: date) -> str:
    """Confirmed flow: Book -> 'Enter Details' page (/ReservationDetails, 3-minute timer,
    you + '(Player 2..4)' placeholders = TBD) -> 'Finish Booking'.
    Returns confirmation text; raises BookingUnverified if the outcome is unclear.
    """
    date_text = f"{d:%b} {d.day}, {d.year}"
    time_text = slot.when.strftime("%-I:%M %p")

    slot.ref.click()
    page.get_by_text("Enter Details").first.wait_for(timeout=20000)
    details = page.locator("body").inner_text()
    # Safety: make sure we're about to book exactly what we meant to.
    for want in (date_text, time_text, f"Player(s): {players}"):
        if want not in details:
            raise RuntimeError(f"Details page mismatch: expected '{want}'. Not booking.")

    page.get_by_role("button", name="Finish Booking").or_(
        page.get_by_role("link", name="Finish Booking")).first.click()

    # From here on the booking may have gone through, so any surprise is treated as
    # "unverified" (date gets parked + you get a please-check email) -- never retried.
    try:
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        after_text = page.locator("body").inner_text()
        refused = re.search(r"error|unable|not available|no longer|expired", after_text, re.I) \
            and "Finish Booking" in after_text
    except Exception as e:
        raise BookingUnverified(f"Clicked Finish Booking for {date_text} {time_text}, then: {e}") from e
    if refused:
        # Still on the details page with an error message: definitely not booked.
        raise RuntimeError(f"Site refused booking: {after_text[:300]}")

    try:
        page.get_by_role("link", name="My Reservations").first.click()
        page.wait_for_load_state("networkidle")
        res_text = page.locator("body").inner_text()
    except Exception as e:
        raise BookingUnverified(
            f"Clicked Finish Booking for {date_text} {time_text}, but couldn't open My Reservations: {e}") from e
    if date_text in res_text and time_text in res_text:
        return f"Verified in My Reservations: {date_text} {time_text}.\n\nPage after booking:\n{after_text[:800]}"
    raise BookingUnverified(
        f"Clicked Finish Booking for {date_text} {time_text}, but couldn't find it in My Reservations.")
