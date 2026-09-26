# Alert delivery and hardware in India: what actually works (Sept 2026)

Research notes behind the choices in `docs/BLUEPRINT.md`. Prices are indicative; items marked [unverified] could not be confirmed directly.

## 1. SMS and voice calls, programmatically

### TRAI DLT: needed for a personal system?
- **Yes, for any cloud A2P provider.** Every SMS on a bulk route is scrubbed against the DLT registry; without a registered entity, header and template, operators drop it, regardless of volume ([developer guide](https://startmessaging.com/blog/dlt-registration-india-sms-developer-guide-2026)).
- Individuals can register (PAN + Aadhaar). One-time Rs 5,900; entity ID in 1-3 working days; header + template approval a few more days. Templates are fixed text with `{#var#}` placeholders, so the alert wording must be pre-approved.
- Transactional / Service-Implicit templates are delivered 24x7 to DND numbers.

### Providers (all need your DLT IDs)
| Provider | Indicative price | Notes |
|---|---|---|
| MSG91 | Rs 0.16-0.25/SMS, prepaid wallet | Good docs, no minimum. Supported by the hub. |
| Fast2SMS | Rs 0.21-0.25, from Rs 100 top-up | Hobbyist-friendly |
| Gupshup / Kaleyra | Rs 0.10-0.18 but Rs 10k-25k minimum | Enterprise |
| AWS SNS | ~$0.0028/SMS domestic | Needs support ticket for sender ID + PEID |
| Twilio | [unverified] | Also needs DLT, USD billing |
| Exotel | Bundled with voice plans | Best if you also want Indian voice |

### Voice call APIs
- **Exotel** (Indian): outbound call into a flow whose Greeting applet speaks dynamic text; ~Rs 0.80-1.15/min plus plan rental [plan rental unverified]. Calls come from an Indian number that family will pick up. Supported by the hub.
- **MSG91 Voice**: TTS voice alerts with a virtual number subscription.
- **Twilio / Plivo**: constrained by DoT rules on VoIP-to-PSTN for domestic calls; calls arrive from a foreign/unknown caller ID that people ignore at 2 a.m. Supported by the hub as a fallback, not recommended as primary for India.
- TRAI's 2025 amendments push service calls onto 160-series numbers; currently mandated for regulated entities, not individuals. Watch this.

### Skip DLT entirely: your own SIM as the gateway (recommended)
- **[capcom6/android-sms-gateway](https://github.com/capcom6/android-sms-gateway)** (Apache-2.0): an old Android 5+ phone runs a REST API (local or via the free cloud relay). Messages come from the household's own number, which recipients recognise. Supported by the hub (`smsgate` provider).
- **A7670C 4G module on the ESP32**: AT commands for SMS and voice dial directly from the button, no cloud, works during ISP outage. Implemented in the firmware as the fallback path.
- TRAI caps personal SIMs at ~100 SMS/day; trivial for emergency use.

## 2. WhatsApp
- **Meta Cloud API**: Utility template Rs 0.145 per message in India; needs a Meta Business account and a dedicated number; unverified businesses capped at 250 conversations/day. Meta's 2026 policy tightening on non-business use adds account-review risk. WhatsApp notifications respect DND like any chat app, so it is a *context* channel, never the siren.
- **Unofficial libraries (Baileys, whatsapp-web.js)**: bans are common and permanent and can take the personal number with them. Avoid.

## 3. Push notifications that wake a sleeping phone

| Option | Android loud/DND | iPhone loud/DND | Cost |
|---|---|---|---|
| **Pushover** | Alarm stream, DND override, repeats until acknowledged (priority 2 + retry/expire) | **Apple-approved Critical Alerts**: bypasses mute and Focus | $4.99 one-time per platform |
| **ntfy** | Foreground service, per-priority channel with "override DND" and "keep alerting" | No Critical Alerts entitlement; delivery best-effort | Free self-hosted |
| **Home Assistant Companion** | `channel: alarm_stream_max` + TTS | HA holds the Critical Alerts entitlement (`push.sound.critical: 1`) | Free (needs HA) |
| Gotify | Yes | No iOS app | Free |
| Telegram bot | Ordinary notification; cannot override DND | Same | Free |
| Custom app + FCM | Possible, but Android 14+ restricts full-screen intents to call/alarm apps | Needs Apple entitlement, rarely granted to individuals | Dev time |

Sources: [Pushover API](https://pushover.net/api), [Pushover iOS Critical Alerts](https://blog.pushover.net/posts/2020/2/ios-critical-alerts), [ntfy phone docs](https://docs.ntfy.sh/subscribe/phone/), [ntfy iOS limitations](https://github.com/binwiederhier/ntfy-ios/blob/main/docs/TECHNICAL_LIMITATIONS.md), [HA critical notifications](https://github.com/home-assistant/companion.home-assistant/blob/master/docs/notifications/critical.md), [Android 14 FSI changes](https://developer.android.com/about/versions/14/behavior-changes-14).

**Recommendation for a mixed Android/iPhone family:** Pushover is the only off-the-shelf option that is loud on both platforms through DND and repeats until acknowledged (~Rs 420 per person per platform, once). Layer ntfy as a free redundant channel for Android members, and a voice call as the channel of last resort. A ringing call still bypasses Focus for starred contacts: **save the alert number as a starred/favourite contact on every phone.**

On Xiaomi/Vivo/Oppo/Realme phones (very common in India), whitelist the Pushover/ntfy apps from battery optimisation or they get killed; see [dontkillmyapp.com](https://dontkillmyapp.com).

## 4. Hardware

- **ESP32 boards:** ESP32-WROOM-32 DevKit ~Rs 284-400 ([Robokits](https://robokits.co.in/wireless-solutions/iot-esp-module/esp32-development-board-wifi-bluetooth)); ESP32-S3 ~Rs 700-900.
- **4G modules:** SIMCom **A7670C** (LTE Cat-1 + 2G fallback, Indian bands) Rs 1,270-2,300 ([Robu](https://robu.in/product/sim-a7670c-4g-lte-development-board-with-4g-flex-antenna/)). SIM7600EI Rs 1,800-4,800 (overkill). LilyGO T-A7670X / Waveshare ESP32-S3-SIM7670G integrated boards are the tidiest single-board option. Voice calls need the A7670C variant with audio codec; the plain module does SMS plus "ring and hang up".
- **SIM800L (2G):** still works on Airtel/Vi/BSNL today; Jio has no 2G; expect shutdown 2027-28. Don't build new on it.
- **Big red button:** 100 mm arcade dome buttons Rs 300-600 [unverified]; industrial 40-60 mm mushroom E-stop heads (Schneider XB4/XB5) Rs 200-400 at [Schneider eShop India](https://eshop.se.com/in/push-button-mushroom-red-1-nc-60mm.html). The mushroom is tactile for elderly users and latching (stays pressed until twisted back).
- **Router UPS:** [Resonate RouterUPS](https://www.amazon.in/Resonate-RouterUPS%C2%AE-Original-Intelligent-Certified/dp/B017NC2IPM) Rs 1,900-4,500 (up to 6 h), RouterUPS Micro Rs 1,499, Oakter Mini UPS ~Rs 1,500. One for the router/ONT, one for the buttons and gateway phone.
- **Smart bulbs:** Philips **WiZ** 9 W ~Rs 659-1,000 with native local-LAN Home Assistant integration. Wipro bulbs are Tuya-based (need local key extraction). For "every light on at 3 a.m." prefer WiZ or Sonoff/Shelly relays; avoid cloud-only scenes that fail when the internet does.
- **Wireless buttons:** Sonoff SNZB-01P (~Rs 900-1,200) and Aqara Mini Switch (Rs 1,500-2,000 grey import) are Zigbee, 2-5 yr coin cell, need a coordinator (~Rs 1,500) + Home Assistant; excellent for bathroom/bedside. Shelly Blu Button1 and Flic 2 are BLE with no official India distribution [pricing unverified]. Wired ESP32 button: ~Rs 800 all-in, mains + UPS, no battery to die, can drive a siren and 4G fallback itself.
- Best pattern: one wired ESP32 master station per bedroom + Zigbee buttons in bathrooms, all landing on the hub.

## 5. Old Android phone as kiosk panic button
- **Kiosk software:** [Fully Kiosk Browser](https://www.fully-kiosk.com/en/) (~$7 one-time): keeps screen on, auto-relaunch, motion wake, REST API. Free alternatives: Android screen pinning, or lock task mode via a device-owner app.
- **PWA viability:** a fullscreen page with one giant button plus the Screen Wake Lock API is fine *as the trigger* (that is `hub/hub/static/kiosk.html`). Do not rely on a PWA for *receiving* alarms.
- **Keep screen on while charging:** Developer Options "Stay awake", or Fully Kiosk's keep-screen-on. Dark, low-brightness UI limits heat.
- **Battery health:** a phone at 100% on charge for years swells. Android 15+/Samsung/Pixel have "Limit to 80%". Older phones: a smart plug automated by Home Assistant to charge 40-80% using Fully Kiosk's battery API. Ventilate; don't bury it in a cushion.
- **Fall-detection wearables in India:** Apple Watch SE 3 (Rs 25,400+) / Series 11 (Rs 45,900+): fall detection auto-calls emergency (112 works) and texts contacts with location after 60 s immobility. Samsung Galaxy Watch 8 (Rs 32,999 BT / Rs 36,999 LTE): hard-fall detection, **off by default**. Noise/boAt: no credible fall detection found. Niche AGEasy Protec (4G, SOS, fall detection) on Amazon.in [accuracy unverified].

## 6. Location and hospital drive time
- **DIGIPIN** (India Post, 2025): 10-char code for a 4x4 m cell, from [dac.indiapost.gov.in/mydigipin](https://dac.indiapost.gov.in/mydigipin/home); increasingly recognised by state 112 control rooms.
- **Google Plus Code**: every driver's Google Maps resolves it. Put it on the front-gate sticker and in every alert.
- Include a `https://maps.google.com/?q=lat,lng` link in every message; this is what drivers and relatives tap.
- The **112 India app** sends an SOS with GPS to the state control room and your contacts; pre-register the household.
- **Drive time:** Google Routes API has 10,000 free events/month on Essentials, 5,000 on Pro (traffic-aware); a home system computing 3-5 hospital ETAs a few times a day is free. Mapbox 100k free/month. OSRM self-hosted free, no traffic. Ola Krutrim Maps 500k free/month, India-focused. Practical: precompute a table of 3-5 hospitals, refresh live ETAs only when an alert fires.

## Recommended stack (summary)
1. **Trigger:** ESP32 + 60 mm NC mushroom button per bedroom (+ A7670C on at least one), Sonoff Zigbee buttons in bathrooms, old Android phone running the kiosk page as a second trigger.
2. **Fan-out, in parallel from the hub:** Pushover Emergency to every family member, ntfy for Android members, SMS + voice from the household SIM (SMS gateway phone / A7670C), Telegram group as the log, WiZ bulbs via Home Assistant.
3. **Resilience:** router UPS, 4G path independent of Wi-Fi, heartbeat watchdog so silence itself is an alert.
4. **Skip:** DLT registration (for now), Twilio/Plivo for India voice, unofficial WhatsApp libraries, SIM800L, Telegram as the wake-up channel.
