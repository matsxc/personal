"""FastAPI application: the HTTP face of the alert hub.

Endpoints
---------
Devices (buttons, phone kiosk) authenticate with ``Authorization: Bearer <device_token>``:
    POST /api/v1/alert         open an incident (panic or test)
    POST /api/v1/heartbeat     "I'm alive" every ~60 s
    POST /api/v1/cancel        pressed by mistake, within the grace window

Responders authenticate with the ``t`` query parameter (responder_token), which is
embedded in every alert link so nobody has to log in at 2 a.m.:
    GET  /i/{incident_id}                       responder page (HTML)
    GET  /api/v1/incidents/{id}                 incident JSON
    POST /api/v1/incidents/{id}/ack             seen / on_my_way / arrived / cannot_come
    POST /api/v1/incidents/{id}/resolve
    GET  /api/v1/status                         devices + open incidents
    GET  /api/v1/playbooks                      emergency checklists
    GET  /healthz                               liveness
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Config, load_config
from .db import Database
from .dispatcher import Dispatcher
from .providers import build_providers

log = logging.getLogger("hub")
HERE = Path(__file__).parent
STATIC_DIR = HERE / "static"
PLAYBOOKS_PATH = Path(os.environ.get("HUB_PLAYBOOKS", HERE / "playbooks.yaml"))

# A press within this many seconds of an open incident on the same device is a
# repeat press, not a new incident (people mash buttons when scared).
DUPLICATE_WINDOW_S = 120
# A device may cancel its own incident this soon after opening ("pressed by mistake").
CANCEL_GRACE_S = 20


# ---------------------------------------------------------------- request models
class AlertIn(BaseModel):
    device_id: str
    kind: Literal["panic", "test"] = "panic"
    extra: dict[str, Any] = Field(default_factory=dict)

class HeartbeatIn(BaseModel):
    device_id: str
    extra: dict[str, Any] = Field(default_factory=dict)

class CancelIn(BaseModel):
    device_id: str

class AckIn(BaseModel):
    contact_id: str
    status: Literal["seen", "on_my_way", "arrived", "cannot_come"]
    eta_minutes: int | None = None
    note: str | None = None

class ResolveIn(BaseModel):
    contact_id: str
    note: str | None = None



class State:
    cfg: Config
    db: Database
    dispatcher: Dispatcher
    client: httpx.AsyncClient
    playbooks: dict[str, Any]
    watchdog: asyncio.Task | None = None


def create_app(config_path: str | None = None) -> FastAPI:
    config_path = config_path or os.environ.get("HUB_CONFIG", "config.yaml")
    state = State()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.cfg = load_config(config_path)
        state.db = Database(state.cfg.hub.db_path)
        state.client = httpx.AsyncClient()
        state.dispatcher = Dispatcher(state.cfg, state.db, build_providers(state.cfg.providers, state.client), state.client)
        state.playbooks = yaml.safe_load(PLAYBOOKS_PATH.read_text(encoding="utf-8")) if PLAYBOOKS_PATH.exists() else {}
        resumed = state.dispatcher.resume_open_incidents()
        if resumed:
            log.warning("resumed %d open incident(s) after restart", resumed)
        state.watchdog = asyncio.create_task(state.dispatcher.watchdog_loop(), name="watchdog")
        log.info("hub ready: %d devices, %d contacts, %d escalation steps", len(state.cfg.devices), len(state.cfg.contacts), len(state.cfg.escalation))
        try:
            yield
        finally:
            if state.watchdog:
                state.watchdog.cancel()
            await state.client.aclose()
            state.db.close()

    app = FastAPI(title="Home Emergency Alert Hub", lifespan=lifespan)
    app.state.hub = state
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ------------------------------------------------------------------ auth
    def device_auth(request: Request) -> None:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
        if not secrets.compare_digest(token, state.cfg.hub.device_token):
            raise HTTPException(401, "bad device token")

    def responder_auth(t: str = Query(default="")) -> None:
        if not secrets.compare_digest(t, state.cfg.hub.responder_token):
            raise HTTPException(401, "bad responder token")

    # ------------------------------------------------------------- devices
    @app.post("/api/v1/alert", dependencies=[Depends(device_auth)])
    async def alert(body: AlertIn):
        if state.cfg.device(body.device_id) is None:
            raise HTTPException(404, f"unknown device {body.device_id}")
        state.db.heartbeat(body.device_id, body.extra)
        existing = state.db.latest_open_for_device(body.device_id, DUPLICATE_WINDOW_S)
        if existing and existing.kind == body.kind:
            return {"incident_id": existing.id, "duplicate": True, "responder_url": state.dispatcher.responder_url(existing.id)}
        inc = await state.dispatcher.open_incident(body.device_id, body.kind, body.extra)
        return {"incident_id": inc.id, "duplicate": False, "responder_url": state.dispatcher.responder_url(inc.id)}

    @app.post("/api/v1/heartbeat", dependencies=[Depends(device_auth)])
    async def heartbeat(body: HeartbeatIn):
        if state.cfg.device(body.device_id) is None:
            raise HTTPException(404, f"unknown device {body.device_id}")
        was_offline = state.db.heartbeat(body.device_id, body.extra)
        if was_offline:
            asyncio.create_task(state.dispatcher.device_back_online(body.device_id))
        open_inc = state.db.latest_open_for_device(body.device_id, 24 * 3600)
        # The device uses this to keep its LED/buzzer in "alert active" mode until resolved.
        return {"ok": True, "server_time": time.time(), "open_incident": open_inc.id if open_inc else None, "acked": bool(open_inc and open_inc.is_acked)}

    @app.post("/api/v1/cancel", dependencies=[Depends(device_auth)])
    async def cancel(body: CancelIn):
        inc = state.db.latest_open_for_device(body.device_id, CANCEL_GRACE_S)
        if inc is None:
            raise HTTPException(409, "no incident within the cancel window; ask a responder to resolve it")
        await state.dispatcher.resolve(inc, "device (cancelled at the button)", "Cancelled at the button within the grace window.")
        return {"ok": True, "incident_id": inc.id}

    # ---------------------------------------------------------- responders
    def _incident_or_404(iid: str):
        inc = state.db.get_incident(iid)
        if inc is None:
            raise HTTPException(404, "no such incident")
        return inc

    def _incident_payload(inc) -> dict[str, Any]:
        dev = state.cfg.device(inc.device_id)
        return {
            "incident": inc.to_dict(),
            "device": dev.model_dump() if dev else {"id": inc.device_id, "label": inc.device_id, "person": "?"},
            "home": state.cfg.home.model_dump(),
            "acks": state.db.acks_for(inc.id),
            "deliveries": state.db.deliveries_for(inc.id),
            "contacts": [
                {"id": c.id, "name": c.name, "role": c.role, "eta_minutes": c.eta_minutes, "phone": c.channels.voice or c.channels.sms}
                for c in state.cfg.contacts
            ],
            "server_time": time.time(),
        }

    @app.get("/api/v1/incidents/{iid}", dependencies=[Depends(responder_auth)])
    async def get_incident(iid: str):
        return _incident_payload(_incident_or_404(iid))

    @app.post("/api/v1/incidents/{iid}/ack", dependencies=[Depends(responder_auth)])
    async def ack(iid: str, body: AckIn):
        inc = _incident_or_404(iid)
        if not inc.is_open:
            raise HTTPException(409, "incident already resolved")
        try:
            contact = state.cfg.contact(body.contact_id)
        except KeyError:
            raise HTTPException(404, "unknown contact") from None
        await state.dispatcher.acknowledge(inc, contact, body.status, body.eta_minutes, body.note)
        return _incident_payload(_incident_or_404(iid))

    @app.post("/api/v1/incidents/{iid}/resolve", dependencies=[Depends(responder_auth)])
    async def resolve(iid: str, body: ResolveIn):
        inc = _incident_or_404(iid)
        if not inc.is_open:
            return _incident_payload(inc)
        try:
            contact = state.cfg.contact(body.contact_id)
        except KeyError:
            raise HTTPException(404, "unknown contact") from None
        await state.dispatcher.resolve(inc, contact.name, body.note)
        return _incident_payload(_incident_or_404(iid))

    @app.get("/api/v1/status", dependencies=[Depends(responder_auth)])
    async def status():
        states = state.db.device_states()
        now = time.time()
        devices = []
        for d in state.cfg.devices:
            st = states.get(d.id, {"last_seen": None, "online": False, "extra": {}})
            devices.append({
                **d.model_dump(),
                "last_seen": st["last_seen"],
                "seconds_since_seen": (now - st["last_seen"]) if st["last_seen"] else None,
                "online": st["online"] and st["last_seen"] is not None and (now - st["last_seen"]) <= d.heartbeat_timeout_s,
                "extra": st["extra"],
            })
        return {"devices": devices, "open_incidents": [i.to_dict() for i in state.db.open_incidents()], "recent": [i.to_dict() for i in state.db.recent_incidents(20)]}

    @app.get("/api/v1/playbooks", dependencies=[Depends(responder_auth)])
    async def playbooks():
        return state.playbooks

    @app.get("/i/{iid}", response_class=HTMLResponse, dependencies=[Depends(responder_auth)])
    async def responder_page(iid: str):
        _incident_or_404(iid)
        return HTMLResponse((STATIC_DIR / "responder.html").read_text(encoding="utf-8"))

    @app.get("/kiosk", response_class=HTMLResponse)
    async def kiosk_page():
        return HTMLResponse((STATIC_DIR / "kiosk.html").read_text(encoding="utf-8"))

    @app.get("/healthz")
    async def healthz():
        return JSONResponse({"ok": True, "open_incidents": len(state.db.open_incidents())})

    return app


def run() -> None:  # pragma: no cover - CLI entry point
    import uvicorn

    logging.basicConfig(level=os.environ.get("HUB_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(), host=os.environ.get("HUB_HOST", "0.0.0.0"), port=int(os.environ.get("HUB_PORT", "8000")))


if __name__ == "__main__":  # pragma: no cover
    run()
