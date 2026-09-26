"""Configuration model for the alert hub.

Everything the hub needs to know about the house, the people, the buttons and the
escalation ladder lives in one YAML file (see ``config.example.yaml``). This module
validates it at start-up so a typo in a phone number is caught when the service
starts, not at 2 a.m. when the button is pressed.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

Method = Literal["push", "sms", "voice", "telegram", "whatsapp", "console"]


class Hospital(BaseModel):
    name: str
    phone: str | None = None
    maps_url: str | None = None
    drive_minutes: int | None = None
    notes: str | None = None  # e.g. "24x7 cath lab, stroke unit"


class Home(BaseModel):
    name: str = "Home"
    address: str = ""
    plus_code: str | None = None
    maps_url: str | None = None
    landmark_directions: str | None = None  # how a driver actually finds the gate
    nearest_hospitals: list[Hospital] = Field(default_factory=list)
    oxygen_note: str | None = None  # where the concentrator / cylinder are


class Device(BaseModel):
    id: str
    label: str  # "Mom's room"
    person: str  # who normally presses it
    heartbeat_timeout_s: int = 300


class ContactChannels(BaseModel):
    ntfy_topic: str | None = None
    pushover_user_key: str | None = None
    sms: str | None = None  # E.164, e.g. +91XXXXXXXXXX
    voice: str | None = None  # E.164
    telegram_chat_id: str | None = None
    whatsapp: str | None = None  # E.164


class Contact(BaseModel):
    id: str
    name: str
    role: Literal["family", "parent", "responder", "doctor", "driver", "admin"]
    channels: ContactChannels = Field(default_factory=ContactChannels)
    eta_minutes: int | None = None  # rough time to reach the house
    notes: str | None = None


class EscalationStep(BaseModel):
    """One rung of the ladder.

    ``at_s`` is seconds after the incident opened. ``only_if`` gates the step on the
    incident state at that moment. ``repeat_every_s`` re-fires the step until the
    incident is acknowledged/resolved or ``max_repeats`` is hit.
    """

    name: str
    at_s: int = 0
    contacts: list[str]
    methods: list[Method]
    only_if: Literal["always", "no_ack", "no_arrival"] = "always"
    repeat_every_s: int | None = None
    max_repeats: int = 10


class Action(BaseModel):
    """A side-effect to run when an incident opens: lights, sirens, etc."""

    name: str
    type: Literal["webhook"]
    url: str
    method: Literal["POST", "GET"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None


class ProviderSettings(BaseModel):
    ntfy: dict[str, Any] | None = None
    pushover: dict[str, Any] | None = None
    twilio: dict[str, Any] | None = None
    msg91: dict[str, Any] | None = None
    smsgate: dict[str, Any] | None = None
    exotel: dict[str, Any] | None = None
    telegram: dict[str, Any] | None = None
    console: dict[str, Any] | None = None


class HubSettings(BaseModel):
    base_url: str = "http://localhost:8000"
    device_token: str
    responder_token: str
    timezone: str = "Asia/Kolkata"
    db_path: str = "hub.sqlite3"
    watchdog_interval_s: int = 30
    offline_alert_contacts: list[str] = Field(default_factory=list)
    test_contacts: list[str] = Field(default_factory=list)

    @field_validator("device_token", "responder_token")
    @classmethod
    def _not_placeholder(cls, v: str) -> str:
        if len(v) < 16 or "CHANGE" in v.upper():
            raise ValueError("tokens must be at least 16 random characters")
        return v


class Config(BaseModel):
    hub: HubSettings
    home: Home = Field(default_factory=Home)
    devices: list[Device]
    contacts: list[Contact]
    escalation: list[EscalationStep]
    actions: list[Action] = Field(default_factory=list)
    providers: ProviderSettings = Field(default_factory=ProviderSettings)

    @model_validator(mode="after")
    def _cross_check(self) -> "Config":
        contact_ids = {c.id for c in self.contacts}
        for step in self.escalation:
            unknown = set(step.contacts) - contact_ids
            if unknown:
                raise ValueError(f"escalation step '{step.name}' references unknown contacts {sorted(unknown)}")
        for cid in self.hub.offline_alert_contacts + self.hub.test_contacts:
            if cid not in contact_ids:
                raise ValueError(f"hub references unknown contact '{cid}'")
        if len({d.id for d in self.devices}) != len(self.devices):
            raise ValueError("device ids must be unique")
        if len(contact_ids) != len(self.contacts):
            raise ValueError("contact ids must be unique")
        return self

    def contact(self, cid: str) -> Contact:
        for c in self.contacts:
            if c.id == cid:
                return c
        raise KeyError(cid)

    def device(self, did: str) -> Device | None:
        for d in self.devices:
            if d.id == did:
                return d
        return None


def _expand_env(node: Any) -> Any:
    """Allow ``${ENV_VAR}`` in string values so secrets stay out of the YAML file."""
    if isinstance(node, dict):
        return {k: _expand_env(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_env(v) for v in node]
    if isinstance(node, str):
        return os.path.expandvars(node)
    return node


def load_config(path: str | Path) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Config.model_validate(_expand_env(raw))
