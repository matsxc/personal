# Home Emergency Alert System

A panic-button system for two elderly parents in a secluded house in India, built so that one press wakes the right people, tells them where to go and what to do, and keeps escalating until someone physically arrives.

**Start with [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md).**

```
docs/
  BLUEPRINT.md              the whole design: layers, ladder, resilience, phases, minute-by-minute flow
  MEDICAL_PLAYBOOKS.md      cited guidance for each emergency (heart attack, stroke, low sugar, BP crisis,
                            falls, breathing, choking, arrest, sepsis, heat, faint), oxygen rules, 112/108,
                            go-bag, CPR/AED, medication pitfalls
  ALERT_CHANNELS_INDIA.md   what wakes a phone at 2 a.m. in India, SMS/voice/DLT, hardware, prices
  OPEN_SOURCE_LANDSCAPE.md  the GitHub projects surveyed and what was borrowed
  RUNBOOK.md                deployment, weekly test, monthly drill, quarterly checks
  INFO_NEEDED.md            what you still need to give me
hub/                        the alert server (FastAPI + SQLite): fan-out, escalation, acks, watchdog,
                            responder page with playbooks, kiosk page for the old phones. Tested.
firmware/esp32-panic-button/  wall button firmware + wiring + parts list (Wi-Fi first, 4G fallback)
home-assistant/             lights / porch flash / siren / hall TTS automation
```

## Run the hub locally

```bash
cd hub
pip install -e ".[dev]"
python -m pytest              # 7 tests: fan-out, escalation, ack, test mode, cancel, watchdog, restart
cp config.example.yaml config.yaml   # edit; set providers: console: {} to just log
HUB_DEVICE_TOKEN=$(openssl rand -hex 24) HUB_RESPONDER_TOKEN=$(openssl rand -hex 24) home-alert-hub
# then open http://localhost:8000/kiosk?device=mom-room-phone&token=$HUB_DEVICE_TOKEN
```

Production: `docker compose up -d --build` behind Caddy (see `hub/docker-compose.yml`, `docs/RUNBOOK.md`).

## Status

- [x] Blueprint, research, medical playbooks
- [x] Hub: API, escalation engine, providers (Pushover, ntfy, SMS gateway, MSG91, Twilio, Exotel, Telegram), responder page, kiosk page, tests
- [x] ESP32 firmware (untested on hardware yet)
- [ ] Real config: location, people, hospitals (waiting on `docs/INFO_NEEDED.md`)
- [ ] Deploy + first test alert
- [ ] Build the two wall buttons
- [ ] First live drill with the neighbours

This is a family safety project, not medical advice. Review the playbooks with the parents' doctors.
