"""Module 1 flow: course -> lesson -> recording -> transcript -> summary -> search -> favorite."""
import io

from tests.conftest import wait_job


def _make_audio(client, headers, lesson_id):
    return client.post(
        f"/api/v1/lessons/{lesson_id}/recordings",
        headers=headers,
        files={"file": ("lesson.webm", io.BytesIO(b"RIFFfakeaudio" * 64), "audio/webm")},
    )


def test_full_module1_flow(client, auth_headers, bank_question, seeded_kp):
    headers, user = auth_headers
    course = client.post("/api/v1/courses", headers=headers, json={"name": "高二数学", "subject": "数学", "grade": "高一"}).json()
    assert course["id"]
    lesson = client.post("/api/v1/lessons", headers=headers,
                         json={"course_id": course["id"], "title": "椭圆及其标准方程", "subject": "数学", "grade": "高一"}).json()

    rec = _make_audio(client, headers, lesson["id"])
    assert rec.status_code == 201, rec.text
    rec_id = rec.json()["id"]

    fin = client.post(f"/api/v1/recordings/{rec_id}/finalize", headers=headers)
    assert fin.status_code == 200, fin.text
    assert fin.json()["status"] == "finalized"

    tr = client.get(f"/api/v1/lessons/{lesson['id']}/transcript", headers=headers).json()
    assert len(tr["items"]) >= 5  # mock ASR 6 segments
    seg = tr["items"][0]
    # edit with correct version
    r = client.patch(f"/api/v1/transcript-segments/{seg['id']}", headers=headers,
                     json={"text": "今天我们复习椭圆的标准方程。", "version": seg["version"]})
    assert r.status_code == 200
    # stale version -> 409
    r = client.patch(f"/api/v1/transcript-segments/{seg['id']}", headers=headers,
                     json={"text": "冲突写入", "version": seg["version"]})
    assert r.status_code == 409

    job = client.post(f"/api/v1/lessons/{lesson['id']}/summary-jobs", headers=headers).json()
    done = wait_job(client, headers, job["job_id"])
    assert done["status"] == "succeeded", done

    summary = client.get(f"/api/v1/lessons/{lesson['id']}/summary", headers=headers).json()
    assert summary["payload"]["topics"], "summary must contain topics"
    # summary must be grounded: topics carry source_segment_ids
    assert all("source_segment_ids" in t for t in summary["payload"]["topics"])

    # lesson exercise search (retrieval only)
    search = client.post(f"/api/v1/lessons/{lesson['id']}/exercise-searches", headers=headers).json()
    assert search["status"] == "succeeded"
    assert len(search["results"]) > 0, "local bank has ellipse questions; must find some"
    top = search["results"][0]
    assert top["question"]["stem"]
    assert top["relevance_reason"]

    # favorite -> appears in personal bank
    qid = top["question"]["id"]
    fav = client.post(f"/api/v1/questions/{qid}/favorite", headers=headers)
    assert fav.status_code == 200 and fav.json()["is_favorite"] is True
    bank = client.get("/api/v1/questions", headers=headers, params={"favorites_only": True}).json()
    assert any(q["id"] == qid for q in bank["items"])
    # idempotent favorite
    client.post(f"/api/v1/questions/{qid}/favorite", headers=headers)
    bank2 = client.get("/api/v1/questions", headers=headers, params={"favorites_only": True}).json()
    assert sum(1 for q in bank2["items"] if q["id"] == qid) == 1


def test_search_without_transcript_conflicts(client, auth_headers):
    headers, _ = auth_headers
    lesson = client.post("/api/v1/lessons", headers=headers, json={"title": "空课堂"}).json()
    r = client.post(f"/api/v1/lessons/{lesson['id']}/exercise-searches", headers=headers)
    assert r.status_code == 409


def test_recording_rejects_bad_extension(client, auth_headers):
    headers, _ = auth_headers
    lesson = client.post("/api/v1/lessons", headers=headers, json={"title": "录音测试"}).json()
    r = client.post(f"/api/v1/lessons/{lesson['id']}/recordings", headers=headers,
                    files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/x-msdownload")})
    assert r.status_code == 415
