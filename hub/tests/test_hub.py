"""End-to-end tests of the hub with the console provider and a fast ladder."""
from __future__ import annotations

import asyncio
import textwrap
import time

import pytest
from httpx import ASGITransport, AsyncClient

from hub import dispatcher as dispatcher_mod
from hub.main import create_app
from hub.providers import ConsoleProvider

DEVICE_TOKEN = "device-token-0123456789abcdef"
RESP_TOKEN = "responder-token-0123456789abcdef"


@pytest.fixture
def config_file(tmp_path):
    cfg = textwrap.dedent(
        f"""
        hub:
          base_url: http://test
          device_token: {DEVICE_TOKEN}
          responder_token: {RESP_TOKEN}
          db_path: {tmp_path / 'hub.sqlite3'}
          watchdog_interval_s: 1
          offline_alert_contacts: [me]
        home:
          name: Test house
          address: 1 Test Lane
        devices:
          - {{id: mom, label: "Mom's room", person: Mom, heartbeat_timeout_s: 1}}
        contacts:
          - {{id: me, name: Me, role: family, channels: {{sms: "+910000000000"}}}}
          - {{id: nb, name: Neighbour, role: responder, eta_minutes: 3}}
        escalation:
          - {{name: t0, at_s: 0, contacts: [me, nb], methods: [push, sms]}}
          - {{name: t1, at_s: 1, only_if: no_ack, contacts: [me], methods: [voice], repeat_every_s: 1, max_repeats: 3}}
        providers:
          console: {{}}
        """
    )
    p = tmp_path / "config.yaml"
    p.write_text(cfg)
    return p


@pytest.fixture
async def client(config_file):
    ConsoleProvider.sent = []
    app = create_app(str(config_file))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


def sent(method: str | None = None):
    return [s for s in ConsoleProvider.sent if method is None or s[1] == method]


async def test_rejects_bad_token(client):
    r = await client.post("/api/v1/alert", json={"device_id": "mom"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    r = await client.get("/api/v1/incidents/x?t=nope")
    assert r.status_code == 401


async def test_panic_fans_out_then_escalates_then_stops_on_ack(client):
    r = await client.post("/api/v1/alert", json={"device_id": "mom", "extra": {"battery": 88}}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
    assert r.status_code == 200, r.text
    iid = r.json()["incident_id"]
    assert not r.json()["duplicate"]
    await asyncio.sleep(0.2)
    # t0: push+sms to me and nb (4 deliveries)
    assert {(s[0], s[1]) for s in sent()} == {("me", "push"), ("me", "sms"), ("nb", "push"), ("nb", "sms")}
    assert "Mom pressed the panic button" in sent()[0][2].title
    assert sent()[0][2].url.endswith(f"/i/{iid}?t={RESP_TOKEN}")

    # duplicate press within the window returns the same incident
    r2 = await client.post("/api/v1/alert", json={"device_id": "mom"}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
    assert r2.json() == {"incident_id": iid, "duplicate": True, "responder_url": r.json()["responder_url"]}

    # t1: voice to me because nobody acked
    await asyncio.sleep(1.2)
    assert len(sent("voice")) == 1
    assert "NOBODY has responded" in sent("voice")[0][2].body

    # neighbour says on my way -> others notified, voice repeats stop
    r = await client.post(f"/api/v1/incidents/{iid}/ack?t={RESP_TOKEN}", json={"contact_id": "nb", "status": "on_my_way", "eta_minutes": 3})
    assert r.status_code == 200
    assert r.json()["incident"]["acked_at"] is not None
    await asyncio.sleep(0.2)
    ack_msgs = [s for s in sent() if s[2].title.startswith("Update")]
    assert ack_msgs and ack_msgs[0][0] == "me" and "ON THE WAY" in ack_msgs[0][2].body
    voice_before = len(sent("voice"))
    await asyncio.sleep(1.5)
    assert len(sent("voice")) == voice_before, "escalation must stop after acknowledgement"

    # resolve
    r = await client.post(f"/api/v1/incidents/{iid}/resolve?t={RESP_TOKEN}", json={"contact_id": "me", "note": "false alarm"})
    assert r.json()["incident"]["resolved_at"] is not None
    assert any(s[2].title == "Resolved" for s in sent())
    r = await client.get(f"/api/v1/incidents/{iid}?t={RESP_TOKEN}")
    assert r.json()["deliveries"]


async def test_test_alert_never_voice_calls(client):
    r = await client.post("/api/v1/alert", json={"device_id": "mom", "kind": "test"}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
    assert r.status_code == 200
    await asyncio.sleep(1.4)
    assert sent("voice") == []
    assert all(s[2].title.startswith("[TEST]") for s in sent() if s[2].title != "Resolved")


async def test_cancel_within_grace(client):
    r = await client.post("/api/v1/alert", json={"device_id": "mom"}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
    iid = r.json()["incident_id"]
    r = await client.post("/api/v1/cancel", json={"device_id": "mom"}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
    assert r.status_code == 200 and r.json()["incident_id"] == iid
    r = await client.get(f"/api/v1/incidents/{iid}?t={RESP_TOKEN}")
    assert r.json()["incident"]["resolved_by"].startswith("device")


async def test_watchdog_marks_offline_and_recovers(client):
    r = await client.post("/api/v1/heartbeat", json={"device_id": "mom", "extra": {"rssi": -60}}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
    assert r.json()["ok"] and r.json()["open_incident"] is None
    r = await client.get(f"/api/v1/status?t={RESP_TOKEN}")
    assert r.json()["devices"][0]["online"] is True
    await asyncio.sleep(2.5)  # timeout is 1 s, watchdog runs every 1 s
    offline = [s for s in sent() if "OFFLINE" in s[2].title]
    assert offline and offline[0][0] == "me"
    r = await client.get(f"/api/v1/status?t={RESP_TOKEN}")
    assert r.json()["devices"][0]["online"] is False
    r = await client.post("/api/v1/heartbeat", json={"device_id": "mom"}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
    await asyncio.sleep(0.2)
    assert any("back online" in s[2].title for s in sent())


async def test_resume_after_restart(config_file, tmp_path):
    """An open incident survives a hub restart and keeps escalating."""
    ConsoleProvider.sent = []
    app = create_app(str(config_file))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/alert", json={"device_id": "mom"}, headers={"Authorization": f"Bearer {DEVICE_TOKEN}"})
            iid = r.json()["incident_id"]
            await asyncio.sleep(0.1)
    # "crash" here: new app on the same DB
    ConsoleProvider.sent = []
    app2 = create_app(str(config_file))
    async with app2.router.lifespan_context(app2):
        assert len(app2.state.hub.db.open_incidents()) == 1
        await asyncio.sleep(1.5)
        assert sent("voice"), "ladder must resume after restart"
        async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as c:
            await c.post(f"/api/v1/incidents/{iid}/resolve?t={RESP_TOKEN}", json={"contact_id": "me"})


def test_config_rejects_unknown_contact(tmp_path):
    from hub.config import load_config

    p = tmp_path / "bad.yaml"
    p.write_text(textwrap.dedent(f"""
        hub: {{device_token: {DEVICE_TOKEN}, responder_token: {RESP_TOKEN}}}
        devices: [{{id: a, label: A, person: A}}]
        contacts: [{{id: me, name: Me, role: family}}]
        escalation: [{{name: t0, contacts: [ghost], methods: [push]}}]
    """))
    with pytest.raises(ValueError, match="ghost"):
        load_config(p)
