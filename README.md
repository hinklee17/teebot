# Tee Time Cancellation Bot

**The Federal Club · IBS WebRes**

Checks the tee sheet about every 5 minutes and books cancellations in your window.

| Setting | Value |
|---|---|
| Days | Saturday and Sunday |
| Time window | 7:00–11:00 AM (earliest open time wins) |
| Group | Foursome: you + 3 TBD/guests |
| Limit | One Saturday and one Sunday time per weekend |
| Look-ahead | 7 days (the club's booking window) |
| Notification | Email after every booking |

To change any of these, edit `config.json`.

## How a booking happens

1. Log in at thefederalclub.com and click **Member Portal**.
2. Open **Browse Tee Times** and pick the date on the calendar.
3. Set the earliest Time, 4 players and 18 holes, then click **Search**.
4. Click **Book** on the earliest time from 7:00 to 11:00.
5. Check that the date, time and 4 players match, then click **Finish Booking**.
6. Confirm the time appears in **My Reservations**.

Players 2–4 stay as TBD placeholders.

> **Tip:** Do a dry run first (Setup, step 5). It shows exactly what the bot *would* book on the real site before it's allowed to book anything.

## Setup

One-time setup, about 15 minutes.

1. **Create a public GitHub repo** and upload these files.

2. **Create a Gmail App Password.** In the Google account for hinklehomesllc@gmail.com, turn on 2-Step Verification, then go to *Security → App passwords* and create one named `teebot`.

3. **Add secrets.** Go to *Repo → Settings → Secrets and variables → Actions → Secrets* and add:

   | Secret | Value |
   |---|---|
   | `CLUB_USERNAME` | Your club login |
   | `CLUB_PASSWORD` | Your club password |
   | `GMAIL_USER` | hinklehomesllc@gmail.com |
   | `GMAIL_APP_PASSWORD` | The 16-character app password |
   | `NOTIFY_TO` | hinklehomesllc@gmail.com |

4. **Add a variable.** On the same page, open the *Variables* tab and add `DRY_RUN` = `true`.

5. **Do a dry run.** Go to *Actions → Tee time watcher → Run workflow* and leave "dry run" checked. Open the run log to see what it *would* book. Screenshots are attached to the run.

6. **Go live.** Once the dry run looks right, change the `DRY_RUN` variable to `false`. Scheduled runs will then book for real.

## Day to day

- **Booking log:** bookings are recorded in `state.json`. To let the bot book a date again (for example, after you cancel a time), delete that date's line.
- **Pause:** go to *Actions → Tee time watcher → ⋯ → Disable workflow*.
- **"Please check" email:** sent if the bot clicked Finish Booking but couldn't find the time in My Reservations. It stops trying that day so it can't double-book. If the time isn't there, delete that date's line from `state.json` to re-arm it.
- **Errors:** if the club site changes, you'll get at most one error email per day, and the bot keeps retrying.
- **Timing:** GitHub often runs scheduled jobs 5–15 minutes late. A weekly heartbeat commit to `state.json` keeps GitHub from switching the schedule off after 60 days.
