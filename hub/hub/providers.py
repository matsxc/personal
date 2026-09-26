"""Notification providers.

Each provider knows how to deliver one or more *methods* (push, sms, voice, ...)
to a contact. The dispatcher asks the registry for every provider that can serve
a given method for a given contact and tries all of them: redundancy is the
whole point of this system.

Nothing here is clever. Every provider is a single HTTPS request with a short
timeout, because a hung request must never block the rest of the fan-out.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Contact, Method, ProviderSettings

log = logging.getLogger("hub.providers")

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass
class Message:
    title: str
    body: str
    url: str | None = None  # responder page
    priority: str = "emergency"  # emergency | high | normal
    tags: list[str] = field(default_factory=list)
    voice_script: str | None = None  # what a voice call reads out

    @property
    def is_emergency(self) -> bool:
        return self.priority == "emergency"


@dataclass
class DeliveryResult:
    ok: bool
    provider: str
    detail: str = ""


class Provider:
    name: str = "base"
    methods: tuple[Method, ...] = ()

    def __init__(self, settings: dict[str, Any], client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    def can_reach(self, contact: Contact, method: Method) -> bool:  # pragma: no cover - overridden
        return False

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:  # pragma: no cover
        raise NotImplementedError


class ConsoleProvider(Provider):
    """Prints to the log. Used in tests and while wiring things up."""

    name = "console"
    methods = ("push", "sms", "voice", "telegram", "whatsapp", "console")
    sent: list[tuple[str, str, Message]] = []

    def can_reach(self, contact: Contact, method: Method) -> bool:
        return True

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        log.info("[console] %s -> %s (%s): %s | %s", method, contact.name, msg.priority, msg.title, msg.body)
        self.sent.append((contact.id, method, msg))
        return DeliveryResult(True, self.name, "logged")


class NtfyProvider(Provider):
    """https://ntfy.sh — self-hostable push. Priority 5 ('max') makes the Android
    app ring with an alarm-stream sound that overrides Do Not Disturb when the
    user has enabled 'Instant delivery' + 'Override DND' for the topic."""

    name = "ntfy"
    methods = ("push",)

    def can_reach(self, contact: Contact, method: Method) -> bool:
        return method == "push" and bool(contact.channels.ntfy_topic)

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        server = self.settings.get("server", "https://ntfy.sh").rstrip("/")
        headers = {
            "Title": msg.title,
            "Priority": "5" if msg.is_emergency else ("4" if msg.priority == "high" else "3"),
            "Tags": ",".join(msg.tags or (["rotating_light"] if msg.is_emergency else ["information_source"])),
        }
        if msg.url:
            headers["Click"] = msg.url
            headers["Actions"] = f"view, Open incident, {msg.url}, clear=true"
        if self.settings.get("token"):
            headers["Authorization"] = f"Bearer {self.settings['token']}"
        try:
            r = await self.client.post(f"{server}/{contact.channels.ntfy_topic}", content=msg.body.encode(), headers=headers, timeout=TIMEOUT)
            return DeliveryResult(r.status_code < 300, self.name, f"HTTP {r.status_code}")
        except httpx.HTTPError as e:
            return DeliveryResult(False, self.name, repr(e))


class PushoverProvider(Provider):
    """Pushover Emergency priority (2) repeats every `retry` seconds for `expire`
    seconds until the user acknowledges. Works on iPhone and Android and bypasses
    silent mode when the user enables it in the app."""

    name = "pushover"
    methods = ("push",)

    def can_reach(self, contact: Contact, method: Method) -> bool:
        return method == "push" and bool(contact.channels.pushover_user_key) and bool(self.settings.get("app_token"))

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        data: dict[str, Any] = {
            "token": self.settings["app_token"],
            "user": contact.channels.pushover_user_key,
            "title": msg.title,
            "message": msg.body,
            "sound": self.settings.get("sound", "siren"),
        }
        if msg.url:
            data["url"] = msg.url
            data["url_title"] = "Open incident"
        if msg.is_emergency:
            data.update({"priority": 2, "retry": int(self.settings.get("retry", 30)), "expire": int(self.settings.get("expire", 1800))})
        elif msg.priority == "high":
            data["priority"] = 1
        try:
            r = await self.client.post("https://api.pushover.net/1/messages.json", data=data, timeout=TIMEOUT)
            return DeliveryResult(r.status_code < 300, self.name, f"HTTP {r.status_code} {r.text[:120]}")
        except httpx.HTTPError as e:
            return DeliveryResult(False, self.name, repr(e))


class TwilioProvider(Provider):
    """Twilio SMS + voice. For India, SMS needs a DLT-registered sender/template for
    reliable delivery to domestic numbers; voice calls work without DLT and are the
    most reliable 'wake up' channel for iPhones."""

    name = "twilio"
    methods = ("sms", "voice")

    def _auth(self) -> tuple[str, str]:
        return (self.settings["account_sid"], self.settings["auth_token"])

    def can_reach(self, contact: Contact, method: Method) -> bool:
        if not self.settings.get("account_sid"):
            return False
        if method == "sms":
            return bool(contact.channels.sms) and bool(self.settings.get("from_sms"))
        if method == "voice":
            return bool(contact.channels.voice) and bool(self.settings.get("from_voice"))
        return False

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        sid = self.settings["account_sid"]
        try:
            if method == "sms":
                body = f"{msg.title}\n{msg.body}" + (f"\n{msg.url}" if msg.url else "")
                r = await self.client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    data={"From": self.settings["from_sms"], "To": contact.channels.sms, "Body": body[:1500]},
                    auth=self._auth(),
                    timeout=TIMEOUT,
                )
            else:
                script = msg.voice_script or f"{msg.title}. {msg.body}"
                # Repeat the script 3 times slowly; the person just woke up.
                twiml = "<Response>" + "".join(
                    f'<Say voice="alice" language="en-IN">{_xml(script)}</Say><Pause length="1"/>' for _ in range(3)
                ) + "</Response>"
                r = await self.client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
                    data={"From": self.settings["from_voice"], "To": contact.channels.voice, "Twiml": twiml},
                    auth=self._auth(),
                    timeout=TIMEOUT,
                )
            return DeliveryResult(r.status_code < 300, self.name, f"HTTP {r.status_code} {r.text[:120]}")
        except httpx.HTTPError as e:
            return DeliveryResult(False, self.name, repr(e))


class Msg91Provider(Provider):
    """MSG91 transactional SMS (India). Requires a DLT-approved template; the template
    must contain the variables you pass in ``template_vars`` order."""

    name = "msg91"
    methods = ("sms",)

    def can_reach(self, contact: Contact, method: Method) -> bool:
        return method == "sms" and bool(contact.channels.sms) and bool(self.settings.get("authkey"))

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        payload = {
            "template_id": self.settings["template_id"],
            "short_url": "0",
            "recipients": [
                {
                    "mobiles": contact.channels.sms.lstrip("+"),
                    "VAR1": msg.title[:60],
                    "VAR2": msg.body[:200],
                    "VAR3": msg.url or "",
                }
            ],
        }
        try:
            r = await self.client.post(
                "https://control.msg91.com/api/v5/flow/",
                json=payload,
                headers={"authkey": self.settings["authkey"]},
                timeout=TIMEOUT,
            )
            return DeliveryResult(r.status_code < 300, self.name, f"HTTP {r.status_code} {r.text[:120]}")
        except httpx.HTTPError as e:
            return DeliveryResult(False, self.name, repr(e))


class ExotelProvider(Provider):
    """Exotel (India) outbound call that connects the contact to a recorded/TTS
    'App' (Exotel applet flow). Set ``app_id`` to a flow that plays the emergency
    message. Exotel numbers are Indian, so calls look local and are picked up."""

    name = "exotel"
    methods = ("voice",)

    def can_reach(self, contact: Contact, method: Method) -> bool:
        return method == "voice" and bool(contact.channels.voice) and bool(self.settings.get("api_key"))

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        s = self.settings
        subdomain = s.get("subdomain", "api.exotel.com")
        url = f"https://{subdomain}/v1/Accounts/{s['sid']}/Calls/connect.json"
        data = {
            "From": contact.channels.voice,
            "CallerId": s["caller_id"],
            "Url": f"http://my.exotel.com/{s['sid']}/exoml/start_voice/{s['app_id']}",
            "CustomField": (msg.title + " " + msg.body)[:200],
        }
        try:
            r = await self.client.post(url, data=data, auth=(s["api_key"], s["api_token"]), timeout=TIMEOUT)
            return DeliveryResult(r.status_code < 300, self.name, f"HTTP {r.status_code} {r.text[:120]}")
        except httpx.HTTPError as e:
            return DeliveryResult(False, self.name, repr(e))


class SmsGateProvider(Provider):
    """SMS through an old Android phone running the open-source 'SMS Gateway for
    Android' app (https://github.com/capcom6/android-sms-gateway).

    Why: in India, every cloud SMS provider needs TRAI DLT registration (entity +
    header + approved template, about a week and Rs 5,900). A spare phone with a
    Rs 200 prepaid SIM sends up to ~100 SMS/day from a number the family already
    recognises, with no registration. Point ``url`` at the phone's local API
    (http://<phone-ip>:8080) or at the app's cloud relay (https://api.sms-gate.app/3rdparty/v1).
    """

    name = "smsgate"
    methods = ("sms",)

    def can_reach(self, contact: Contact, method: Method) -> bool:
        return method == "sms" and bool(contact.channels.sms) and bool(self.settings.get("url"))

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        body = f"{msg.title}\n{msg.body}" + (f"\n{msg.url}" if msg.url else "")
        payload = {"message": body[:1000], "phoneNumbers": [contact.channels.sms], "priority": 100 if msg.is_emergency else 0}
        try:
            r = await self.client.post(
                self.settings["url"].rstrip("/") + "/message",
                json=payload,
                auth=(self.settings.get("username", ""), self.settings.get("password", "")),
                timeout=TIMEOUT,
            )
            return DeliveryResult(r.status_code < 300, self.name, f"HTTP {r.status_code} {r.text[:120]}")
        except httpx.HTTPError as e:
            return DeliveryResult(False, self.name, repr(e))


class TelegramProvider(Provider):
    """Telegram bot message. Cannot override DND, but it is free, instant, and a
    good second channel for the group chat of responders."""

    name = "telegram"
    methods = ("telegram",)

    def can_reach(self, contact: Contact, method: Method) -> bool:
        return method == "telegram" and bool(contact.channels.telegram_chat_id) and bool(self.settings.get("bot_token"))

    async def send(self, contact: Contact, method: Method, msg: Message) -> DeliveryResult:
        text = f"*{_md(msg.title)}*\n{_md(msg.body)}" + (f"\n[Open incident]({msg.url})" if msg.url else "")
        try:
            r = await self.client.post(
                f"https://api.telegram.org/bot{self.settings['bot_token']}/sendMessage",
                json={"chat_id": contact.channels.telegram_chat_id, "text": text, "parse_mode": "Markdown", "disable_notification": False},
                timeout=TIMEOUT,
            )
            return DeliveryResult(r.status_code < 300, self.name, f"HTTP {r.status_code} {r.text[:120]}")
        except httpx.HTTPError as e:
            return DeliveryResult(False, self.name, repr(e))


def _xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md(s: str) -> str:
    for ch in "_*[]`":
        s = s.replace(ch, "\\" + ch)
    return s


PROVIDER_CLASSES: dict[str, type[Provider]] = {
    "console": ConsoleProvider,
    "ntfy": NtfyProvider,
    "pushover": PushoverProvider,
    "twilio": TwilioProvider,
    "msg91": Msg91Provider,
    "smsgate": SmsGateProvider,
    "exotel": ExotelProvider,
    "telegram": TelegramProvider,
}


def build_providers(settings: ProviderSettings, client: httpx.AsyncClient) -> list[Provider]:
    out: list[Provider] = []
    for name, cls in PROVIDER_CLASSES.items():
        cfg = getattr(settings, name)
        if cfg is None:
            continue
        out.append(cls(cfg, client))
    return out
