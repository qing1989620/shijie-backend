"""回归：同一课堂重开录音会话，sequence 必须续接（曾因 UNIQUE 约束报"连接错误"）。

运行：python scripts/ws_reconnect_regression.py
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
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'reconnect.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def record_session(c, headers, lesson_id, n_chunks):
    ticket = c.post("/api/v1/realtime/tickets", headers=headers, json={"lesson_id": lesson_id}).json()["ticket"]
    finals = []
    with c.websocket_connect(f"/ws/v1/lessons/{lesson_id}/transcription") as ws:
        ws.send_json({"type": "session.start", "version": 1, "payload": {"ticket": ticket}})
        deadline = time.time() + 10
        while time.time() < deadline:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "session.ready":
                break
        for _ in range(n_chunks):
            ws.send_json({"type": "audio.chunk", "version": 1, "payload": {}})
        got, deadline = 0, time.time() + 10
        while got < n_chunks and time.time() < deadline:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "error":
                raise AssertionError(f"error envelope: {msg['payload']}")
            if msg["type"] in {"transcript.partial", "transcript.final"}:
                got += 1
                if msg["type"] == "transcript.final":
                    finals.append(msg["payload"]["sequence"])
        ws.send_json({"type": "session.end", "version": 1, "payload": {}})
    return finals


def main() -> None:
    Base.metadata.create_all(engine)
    email = f"reconnect-{uuid.uuid4().hex[:6]}@test.dev"
    c = TestClient(app)
    c.post("/api/v1/auth/register", json={"email": email, "password": "password123", "display_name": "R"})
    tok = c.post("/api/v1/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    lesson = c.post("/api/v1/lessons", headers=h, json={"title": "重连回归"}).json()

    s1 = record_session(c, h, lesson["id"], 3)
    s2 = record_session(c, h, lesson["id"], 3)
    tr = c.get(f"/api/v1/lessons/{lesson['id']}/transcript", headers=h).json()
    seqs = [s["sequence"] for s in tr["items"]]
    assert s1 and s2, "两次会话都必须产出 final 片段"
    assert len(set(seqs)) == len(seqs), "sequence 不得重复"
    assert len(seqs) == len(s1) + len(s2), "第二次会话的片段应全部落库"
    print(f"RECONNECT REGRESSION: PASS (session1={s1}, session2={s2}, persisted={seqs})")


if __name__ == "__main__":
    main()
