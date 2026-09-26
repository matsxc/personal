# Open-source panic button and medical alert projects: what exists and what we reuse

Surveyed 26 Sept 2026. Nothing off-the-shelf is production-grade end to end, but the pieces are mature. Our hub (`hub/`) borrows the good patterns and avoids the dead ends listed here.

## ESP32 / ESP8266 button firmware

| Repo | Stars | Licence | What it does | What we took |
|---|---|---|---|---|
| [RAHB-REALTORS-Association/panic-button-esp](https://github.com/RAHB-REALTORS-Association/panic-button-esp) | 1 | GPLv3 | ESP32-C6, captive-portal setup, JSON webhook with device ID, battery %, RSSI, timestamp; low-battery heartbeat; OTA server; 3D case | Webhook payload shape, battery/RSSI in every heartbeat |
| [MrT-coder/alarma-ya](https://github.com/MrT-coder/alarma-ya) | 0 | MIT | ESP32 over MQTT/TLS drives a 130 dB siren; role-scoped broker creds, NTP before TLS, retained-message guard | Security hygiene reference for a future MQTT path |
| [Robert27/esp32-emergency-stop-button](https://github.com/Robert27/esp32-emergency-stop-button) | 5 | MIT | Industrial **normally-closed** mushroom button on ESP32-C3, MQTT to HomeKit, RGB LED status codes | NC button (wire-break = alarm), LED status vocabulary |
| [gcsecsey/ESP8266-Telegram-Panic-Button](https://github.com/gcsecsey/ESP8266-Telegram-Panic-Button) | 1 | - | 30-line Telegram sketch | Nothing new |
| [timothy3001/EmergencyButton](https://github.com/timothy3001/EmergencyButton) | 6 | - | Wemos D1 + LiPo, emails 3 recipients with battery voltage | Battery voltage in every alert |
| [kushagrabansal-IOT RAKSHA](https://github.com/kushagrabansal-IOT/GSM-GPS-Panic-Button-ESP32) | 1 | MIT | Indian project: ESP32 + SIM800L + GPS, SMS with maps link **and auto-dials** the contact | SMS + immediate call as the offline path (but on A7670, not SIM800L) |
| [Xinyuan-LilyGO/LilyGo-Modem-Series](https://github.com/Xinyuan-LilyGO/LilyGo-Modem-Series) | 356 | MIT | Official examples for ESP32 boards with integrated A7670/SIM7670G 4G modems | Hardware platform for the 4G fallback |
| [vshymanskyy/TinyGSM](https://github.com/vshymanskyy/TinyGSM) | 2.2k | LGPL-3 | AT abstraction; SMS send, voice dial on SIM800/SIM7600/A7670 | Used in our firmware for the modem path |
| [ESPHome sim800l component](https://esphome.io/components/sim800l/) | - | MIT/GPL | YAML: send_sms, dial, on_sms_received | Alternative if Home Assistant becomes the brain |
| [RomeHein/ESPecial](https://github.com/RomeHein/ESPecial) | 120 | GPLv3 | No-code ESP32: GPIO event to Telegram/MQTT/REST | Option for a no-firmware second button |

## Home Assistant based setups
- **HA `alert` integration**: built-in escalation ladder (`repeat: [1, 2, 5, 10]`, multiple notifiers, `alert.turn_off` = acknowledge). Simplest self-hosted ladder if you don't want our hub. Our hub does the same with explicit acknowledgement tracking and a responder page, which HA lacks.
- **HA Companion critical notifications** ([docs](https://github.com/home-assistant/companion.home-assistant/blob/master/docs/notifications/critical.md)): Android `channel: alarm_stream_max` + TTS; iOS `push.sound.critical: 1` (HA holds Apple's Critical Alerts entitlement). A free way to get true iOS critical alerts if the family installs the HA app.
- [WTavasi/elder-emergency-escalation](https://github.com/WTavasi/elder-emergency-escalation): student project, but its data model (tiered chain caregiver > family > responder, auto-promote on ack timeout, SMS fallback when push fails, audit log) is the template our dispatcher follows.
- Community threads: [Panic button for a 91-year-old](https://community.home-assistant.io/t/assistance-panic-button/331331), [emergency automation for a disabled person living alone](https://community.home-assistant.io/t/request-for-help-ideas-creating-an-emergency-alert-automation-for-disabled-person-living-alone/333830), [alert when motion stops (elderly care)](https://community.home-assistant.io/t/alert-when-motion-stops-after-x-minutes-elderly-care/547146).

## Android "one big button" / kiosk
- [UriahShaulMandel/BaldPhone](https://github.com/UriahShaulMandel/BaldPhone) (305 stars, Apache-2.0, F-Droid): full senior launcher with SOS button, pill reminders, big-button dialer. Development slowed since 2022 but stable. Worth installing on the parents' *own* phones.
- [guardianproject/ripple](https://github.com/guardianproject/ripple) (297 stars): PanicKit trigger app.
- [RushB-fr/freekiosk](https://github.com/RushB-fr/freekiosk) (634 stars, MIT): device-owner lock-task kiosk with REST API; wraps our kiosk page on a cheap tablet.

## Self-hosted alerting servers
| Tool | Stars | Fit |
|---|---|---|
| [ntfy](https://github.com/binwiederhier/ntfy) | 34.5k | Best free push; supported by the hub |
| [Apprise](https://github.com/caronc/apprise) | 17.4k | Fan-out to 200+ services incl. Twilio voice and Exotel; could replace our providers module later |
| [Healthchecks](https://github.com/healthchecks/healthchecks) | 10.4k | Dead-man's switch; our hub has its own watchdog, but Healthchecks can watch the hub itself |
| [Uptime Kuma](https://github.com/louislam/uptime-kuma) | 91.9k | Same idea, friendlier UI |
| [GoAlert](https://github.com/target/goalert) | 2.8k | Real on-call escalation with Twilio; heavier (Postgres) |
| Grafana OnCall OSS | archived Mar 2026 | Don't start on it |

## Indian context
- **112 ERSS** ingests voice, SMS, app SOS and Android's power-button emergency affordance. **No public API** for third-party devices; the practical integration is a human in the ladder dialling 112/108, which the responder page makes one tap.
- **Elder Line 14567**: 8 am-8 pm helpline, no API; a non-emergency escalation contact.
- **Delhi Police Senior Citizen app / Hyderabad Hawk Eye**: register the parents with local police plus two relatives; beat-officer visits.
- **Emoha, Anvayaa, Samarth**: their value is the *human 24x7 escalation desk* behind a wearable SOS button, with ambulance dispatch in 20-45 min. If the family wants a paid backstop, one of these subscriptions is the thing to buy; the hub can still be the first alert.

## Bottom line for our design
A **normally-closed mushroom button on an ESP32 (LilyGO T-A7670X for 4G)** with firmware modelled on panic-button-esp; **our hub** as the brain (ladder + acknowledgements + responder page + watchdog); **Pushover emergency / ntfy max** as sirens; **voice calls** as the tier that wakes people; **a mini DC UPS** and **the modem's own SMS/voice** as the offline path. Not built on: SIM800L (2G) and Grafana OnCall (archived).
