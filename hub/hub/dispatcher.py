"""Escalation engine.

When a button is pressed the hub opens an incident and starts one asyncio task
that walks the escalation ladder from ``config.escalation``:

    t=0s     push + SMS to everyone on the list, lights on
    t=90s    if nobody said "on my way": voice-call the family
    t=180s   if still nobody: voice-call the local responders, repeat every 3 min
    ...

Every step is gated on the live incident state, so as soon as someone
acknowledges from the responder page the remaining "no_ack" rungs are skipped
and everyone is told who is coming.

The engine is deliberately restartable: if the hub process dies mid-incident,
``resume_open_incidents`` re-attaches a ladder walker to every open incident
and continues from wherever the clock says we are.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .config import Config, Contact, EscalationStep, Method
from .db import Database, Incident
from .providers import Message, Provider

log = logging.getLogger("hub.dispatcher")


class Dispatcher:
    def __init__(self, cfg: Config, db: Database, providers: list[Provider], client: httpx.AsyncClient):
        self.cfg = cfg
        self.db = db
        self.providers = providers
        self.client = client
        self._tasks: dict[str, asyncio.Task] = {}
        self._tz = ZoneInfo(cfg.hub.timezone)

    # ------------------------------------------------------------------ utils
    def _fmt_time(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, self._tz).strftime("%I:%M %p, %d %b")

    def responder_url(self, incident_id: str) -> str:
        return f"{self.cfg.hub.base_url.rstrip('/')}/i/{incident_id}?t={self.cfg.hub.responder_token}"

    def _providers_for(self, contact: Contact, method: Method) -> list[Provider]:
        return [p for p in self.providers if method in p.methods and p.can_reach(contact, method)]

    async def deliver(self, contact: Contact, method: Method, msg: Message, incident_id: str | None, step: str | None) -> bool:
        """Try every provider able to reach this contact by this method. Returns True if any succeeded."""
        provs = self._providers_for(contact, method)
        if not provs:
            self.db.log_delivery(incident_id, step, contact.id, method, "-", False, "no provider configured for this contact/method")
            return False
        results = await asyncio.gather(*(p.send(contact, method, msg) for p in provs), return_exceptions=True)
        any_ok = False
        for p, res in zip(provs, results):
            if isinstance(res, BaseException):
                self.db.log_delivery(incident_id, step, contact.id, method, p.name, False, repr(res))
                log.exception("provider %s crashed", p.name, exc_info=res)
                continue
            self.db.log_delivery(incident_id, step, contact.id, method, p.name, res.ok, res.detail)
            any_ok = any_ok or res.ok
            if not res.ok:
                log.warning("delivery failed: %s via %s to %s: %s", method, p.name, contact.id, res.detail)
        return any_ok

    async def fan_out(self, contact_ids: list[str], methods: list[Method], msg: Message, incident_id: str | None, step: str | None) -> None:
        jobs = []
        for cid in contact_ids:
            try:
                contact = self.cfg.contact(cid)
            except KeyError:
                log.error("unknown contact %s in step %s", cid, step)
                continue
            for m in methods:
                jobs.append(self.deliver(contact, m, msg, incident_id, step))
        if jobs:
            await asyncio.gather(*jobs)

    # --------------------------------------------------------------- messages
    def build_alert_message(self, inc: Incident, step: EscalationStep | None = None) -> Message:
        dev = self.cfg.device(inc.device_id)
        room = dev.label if dev else inc.device_id
        person = dev.person if dev else "someone"
        home = self.cfg.home
        when = self._fmt_time(inc.opened_at)
        test = inc.kind == "test"
        title = ("[TEST] " if test else "🚨 EMERGENCY: ") + f"{person} pressed the panic button"
        lines = [f"{room} at {home.name}, {when}."]
        if home.address:
            lines.append(f"Address: {home.address}")
        if home.maps_url:
            lines.append(f"Map: {home.maps_url}")
        if home.landmark_directions:
            lines.append(f"Directions: {home.landmark_directions}")
        if step and step.only_if == "no_ack":
            mins = int((time.time() - inc.opened_at) // 60)
            lines.insert(0, f"⚠️ {mins} min passed and NOBODY has responded yet.")
        lines.append("Open the link, press 'On my way' so others know.")
        voice = (
            ("This is a test of the home emergency system. " if test else "Emergency at home. ")
            + f"{person} has pressed the panic button in {room}. Please check your phone and respond now."
        )
        return Message(
            title=title,
            body="\n".join(lines),
            url=self.responder_url(inc.id),
            priority="high" if test else "emergency",
            tags=["rotating_light", "sos"] if not test else ["white_check_mark"],
            voice_script=voice,
        )

    def build_ack_message(self, inc: Incident, by: Contact, status: str, eta: int | None) -> Message:
        dev = self.cfg.device(inc.device_id)
        room = dev.label if dev else inc.device_id
        text = {
            "seen": f"{by.name} has seen the alert.",
            "on_my_way": f"{by.name} is ON THE WAY" + (f" (ETA ~{eta} min)." if eta else "."),
            "arrived": f"{by.name} has ARRIVED at the house.",
            "cannot_come": f"{by.name} cannot come. Someone else must go.",
        }[status]
        return Message(title=f"Update: {room}", body=text, url=self.responder_url(inc.id), priority="high", tags=["information_source"])

    def build_resolved_message(self, inc: Incident, by: str, note: str | None) -> Message:
        dev = self.cfg.device(inc.device_id)
        room = dev.label if dev else inc.device_id
        body = f"Incident in {room} marked resolved by {by}." + (f" Note: {note}" if note else "")
        return Message(title="Resolved", body=body, url=self.responder_url(inc.id), priority="normal", tags=["white_check_mark"])

    # ----------------------------------------------------------------- actions
    async def run_actions(self, inc: Incident) -> None:
        """Fire side effects like turning on the room lights via Home Assistant."""
        dev = self.cfg.device(inc.device_id)
        payload = {"incident": inc.id, "device_id": inc.device_id, "device": dev.label if dev else inc.device_id, "person": dev.person if dev else "", "url": self.responder_url(inc.id)}
        for a in self.cfg.actions:
            try:
                if a.method == "POST":
                    r = await self.client.post(a.url, headers=a.headers, json={**payload, **(a.body or {})}, timeout=10)
                else:
                    r = await self.client.get(a.url, headers=a.headers, timeout=10)
                self.db.log_delivery(inc.id, "action", a.name, "console", "webhook", r.status_code < 300, f"HTTP {r.status_code}")
            except Exception as e:  # noqa: BLE001 - never let an action kill the fan-out
                self.db.log_delivery(inc.id, "action", a.name, "console", "webhook", False, repr(e))
                log.warning("action %s failed: %r", a.name, e)

    # ---------------------------------------------------------------- ladder
    def _all_contacts_in_ladder(self) -> list[str]:
        seen: list[str] = []
        for s in self.cfg.escalation:
            for c in s.contacts:
                if c not in seen:
                    seen.append(c)
        return seen

    def _step_applies(self, inc: Incident, step: EscalationStep) -> bool:
        if inc.kind == "test" and "voice" in step.methods and step.only_if != "always":
            return False  # never ring people's phones at night for a test
        if step.only_if == "no_ack":
            return not inc.is_acked
        if step.only_if == "no_arrival":
            return not self.db.has_arrival(inc.id)
        return True

    async def _walk_ladder(self, incident_id: str) -> None:
        steps = sorted(self.cfg.escalation, key=lambda s: s.at_s)
        # Each step has its own "next fire time"; repeating steps re-arm themselves.
        schedule: list[tuple[float, int, EscalationStep]] = []
        for s in steps:
            schedule.append((s.at_s, 0, s))
        inc = self.db.get_incident(incident_id)
        if inc is None:
            return
        t0 = inc.opened_at
        while schedule:
            schedule.sort(key=lambda x: x[0])
            fire_at, n, step = schedule.pop(0)
            delay = t0 + fire_at - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
            inc = self.db.get_incident(incident_id)
            if inc is None or not inc.is_open:
                return
            if self._step_applies(inc, step):
                log.info("incident %s: firing step '%s' (repeat %d)", incident_id, step.name, n)
                await self.fan_out(step.contacts, step.methods, self.build_alert_message(inc, step), incident_id, step.name)
            if step.repeat_every_s and n + 1 < step.max_repeats:
                schedule.append((fire_at + step.repeat_every_s, n + 1, step))
        log.info("incident %s: ladder exhausted", incident_id)

    def start_ladder(self, incident_id: str) -> None:
        if incident_id in self._tasks and not self._tasks[incident_id].done():
            return
        self._tasks[incident_id] = asyncio.create_task(self._walk_ladder(incident_id), name=f"ladder-{incident_id}")

    def resume_open_incidents(self) -> int:
        n = 0
        for inc in self.db.open_incidents():
            self.start_ladder(inc.id)
            n += 1
        return n

    # ------------------------------------------------------------ public API
    async def open_incident(self, device_id: str, kind: str, extra: dict) -> Incident:
        inc = self.db.open_incident(device_id, kind, extra)
        log.warning("INCIDENT %s opened: device=%s kind=%s", inc.id, device_id, kind)
        if kind != "test":
            asyncio.create_task(self.run_actions(inc))
        self.start_ladder(inc.id)
        return inc

    async def acknowledge(self, inc: Incident, contact: Contact, status: str, eta: int | None, note: str | None) -> None:
        self.db.ack_incident(inc.id, contact.id, status, eta, note)
        inc = self.db.get_incident(inc.id) or inc
        msg = self.build_ack_message(inc, contact, status, eta)
        others = [c for c in self._all_contacts_in_ladder() if c != contact.id]
        await self.fan_out(others, ["push", "telegram"], msg, inc.id, f"ack:{status}")

    async def resolve(self, inc: Incident, by: str, note: str | None) -> None:
        self.db.resolve_incident(inc.id, by, note)
        task = self._tasks.pop(inc.id, None)
        if task and not task.done():
            task.cancel()
        inc = self.db.get_incident(inc.id) or inc
        await self.fan_out(self._all_contacts_in_ladder(), ["push", "telegram"], self.build_resolved_message(inc, by, note), inc.id, "resolved")

    # --------------------------------------------------------------- watchdog
    async def watchdog_loop(self) -> None:
        """Mark devices offline when their heartbeat stops and tell the admins.

        A silent button is a broken button. This is a *low* priority alert (no
        siren), but it must never be ignored: it means the room has no coverage.
        """
        interval = self.cfg.hub.watchdog_interval_s
        while True:
            try:
                states = self.db.device_states()
                now = time.time()
                for dev in self.cfg.devices:
                    st = states.get(dev.id)
                    if st is None or st["last_seen"] is None:
                        continue  # never seen; nothing to compare against
                    if st["online"] and now - st["last_seen"] > dev.heartbeat_timeout_s:
                        self.db.mark_offline(dev.id)
                        mins = int((now - st["last_seen"]) // 60)
                        msg = Message(
                            title=f"⚠️ {dev.label} button OFFLINE",
                            body=f"No heartbeat from '{dev.label}' for {mins} min. Check power / Wi-Fi / router UPS. The room has NO panic coverage until this is fixed.",
                            priority="high",
                            tags=["warning"],
                        )
                        await self.fan_out(self.cfg.hub.offline_alert_contacts, ["push", "telegram"], msg, None, "watchdog")
            except Exception:  # noqa: BLE001
                log.exception("watchdog iteration failed")
            await asyncio.sleep(interval)

    async def device_back_online(self, device_id: str) -> None:
        dev = self.cfg.device(device_id)
        label = dev.label if dev else device_id
        msg = Message(title=f"✅ {label} button back online", body="Heartbeat resumed.", priority="normal", tags=["white_check_mark"])
        await self.fan_out(self.cfg.hub.offline_alert_contacts, ["push", "telegram"], msg, None, "watchdog")
