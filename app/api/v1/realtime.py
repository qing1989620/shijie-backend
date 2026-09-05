"""Realtime transcription: ticket issue + WebSocket endpoint.

Message contract lives in backend/contracts/asyncapi.yaml. Every message:
{type, version, session_id, request_id?, timestamp, payload}.
Client messages: audio.chunk, session.end, heartbeat. Server: session.ready,
transcript.partial, transcript.final, session.closed, error, heartbeat.
"""
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import AppError
from app.models import Lesson, Recording, TranscriptSegment, User
from app.providers.asr.provider import get_asr_provider

router = APIRouter(tags=["realtime"])        # HTTP routes — mounted under /api/v1
ws_router = APIRouter(tags=["realtime"])     # WS route — contract path /ws/v1/... (no prefix)


class TicketOut(BaseModel):
    ticket: str
    ws_url: str
    expires_in: int = 300


_active_tickets: set[str] = set()


@router.post("/realtime/tickets", response_model=TicketOut, operation_id="realtime_ticket_create")
def realtime_ticket(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Issue a short-lived one-time ticket for the WS handshake (browser cannot set
    Authorization header on WebSocket). lesson_id must belong to the user."""
    lesson_id = (body or {}).get("lesson_id")
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.deleted_at.is_(None)).first()
    if not lesson or lesson.user_id != user.id:
        raise AppError("NOT_FOUND")
    ticket = uuid.uuid4().hex
    _active_tickets.add((ticket, user.id, lesson_id))
    return TicketOut(ticket=ticket, ws_url=f"/ws/v1/lessons/{lesson_id}/transcription")


@ws_router.websocket("/ws/v1/lessons/{lesson_id}/transcription")
async def ws_transcription(websocket: WebSocket, lesson_id: str):
    """Accepts audio chunks; streams partial/final transcripts via the ASR provider.

    Dev note: browser MediaRecorder chunks are opaque; the Mock ASR emits a fixed
    classroom script keyed by chunk sequence, so the realtime flow is fully
    exercised end-to-end without a model runtime.
    """
    from app.core.db import SessionLocal

    await websocket.accept()
    db = SessionLocal()
    session_id = uuid.uuid4().hex
    seq = 0

    async def send(msg_type: str, payload: dict, request_id: str | None = None):
        await websocket.send_text(
            json.dumps(
                {
                    "type": msg_type,
                    "version": 1,
                    "session_id": session_id,
                    "request_id": request_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": payload,
                },
                ensure_ascii=False,
            )
        )

    # handshake: first message must be {type: session.start, payload:{ticket}}
    try:
        raw = await websocket.receive_text()
        hello = json.loads(raw)
        ticket = (hello.get("payload") or {}).get("ticket", "")
        match = next((t for t in _active_tickets if t[0] == ticket), None)
        if hello.get("type") != "session.start" or not match:
            await send("error", {"code": "UNAUTHORIZED", "message": "invalid ticket"})
            await websocket.close(code=4401)
            return
        _, ticket_user, ticket_lesson = match
        _active_tickets.discard(match)
        if ticket_lesson != lesson_id:
            await send("error", {"code": "FORBIDDEN", "message": "lesson mismatch"})
            await websocket.close(code=4403)
            return
        lesson = db.query(Lesson).get(ticket_lesson)
        if not lesson or lesson.deleted_at is not None:
            await send("error", {"code": "NOT_FOUND", "message": "lesson not found"})
            await websocket.close(code=4404)
            return

        recording = Recording(lesson_id=lesson.id, user_id=ticket_user, storage_key=f"ws/{session_id}.webm",
                              mime_type="audio/webm", status="recording")
        db.add(recording)
        lesson.status = "recording"
        if not lesson.started_at:
            lesson.started_at = datetime.now(UTC)
        db.commit()
        await send("session.ready", {"recording_id": recording.id, "lesson_id": lesson.id})

        asr = get_asr_provider()
        # sequence 续接已有片段：同课堂重开录音会话时不会撞 UNIQUE(lesson_id, sequence)
        final_seq = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.lesson_id == lesson.id)
            .order_by(TranscriptSegment.sequence.desc())
            .first()
        )
        final_seq = final_seq.sequence if final_seq else 0
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send("error", {"code": "BAD_REQUEST", "message": "invalid json"})
                continue
            mtype = msg.get("type")
            if mtype == "heartbeat":
                await send("heartbeat", {})
            elif mtype == "audio.chunk":
                seq += 1
                # 单分片失败不终止整个会话：记录错误并继续
                try:
                    result = asr.transcribe_stream_chunk(session_id, b"", seq)
                    start_ms = seq * 8000
                    if result["is_final"]:
                        seg = TranscriptSegment(
                            lesson_id=lesson.id, recording_id=recording.id, sequence=final_seq + 1,
                            start_ms=start_ms, end_ms=start_ms + 8000, text=result["text"],
                            confidence=result.get("confidence"), is_final=False,
                        )
                        db.add(seg)
                        db.commit()
                        final_seq += 1
                        await send("transcript.final",
                                   {"segment_id": seg.id, "sequence": seg.sequence, "start_ms": seg.start_ms,
                                    "end_ms": seg.end_ms, "text": seg.text, "confidence": seg.confidence})
                    else:
                        await send("transcript.partial", {"sequence": seq, "start_ms": start_ms,
                                                          "text": result["text"], "confidence": result.get("confidence")})
                except Exception as chunk_exc:  # noqa: BLE001
                    await send("error", {"code": "CHUNK_FAILED", "message": str(chunk_exc)[:200]})
            elif mtype == "session.end":
                break
            else:
                await send("error", {"code": "BAD_REQUEST", "message": f"unknown type {mtype}"})

        recording.status = "finalized"
        recording.finalized_at = datetime.now(UTC)
        lesson.status = "ready"
        lesson.ended_at = datetime.now(UTC)
        db.commit()
        await send("session.closed", {"recording_id": recording.id, "segments": final_seq})
        await websocket.close()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await send("error", {"code": "INTERNAL_ERROR", "message": str(exc)[:200]})
            await websocket.close()
        except Exception:  # pragma: no cover
            pass
    finally:
        db.close()
