# Runbook: setting up, testing, and drilling the system

## A. First deployment (about one evening)

1. **VPS + domain.** Any small Linux VPS (Hetzner CX22, DigitalOcean, or an Indian provider for lower latency; ~Rs 400-800/month). Point `alert.<yourdomain>` at it.
2. **Secrets.** On the VPS:
   ```bash
   git clone <this repo> && cd personal/hub
   cp config.example.yaml config.yaml          # fill in people, location, hospitals
   cat > .env <<EOF
   HUB_DEVICE_TOKEN=$(openssl rand -hex 24)
   HUB_RESPONDER_TOKEN=$(openssl rand -hex 24)
   PUSHOVER_APP_TOKEN=...
   PUSHOVER_MAITRABH=...
   TELEGRAM_BOT_TOKEN=...
   SMSGATE_USER=... SMSGATE_PASS=...
   EOF
   sed -i 's/alert.example.com/alert.yourdomain.in/' Caddyfile
   docker compose up -d --build
   curl https://alert.yourdomain.in/healthz
   ```
3. **Pushover.** Create an application at pushover.net (that is `PUSHOVER_APP_TOKEN`). Each family member installs the app, pays the one-time licence, sends you their user key. In the app: Settings, allow "Emergency" priority to bypass DND; on Android also exclude Pushover from battery optimisation.
4. **ntfy.** Family on Android installs ntfy (F-Droid build for the foreground "instant delivery" service), subscribes to their random topic, and in the topic settings enables "Override Do Not Disturb" for max priority and "Keep alerting".
5. **Kiosk phones.** On each old phone: install Fully Kiosk Browser, set start URL to `https://alert.yourdomain.in/kiosk?device=mom-room-phone&token=<HUB_DEVICE_TOKEN>` (the token is remembered, then change the start URL to plain `/kiosk`). Enable keep-screen-on, kiosk mode, auto-restart, and limit charging to 80% if the phone supports it. Put it on a stand at the bedside, on a charger.
6. **Run a test:**
   ```bash
   curl -X POST https://alert.yourdomain.in/api/v1/alert \
     -H "Authorization: Bearer $HUB_DEVICE_TOKEN" -H "content-type: application/json" \
     -d '{"device_id":"mom-room-phone","kind":"test"}'
   ```
   Everyone in the ladder should get a "[TEST]" push + SMS with a link. Open the link, tap "On my way", confirm the others see it, tap "Resolved".
7. **Watchdog check:** unplug a kiosk phone's Wi-Fi for 10 minutes; admins must receive "OFFLINE".
8. **Monitoring the monitor:** add `https://alert.yourdomain.in/healthz` to a free Uptime Kuma / Healthchecks.io / UptimeRobot with a push notification to you.

## B. Weekly (automated, Sunday 11:00)

A cron on the VPS sends a test alert from one device to `test_contacts` only:
```
0 11 * * 0  curl -s -X POST https://alert.yourdomain.in/api/v1/alert -H "Authorization: Bearer $HUB_DEVICE_TOKEN" -H "content-type: application/json" -d '{"device_id":"mom-room-button","kind":"test"}'
```
If you do not get it, something is broken. Fix it that day.

Also weekly: glance at `GET /api/v1/status?t=<responder token>` (all devices `online: true`, kiosk battery sane), check the router UPS charge LED, check the oxygen cylinder gauge.

## C. Monthly live drill (15 minutes, everybody)

1. Tell everyone the day before: "Drill on Saturday 6 pm."
2. A parent presses the real button (kind panic). Do **not** use test mode; the point is the voice calls and the lights.
3. Measure: seconds to first "On my way"; minutes to first "Arrived"; did every phone ring loudly; did the lights come on; did the porch flash.
4. Neighbour walks the route to the bedroom, finds the red folder, reads the oximeter, finds the oxygen. Time it.
5. Resolve with a note "DRILL". Fix whatever was slow. Rotate which neighbour is "first".

## D. Quarterly

- Re-check both hospitals still have 24x7 CT / cath lab; update phone numbers in `config.yaml`.
- Refresh the one-page medical summaries and the medicine strips in the red folder.
- Test-call 112 and 108 from the house landline and a mobile; note the response.
- Replace the kiosk phone if the battery has swollen; replace the UPS battery every 2-3 years.
- Rotate `HUB_RESPONDER_TOKEN` if the link has been forwarded outside the family (old links stop working).

## E. When a real incident happens: after-action

Within a day, while it is fresh: what worked, what was slow, which message was confusing, which playbook step was missing. Edit `playbooks.yaml` and `config.yaml` accordingly. The incident's full delivery log is at `GET /api/v1/incidents/<id>?t=...`.

## F. Operational notes

- **Never let the hub become the only path.** The A7670C modem fallback and the "call 112" text on the kiosk exist for the day the VPS is down.
- **Tokens:** `device_token` lives on the buttons and kiosk phones; `responder_token` is in every alert link. Both are 48 hex chars. Keep them out of git.
- **Logs:** `docker compose logs -f hub`. Every delivery attempt is also in SQLite (`deliveries` table) with the provider's response.
- **Backups:** `docker cp` the `/data/hub.sqlite3` volume weekly; it is small.
- **Upgrading:** `git pull && docker compose up -d --build`. Open incidents survive.
