"""WebSocket realtime contract smoke (AsyncAPI envelope + transcript persistence).

Run with a live backend:  python scripts/ws_smoke.py  (default http://localhost:8000)
Verified via standalone script because pytest+TestClient WebSocket portals hang
under this environment (documented in docs/testing/TEST_PLAN.md).
"""
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if os.environ.get("DATABASE_URL", "").startswith("sqlite:///data"):
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'ws-smoke.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def main() -> None:
    Base.metadata.create_all(engine)
    email = f"ws-smoke-{uuid.uuid4().hex[:6]}@test.dev"
    with TestClient(app) as c:
        c.post("/api/v1/auth/register", json={"email": email, "password": "password123", "display_name": "WS"})
        tok = c.post("/api/v1/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        lesson = c.post("/api/v1/lessons", headers=h, json={"title": "WS 冒烟"}).json()
        ticket = c.post("/api/v1/realtime/tickets", headers=h, json={"lesson_id": lesson["id"]}).json()["ticket"]

        with c.websocket_connect(f"/ws/v1/lessons/{lesson['id']}/transcription") as ws:
            ws.send_json({"type": "session.start", "version": 1, "payload": {"ticket": ticket}})
            ready = _expect(ws, "session.ready")
            assert ready["payload"]["lesson_id"] == lesson["id"]

            # Mock ASR: odd chunk seq -> final, even -> partial
            ws.send_json({"type": "audio.chunk", "version": 1, "payload": {}})
            final = _expect(ws, "transcript.final")
            ws.send_json({"type": "audio.chunk", "version": 1, "payload": {}})
            _expect(ws, "transcript.partial")
            ws.send_json({"type": "audio.chunk", "version": 1, "payload": {}})
            final = _expect(ws, "transcript.final")
            for key in {"type", "version", "session_id", "timestamp", "payload"}:
                assert key in final, f"envelope missing {key}"

            ws.send_json({"type": "bogus.type", "version": 1, "payload": {}})
            assert _expect(ws, "error")["payload"]["code"] == "BAD_REQUEST"

            ws.send_json({"type": "session.end", "version": 1, "payload": {}})
            closed = _expect(ws, "session.closed")
            assert closed["payload"]["segments"] >= 1

        tr = c.get(f"/api/v1/lessons/{lesson['id']}/transcript", headers=h).json()
        assert len(tr["items"]) >= 1
        status = c.get(f"/api/v1/lessons/{lesson['id']}", headers=h).json()["status"]
        assert status == "ready", status
    print("WS SMOKE: PASS (ready -> partial -> final -> error -> closed; segments persisted)")


def _expect(ws, expected: str) -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        msg = json.loads(ws.receive_text())
        if msg.get("type") == expected:
            return msg
        if msg.get("type") == "error":
            raise AssertionError(f"unexpected error: {msg}")
    raise TimeoutError(expected)


if __name__ == "__main__":
    main()
