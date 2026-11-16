# Tee Time Cancellation Bot

**The Federal Club · IBS WebRes · runs on your own server**

Stays logged in and checks the tee sheet every 60 seconds. When a time opens in your window, it books it and emails you.

| Setting | Value |
|---|---|
| Days | Saturday and Sunday |
| Time window | 7:00–11:00 AM (the club's search starts at 9:00, so effectively 9:00–11:00) |
| Group | Foursome: you + 3 TBD/guests |
| Limit | One Saturday and one Sunday time per weekend |
| Look-ahead | 7 days (the club's booking window) |
| Check interval | Every 60 seconds |
| Notifications | Email for every booking; at most one error email per day |

To change any of these, edit `config.json` on GitHub, then run `sudo teebot-update` on the server.

## How a booking happens

1. Log in at thefederalclub.com and click **Member Portal**. The bot stays logged in between checks.
2. Open **Browse Tee Times**, set the date, earliest time, 4 players and 18 holes, then click **Search**.
3. Click **Book** on the earliest time in the window.
4. Check that the date, time and 4 players match, then click **Finish Booking**.
5. Confirm the time appears in **My Reservations**, then email you.

**Safety:**
- **Never double-books.** If anything is unclear after Finish Booking, it parks that day and emails you to check.
- **Recovers on its own.** If the session expires, it logs in again.
- **Survives crashes and reboots.** If it crashes or the server reboots, it restarts automatically.

## Setup

1. **Email relay.** Cloud servers block normal email, so emails go through a small Google Apps Script in your Gmail account (`server/email-relay.gs`). At script.google.com, create a new project, paste the file, set `SECRET`, then **Deploy → New deployment → Web app** (Execute as: Me; Who has access: Anyone). Copy the web app URL.
2. **Optional "it stopped" alert.** At healthchecks.io, add a check (Period 5 min, Grace 10 min) and copy its ping URL.
3. **Server.** Create an Ubuntu 24.04 server (DigitalOcean, $6/mo, 1 GB).
4. **Install.** In the server's console, run:

   ```
   git clone https://github.com/hinklee17/teebot /opt/teebot && sudo bash /opt/teebot/server/setup.sh
   ```

5. Enter your club login, the email web app URL, the secret phrase and the optional healthchecks URL. The installer sends a test email, does a dry run, then goes live.

## Day to day (in the server console)

| Task | Command |
|---|---|
| Watch it work | `journalctl -u teebot -f` (Ctrl+C to stop watching) |
| Pause | `sudo systemctl stop teebot` |
| Resume | `sudo systemctl start teebot` |
| Let it book a day again | `sudo teebot-rearm 2026-11-21` |
| Get the latest code from GitHub | `sudo teebot-update` |
| Change logins or email settings | `sudo rm /etc/teebot.env && sudo teebot-update` |

## Where things live on the server

- **Code:** `/opt/teebot` (a copy of this repo)
- **Logins:** `/etc/teebot.env`, readable only by the server's admin (root)
- **Booking log:** `/opt/teebot/state.json`
- **Screenshots of each booking or error:** `/opt/teebot/screenshots/`
