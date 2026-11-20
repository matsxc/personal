# Handoff: Home Emergency Alert System

Written 20 November 2026 from a fresh read of the project folder and its git history, not from memory alone.

## 1. What this project is and why it exists

Maitrabh's elderly parents live alone in a secluded house in India, far from their children. The mother is diabetic and the father has high blood pressure. After a recent death in the family, the goal was a system where either parent can press one button when they feel unwell. That press should:

- wake the right people loudly, even at 2 a.m.;
- tell them where to go and what to do;
- keep calling people until someone has actually arrived at the house.

The people involved are Maitrabh, his brother, the other parent, a driver about 8 minutes away, two neighbours and a doctor in the housing society. An ambulance can take 30 to 60 minutes to reach the house.

## 2. What was done, what is finished, what is not

**Finished, and in the repository:**

- **A full written design.** It covers the people, the buttons, the server, the alert channels, what happens when something fails, the build phases and the budget.
- **Medical guidance for the family.** For 12 emergencies it gives the warning signs, what to do in the first 10 minutes and what not to do. The 12 are heart attack, stroke, low sugar, high sugar, very high blood pressure, falls, breathing difficulty, choking, cardiac arrest, sepsis, heat stroke and fainting. It also covers home oxygen rules, how the 112 and 108 emergency numbers work, a go-bag checklist, CPR, and medicine mistakes to avoid. Sources are cited.
- **Research notes.** One set covers which phone alerts and SMS or voice services actually work in India. The other covers the open-source projects reviewed.
- **The alert server ("hub").** This is working software. It receives a button press and sends alerts to everyone. It phones people at set intervals until someone replies "On my way". It shows each responder a web page with call buttons and the medical guidance. It warns the family when a button stops reporting in, and it picks up open emergencies again after a restart.
- **Automated tests for the hub.** All 7 pass. They were last run on 20 Nov 2026 in this session.
- **A one-big-button web page** for repurposing old phones as bedside panic buttons.
- **Code for the wall button.** It runs on an ESP32 chip, a small Wi-Fi board, and comes with a parts list and wiring guide.
- **Home Assistant rules.** Home Assistant is home-automation software. These rules turn the lights on, flash the porch light, sound a siren and make a spoken announcement in the hall.
- **A runbook.** It covers deployment, the weekly test, the monthly drill and the quarterly checks.

**Not finished:**

- **No real details have been entered.** The configuration still has placeholder values for the address, people, phone numbers, hospitals and secret keys. The list of what is needed is in `docs/INFO_NEEDED.md`.
- **Nothing is deployed.** No server has been rented, no web address set up and no Pushover account created. Pushover is the phone-siren app the design uses.
- **The wall-button code has never been compiled or run on a real board.**
- **No hospitals have been researched yet.** This needs the house location.
- **The parents' medical reports have not been reviewed,** and no oxygen run-time card has been made. The concentrator and cylinder details were never shared.
- **No pull request has been opened.** The work lives only on its own branch.

## 3. Decisions made, with reasons

| Decision | Reason |
|---|---|
| The hub runs on a small rented cloud server, not inside the house | A power cut or broadband outage at the house cannot take it down. |
| Pushover is the main phone siren | It is the only ready-made app found that rings loudly through silent mode and Do Not Disturb on both iPhone and Android, and repeats until someone acknowledges. It costs a one-time fee per person. |
| ntfy is the second siren | It is free and overrides Do Not Disturb on Android. On iPhone it is weak. |
| Automated voice calls are the escalation step | A ringing call is what reliably wakes a sleeping person. Calls start 60 to 90 seconds after the press if nobody has replied. |
| Exotel is preferred over Twilio for voice calls | Exotel calls come from an Indian number that family will pick up. Twilio calls arrive from foreign or unknown numbers. |
| SMS is sent from a spare Android phone with a prepaid SIM, using the free "SMS Gateway for Android" app | Every cloud SMS company in India requires TRAI DLT registration. That takes about a week and costs Rs 5,900. A personal SIM avoids it. |
| The wall button uses a normally-closed red mushroom switch | It is big and easy to press. If the wire breaks, the system raises an alarm instead of going silent. |
| The 4G backup uses the A7670C module, not the SIM800L | The SIM800L only works on 2G. Jio has no 2G, and Airtel and Vi are shutting 2G down. |
| Every button reports in every 60 seconds, and the hub raises an alert if it goes quiet | A dead button gives no coverage. The family needs to know before an emergency, not during one. |
| Alerts stop escalating only when someone presses "On my way" | A phone buzzing does not mean help is coming. If nobody presses "Arrived" within 15 minutes, everyone is alerted again. |
| Test alerts never trigger voice calls | Weekly tests should not ring people's phones at night. |
| A second press within 2 minutes joins the existing emergency, and holding or cancelling within 20 seconds undoes a mistake | Frightened people press buttons repeatedly. Accidental presses happen. |
| Neighbours, the driver and the doctor are paged immediately | The ambulance is 30 to 60 minutes away. The neighbours are 3 to 4 minutes away. |
| The database is a single SQLite file | The system sees only a handful of events a day. One file is simple to back up, and open emergencies survive a restart. |
| WhatsApp and Telegram are not used to wake people | Neither can break through Do Not Disturb. Telegram is used only as a running log. Unofficial WhatsApp tools risk a permanent ban on the number. |
| Real configuration, secret keys and medical files are excluded from git | They are private. The `.gitignore` file blocks them. |

## 4. Folders and files the project is connected to or reads from

There are no external drives, network shares or folders outside the project.

**Main folder:** `/home/user/personal`. It is a temporary cloud container. The durable copy is the GitHub repository in section 9.

| Full path | What it is |
|---|---|
| `/home/user/personal/README.md` | Overview and quick start |
| `/home/user/personal/HANDOFF.md` | This document |
| `/home/user/personal/.gitignore` | Keeps secrets, the database and private medical files out of git |
| `/home/user/personal/docs/BLUEPRINT.md` | The full design |
| `/home/user/personal/docs/MEDICAL_PLAYBOOKS.md` | Cited medical guidance |
| `/home/user/personal/docs/ALERT_CHANNELS_INDIA.md` | Research on phone alerts, SMS, voice and hardware in India |
| `/home/user/personal/docs/OPEN_SOURCE_LANDSCAPE.md` | Open-source projects reviewed and what was borrowed |
| `/home/user/personal/docs/RUNBOOK.md` | How to deploy, test and drill |
| `/home/user/personal/docs/INFO_NEEDED.md` | The checklist of details still needed from Maitrabh |
| `/home/user/personal/hub/pyproject.toml` | Hub package definition and dependency list |
| `/home/user/personal/hub/config.example.yaml` | Template configuration with placeholders only |
| `/home/user/personal/hub/Dockerfile`, `/home/user/personal/hub/docker-compose.yml`, `/home/user/personal/hub/Caddyfile` | Server deployment files |
| `/home/user/personal/hub/hub/main.py` | Web endpoints |
| `/home/user/personal/hub/hub/dispatcher.py` | Escalation and watchdog logic |
| `/home/user/personal/hub/hub/providers.py` | Pushover, ntfy, SMS, voice and Telegram senders |
| `/home/user/personal/hub/hub/config.py` | Checks the configuration file |
| `/home/user/personal/hub/hub/db.py` | Database |
| `/home/user/personal/hub/hub/playbooks.yaml` | Short medical guidance shown on the responder page |
| `/home/user/personal/hub/hub/static/responder.html` | Page that opens from the alert link |
| `/home/user/personal/hub/hub/static/kiosk.html` | Big-button page for the old phones |
| `/home/user/personal/hub/tests/test_hub.py` | Automated tests |
| `/home/user/personal/firmware/esp32-panic-button/esp32-panic-button.ino` | Wall-button code |
| `/home/user/personal/firmware/esp32-panic-button/secrets.example.h` | Template for the button's Wi-Fi and key settings, with placeholders only |
| `/home/user/personal/firmware/esp32-panic-button/WIRING.md` | Parts list and wiring |
| `/home/user/personal/home-assistant/panic_lights.yaml` | Lights, siren and announcement rules |

**What the hub reads when it runs.** None of these files exist yet; they are all created at deployment.

- `hub/config.yaml`, or the path set in the HUB_CONFIG setting.
- `hub/.env`, which holds the secret keys.
- The playbooks file at `hub/hub/playbooks.yaml`, or the path set in the HUB_PLAYBOOKS setting.

**Research transcripts.** These were working files in `/tmp/claude-0/-home-user-personal/ceea314c-870e-556e-9dbd-105786c4d0e1/tasks/`, a temporary folder. They are not needed: their content was copied into the three research documents in `docs/`.

## 5. Where outputs are saved

- **All deliverables** are the files in `/home/user/personal`, pushed to GitHub. See section 9.
- **When the hub runs,** it writes its database file to the path set by `db_path` in the configuration. The template uses `/data/hub.sqlite3` inside the Docker container, stored in a Docker volume named `hub-data`. No database exists yet, because the hub has never been deployed.
- **Delivery logs** go into that same database, and to the server's screen output, which you can view with `docker compose logs`.

## 6. How to run or continue it

**What needs to be installed:**

- For testing on a computer: Python 3.11 or newer.
- For the real server: a small Linux server with Docker and Docker Compose, and a web address.
- For the wall button: the Arduino IDE 2.x with the "esp32" board package and the ArduinoJson library. Add the TinyGSM library if the 4G module is fitted.

**Run the tests on a computer:**

```bash
cd /home/user/personal/hub
python3 -m pip install -e ".[dev]"
python3 -m pytest -q          # expect: 7 passed
```

**Continue the project:**

1. Collect the details listed in `docs/INFO_NEEDED.md`: the address and map pin, everyone's names, numbers and phone types, the oxygen equipment, and the medicine lists. Keep medical files out of the repository.
2. Copy `hub/config.example.yaml` to `hub/config.yaml` and fill it in.
3. Create `hub/.env` with freshly generated keys, using the commands in `docs/RUNBOOK.md` section A.
4. Rent a small server, point a web address at it, put that address in `hub/Caddyfile`, then start the hub:

   ```bash
   docker compose up -d --build
   ```

5. Each family member installs Pushover, buys the licence, allows it through Do Not Disturb, and saves the alert number as a starred contact.
6. Set up the kiosk page on the two old phones using Fully Kiosk Browser.
7. Send a test alert as shown in the runbook. Then follow the weekly, monthly and quarterly routine in `docs/RUNBOOK.md`.
8. Build the wall buttons using `firmware/esp32-panic-button/WIRING.md`.

## 7. Instruction, memory and settings files

- **Project instructions:** there is no `CLAUDE.md`, no `.claude/` folder and no other AI instruction or memory file inside the project.
- **Project settings files:**
  - `/home/user/personal/hub/pyproject.toml` holds the dependencies and test settings.
  - `/home/user/personal/hub/config.example.yaml` is the template for the main settings.
  - `/home/user/personal/firmware/esp32-panic-button/secrets.example.h` is the template for the button settings.
  - `/home/user/personal/.gitignore` controls what is kept out of git.
- **Outside the project:** `/root/.claude/` belongs to the cloud environment's own Claude Code setup. It is not part of this project and holds nothing specific to it.

## 8. Secret files

**None are present.** A search found no `.env`, `config.yaml`, `secrets.h`, database, key or certificate file.

The two template files hold placeholders only, not real secrets:

- `config.example.yaml`
- `secrets.example.h`

When the project is deployed, these files will hold real secrets. They are already excluded from git.

- `hub/config.yaml`
- `hub/.env`
- `firmware/esp32-panic-button/secrets.h`
- `*.sqlite3`

## 9. Commit and push status

- **Repository:** https://github.com/matsxc/personal
- **Branch:** `claude/home-emergency-alert-10luib`. It is the only branch on the remote. No main branch and no pull request exist.
- **Code:** all project code is committed and pushed. The last pushed project commit is `62c1dce`. Before this handoff was written, the folder matched the remote exactly.
- **This handoff file** is committed and pushed in a separate commit on the same branch.

## 10. Open problems and next three steps

**Open problems:**

- **The system is not live.** No real details have been entered and nothing is deployed, so it protects no one today.
- **The wall-button code has never been compiled or run on real hardware.** Its connection to the server also skips the security-certificate check, which is marked as a to-do in the code.
- **Several prices and services could not be confirmed online.** These are Robu.in parts prices, Exotel plan rental, and Twilio India voice rates.
- **The medical guidance is general.** The parents' doctors should review it against their actual medicines, especially the oxygen targets and the low-sugar instructions.
- **The project lives only on a non-default branch with no pull request.** Someone could miss it in a repository review.

**Next three steps:**

1. Gather the details in `docs/INFO_NEEDED.md`. Then research the nearest 24x7 hospitals that have a CT scanner and a heart catheter lab, and fill in `hub/config.yaml`.
2. Deploy the hub on a small server. Set up Pushover on every family phone and the kiosk page on the two old phones. Then run the first test alert from `docs/RUNBOOK.md`.
3. Build and bench-test one wall button, then run the first live drill with the neighbours, driver and doctor.

PROJECT: Home Emergency Alert System (matsxc/personal)
ONE-LINE PURPOSE: A panic-button system so that elderly parents living alone in India can summon family, neighbours and a doctor with one press, with loud escalating alerts and on-screen emergency guidance.
STATE: active
MAIN FOLDER: /home/user/personal
OTHER FOLDERS USED: none (only temporary research transcripts in /tmp/claude-0/-home-user-personal/ceea314c-870e-556e-9dbd-105786c4d0e1/tasks/, already copied into docs/)
OUTPUTS SAVED AT: /home/user/personal (docs/, hub/, firmware/, home-assistant/), pushed to GitHub; future runtime database at /data/hub.sqlite3 in the hub-data Docker volume once deployed
REPOSITORY: https://github.com/matsxc/personal, branch claude/home-emergency-alert-10luib
UNCOMMITTED WORK: no
SECRET FILES PRESENT: no
YOUR RECOMMENDATION: keep active
HANDOFF SAVED AT: /home/user/personal/HANDOFF.md
