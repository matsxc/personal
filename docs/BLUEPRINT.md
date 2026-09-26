# Home Emergency Alert System: blueprint

**Goal.** When either parent feels unwell at any hour, one press of a button in their room must, within seconds, wake the right people, tell them where to go and what to do, and keep escalating until someone physically arrives. It must keep working through a power cut, a broadband outage, a dead phone battery, and a hub crash, and the family must know *before* an emergency if any part of it has stopped working.

**Design principles**
1. **Two of everything on the path that matters.** Two triggers per room, two ways out of the house (Wi-Fi + 4G), two siren channels per person, two people within 5 minutes.
2. **Silence is an alarm.** Every device heartbeats; the family hears when a button dies.
3. **Escalate until a human arrives, not until a phone buzzes.** The ladder only stops when someone taps "On my way", and re-fires if nobody taps "Arrived".
4. **The first responder is a neighbour, not the ambulance.** Ambulance is 30-60 min away here; the neighbour is 3.
5. **Drill it.** A weekly test alert and a monthly live drill are part of the system, not optional.

---

## 1. The system in one picture

```
 PARENTS' HOUSE                                  CLOUD (small VPS, Rs ~400/mo)          RESPONDERS
 ┌──────────────────────────────────────┐       ┌──────────────────────────────┐       ┌──────────────────────┐
 │ Mom's room                           │       │  ALERT HUB  (hub/)           │       │ Maitrabh (far)       │
 │  [ESP32 wall button, NC mushroom]────┼──Wi-Fi─┼─▶ POST /alert               │──push─▶│  Pushover siren      │
 │  [old phone, kiosk page] ────────────┼──Wi-Fi─┼─▶ POST /heartbeat (60 s)    │──sms──▶│  SMS + voice call    │
 │ Dad's room                           │        │                              │──voice▶│  Responder page:     │
 │  [ESP32 wall button] ────────────────┼──Wi-Fi─┤   escalation ladder          │        │   on-my-way / arrived│
 │  [old phone, kiosk page] ────────────┼────────┤   acknowledgement tracking   │       ├──────────────────────┤
 │ Bathroom: [Zigbee button]──HA────────┼────────┤   watchdog (dead device)     │──push─▶│ Brother (far)        │
 │                                      │        │   responder page + playbooks │       ├──────────────────────┤
 │ Router + ONT on mini DC UPS          │        │   SQLite (survives restart)  │──sms──▶│ Driver (8 min)       │
 │ Home Assistant (optional) ◀──webhook─┼────────┤                              │──voice▶│ Neighbour 1 (3 min)  │
 │   lights on, porch flash, siren, TTS │        └──────────────┬───────────────┘       │ Neighbour 2 (4 min)  │
 │                                      │                       │                       │ Society doctor (6min)│
 │ 4G FALLBACK (if hub unreachable):    │                       │ Telegram group log    ├──────────────────────┤
 │  A7670C modem on the ESP32 sends SMS │                       ▼                       │ Other parent:        │
 │  + rings the first contact directly ─┼───────cellular──────▶ family phones           │  ntfy siren in their │
 └──────────────────────────────────────┘                                               │  room + hall TTS     │
                                                                                        └──────────────────────┘
```

## 2. Layers

### Layer 0: the people (this matters more than the electronics)
| Tier | Who | ETA | Role in the plan |
|---|---|---|---|
| Inside the house | The other parent | 0 | Goes to the room, puts the phone on speaker with a family member, follows the playbook on the responder page |
| Tier 1 local | Neighbour 1, Neighbour 2 | 3-4 min | Get to the patient, unlock the gate, start first aid, flag the ambulance |
| Tier 1 local | Society doctor | 6 min | Triage, decides hospital, rides along |
| Tier 1 local | Driver | 8 min | Car at the gate, drives to the pre-chosen hospital if faster than the ambulance and the condition allows (not spine/hip injury or cardiac arrest) |
| Tier 2 family | Maitrabh, brother | far | Command: calls 112/108, calls the hospital, coordinates on the responder page, travels |
| Tier 3 | 108/112 ambulance, private ambulance | 30-60 min | Transport and advanced care |

Each Tier 1 person gets: a laminated card with the address, Plus Code, gate directions, the red-folder location, the two hospital names, and the hands-only CPR steps. And one 2-hour CPR class.

### Layer 1: triggers (in each bedroom)
1. **Wall button**: ESP32 + 60 mm red normally-closed mushroom button, mains + mini UPS. Firmware in `firmware/esp32-panic-button/`. Press = alert. Hold 5 s = cancel within the grace window. Heartbeat every 60 s. LED tells the parent it is alive. Optional A7670C 4G module for SMS + call when Wi-Fi or the hub is down.
2. **Old phone on a charging stand**: `hub/hub/static/kiosk.html` in Fully Kiosk Browser. One giant HELP / मदद button, 20 s cancel, "NO NETWORK: call 112" fallback, heartbeat with battery level. Charge limited to 80% to avoid swelling.
3. **Bathroom**: Zigbee button (Sonoff SNZB-01P) via Home Assistant, because falls happen in bathrooms. Phase 2.
4. **Wearable** (phase 2): a watch with fall detection for whichever parent is at higher fall risk, or a paid SOS-button service (Emoha / Anvayaa) as a human backstop.

### Layer 2: the hub (`hub/`)
A small FastAPI service on a cloud VPS (so a house power cut cannot take it down), behind Caddy for HTTPS. On `POST /api/v1/alert` it:
1. Opens an incident in SQLite (survives restart; open incidents resume their ladder on boot).
2. Fires side effects: Home Assistant webhook (lights, porch flash, siren, TTS in the hall).
3. Walks the **escalation ladder** from `config.yaml`:

| Time | Who | How | Condition |
|---|---|---|---|
| 0 s | Maitrabh, brother, both parents | Pushover emergency (repeats every 30 s until acknowledged) + ntfy max + SMS + Telegram | always |
| 0 s | driver, neighbours, doctor | push + SMS | always |
| 60 s | Maitrabh, brother | voice call, message read 3 times | nobody tapped "On my way" |
| 90 s | neighbours, driver | voice call | nobody tapped "On my way" |
| 3 min, then every 3 min x10 | everyone incl. doctor | voice + push | nobody tapped "On my way" |
| 15 min, then every 10 min x6 | everyone | push + voice | nobody tapped "Arrived" |

4. Every message carries a link to the **responder page** (`/i/{incident}`): a red banner, a running timer, tap-to-call 112 / 108 / every contact / both hospitals, the map link, and the buttons **On my way (with ETA) / Seen / Arrived / Cannot come / Resolved**. Every tap is broadcast to everyone else, so nobody drives blind and nobody assumes someone else went. Below the buttons: the **playbooks** (first 60 seconds, chest pain, stroke, low sugar, high sugar, BP crisis, fall, breathing, choking, cardiac arrest, sepsis, heat, faint), the oxygen rules, and the 112 script.
5. **Watchdog**: a device silent for 5 min is marked offline and the admins get a high-priority (not siren) alert: "Mom's room button OFFLINE. The room has NO panic coverage." Recovery is announced too.
6. **Test mode**: `kind: test` runs the whole chain to the configured people with "[TEST]" prefixes and never voice-calls anyone.
7. **Duplicate press** within 2 min joins the existing incident; a **cancel** within 20 s resolves it and tells everyone it was a mistake.

Tested: `hub/tests/test_hub.py` covers fan-out, escalation timing, stop-on-ack, test mode, cancel, watchdog offline/recovery, and resume after restart.

### Layer 3: channels (why several)
| Channel | Wakes a sleeping phone? | Cost | Used for |
|---|---|---|---|
| Pushover, priority "emergency" | **Yes**, iPhone (Apple critical alert) and Android (alarm stream, DND override), repeats until acknowledged | Rs ~420 once per person per platform | Primary siren |
| ntfy, priority 5 | Yes on Android (override DND + keep alerting); weak on iPhone | free | Second siren for Android members and the parents' own phones |
| Voice call (Exotel Indian number; Twilio fallback; or the button's own 4G modem) | **Yes**, any phone, if the number is starred | Rs ~1/min | Tier 2 escalation, the thing that actually works at 2 a.m. |
| SMS via an old Android phone running SMS Gateway (no TRAI DLT paperwork) or the A7670C modem | No, but it arrives when data doesn't | Rs 200/month SIM | Address + map link + responder link to everyone |
| Telegram group | No | free | Running log everyone can read |
| WhatsApp Cloud API | No | Rs 0.15/msg | Phase 2 context channel only |

Every phone in the ladder: alert number saved as a starred contact, Pushover/ntfy excluded from battery optimisation, "Repeat callers" allowed through DND.

### Layer 4: resilience
| Failure | What happens |
|---|---|
| House power cut | Router + buttons on mini DC UPS (4-6 h). Phones on battery. Hub is in the cloud. |
| Broadband down | ESP32 with A7670C sends SMS + rings the first contact directly over 4G. Kiosk phone shows "NO NETWORK, call 112". |
| Hub crashes / VPS reboots | Open incidents and their ladder position are in SQLite; the ladder resumes on start. Uptime Kuma / Healthchecks watches the hub's `/healthz`. |
| A button dies (unplugged, Wi-Fi password changed) | Watchdog alert to admins within 5 min. LED on the button goes from steady green to blinking so the parent can tell too. |
| Pushover down | ntfy, SMS, voice all still fire. No single provider is load-bearing. |
| A responder's phone is off | The ladder calls the next people and keeps repeating until someone says "On my way". |
| Family cannot be reached at all | Tier 1 neighbours + doctor were paged at 0 s and voice-called at 90 s; they call 108 themselves from the responder page. |
| Mis-press | 20 s cancel at the button / kiosk; "Resolved: pressed by mistake" goes to everyone. |

### Layer 5: information, ready before it is needed
- **Home location** in three forms: address with landmark directions, Google Plus Code, DIGIPIN, plus a maps link. Same text on a sticker at the gate.
- **Hospitals**: the nearest 24x7 CT + thrombolysis hospital and the nearest 24x7 cath-lab hospital, with phone numbers, drive time and a note on which to choose for which emergency. Drive there once.
- **Red folder** by the door (`docs/MEDICAL_PLAYBOOKS.md` Part 4) and a photo set on every family phone.
- **Oxygen**: concentrator and cylinder location in every alert; flow card on the machine; safety rules; the oximeter thresholds that decide whether to use it at all.
- **Medicines**: a one-page summary per parent; sick-day rules from their doctors; glucagon kit in the fridge for Mom.

---

## 3. Emergency flow, minute by minute

```
00:00  Mom presses the wall button.  Buzzer: 3 chirps + 1 long (sent).  Red LED on.
00:01  Hub opens incident, fires HA webhook: all lights on, porch flashing, hall speaker: "Emergency. Mom's room. Help has been called."
00:02  Pushover sirens on Maitrabh, brother.  ntfy siren on Dad's phone in the other room.  SMS + push to driver, neighbours, doctor.
00:05  Dad reaches Mom's room, opens the alert link, taps "Arrived", puts the phone on speaker with Maitrabh.
00:30  Maitrabh: opens responder page, sees Dad arrived, calls the house, reads the playbook aloud (chest pain? stroke? sugar?), dials 108 from the page.
01:00  (if nobody had tapped On my way) voice calls to Maitrabh and brother.
01:30  (if still nobody) voice calls to neighbours + driver.
02:00  Neighbour 1 taps "On my way, 3 min" → everyone sees it.  Driver taps "On my way, 8 min".
05:00  Neighbour 1 arrives, taps "Arrived", opens the gate, sends someone to the road.
06:00  Doctor arrives.  Decides: wait for 108 or go by car to the cath-lab hospital.
30-60  Ambulance.  Maitrabh has already called the hospital's emergency desk with the one-page summary.
       Anyone taps "Resolved" with a note ("taken to X hospital, stable").  Everyone is told to stand down.
```

## 4. Build phases

| Phase | What | Outcome |
|---|---|---|
| **0. This week** | Fill `config.yaml` (contacts, location, hospitals). Deploy the hub on a VPS. Everyone installs Pushover, buys the licence, whitelists it, stars the alert number. Set up the kiosk page on the two old phones. Run a test alert. | Working end-to-end alert from the old phones, no hardware yet |
| **1. Next 2 weeks** | Build two ESP32 wall buttons (parts list in `firmware/.../WIRING.md`), mini UPS for the router. SMS gateway phone. First live drill with neighbours. Red folder. Laminated cards. | Physical buttons, SMS path, people briefed |
| **2. Month 2** | A7670C 4G fallback on the buttons. Home Assistant for lights + hall TTS. Bathroom Zigbee buttons. Exotel voice. Hospital drive test. CPR class for the household + neighbours. | Works without broadband; lights + voice |
| **3. Later** | Fall-detection watch. Daily "I'm OK" check-in. Medication reminders. Paid SOS backstop service if desired. Oxygen run-time card. | Passive safety, not just the button |

## 5. What I still need from you (see `docs/INFO_NEEDED.md`)
Location and directions, the hospitals near you, everyone's numbers and phone types, the concentrator model and cylinder size, the parents' medicine lists and reports, and which VPS/domain to use. The code and docs are written so that every one of those is a config entry, not a code change.
