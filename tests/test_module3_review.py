"""Module 3 flow: attempt -> MemoryState -> ReviewTask -> complete -> next review."""
from datetime import UTC, datetime


def _practice_one(client, headers, question):
    ps = client.post("/api/v1/practice-sets", headers=headers, json={"mode": "random", "count": 1}).json()
    r = client.post(f"/api/v1/practice-sets/{ps['id']}/attempts", headers=headers, json={
        "question_id": question.id, "answer": "B", "duration_ms": 40000, "confidence": 2,
    })  # wrong answer -> Again
    assert r.status_code == 201, r.text
    return r.json()


def test_attempt_creates_memory_state_and_review_task(client, auth_headers, bank_question):
    headers, user = auth_headers
    client.post(f"/api/v1/questions/{bank_question.id}/favorite", headers=headers)
    attempt = _practice_one(client, headers, bank_question)
    assert attempt["created_memory_state"] is True

    ms = client.get(f"/api/v1/questions/{bank_question.id}/memory-state", headers=headers)
    assert ms.status_code == 200
    body = ms.json()
    assert body["review_count"] == 1 and body["lapse_count"] == 1
    assert body["next_review_at"]

    # review task appeared (tomorrow)
    tasks = client.get("/api/v1/review/tasks", headers=headers).json()
    assert any(t["question_id"] == bank_question.id for t in tasks)

    # calendar contains a future day entry for the same question
    cal = client.get("/api/v1/review/calendar", headers=headers, params={"days": 30}).json()
    assert any(d["count"] > 0 for d in cal)


def test_review_completion_updates_memory_and_schedules_next(client, auth_headers, bank_question):
    headers, user = auth_headers
    client.post(f"/api/v1/questions/{bank_question.id}/favorite", headers=headers)
    _practice_one(client, headers, bank_question)
    tasks = client.get("/api/v1/review/tasks", headers=headers).json()
    task = next(t for t in tasks if t["question_id"] == bank_question.id)

    # fetch the task detail & complete it correctly
    detail = client.get(f"/api/v1/review/tasks/{task['id']}", headers=headers).json()
    assert detail["question"]["id"] == bank_question.id
    done = client.post(f"/api/v1/review/tasks/{task['id']}/complete", headers=headers, json={
        "question_id": bank_question.id, "answer": "A", "duration_ms": 20000, "confidence": 5,
    })
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["next_review_at"]

    ms = client.get(f"/api/v1/questions/{bank_question.id}/memory-state", headers=headers).json()
    assert ms["review_count"] == 2 and ms["lapse_count"] == 1
    assert ms["stability"] > 0.5

    # a NEW future review task exists — visible on the calendar (scheduled, not completed)
    cal = client.get("/api/v1/review/calendar", headers=headers, params={"days": 30}).json()
    future = [d for d in cal if d["date"] > datetime.now(UTC).date().isoformat()
              and any(i["question_id"] == bank_question.id for i in d["items"])]
    assert future, "next review task must appear on the calendar after completion"


def test_skip_reschedules_without_memory_update(client, auth_headers, bank_question):
    headers, user = auth_headers
    client.post(f"/api/v1/questions/{bank_question.id}/favorite", headers=headers)
    _practice_one(client, headers, bank_question)
    tasks = client.get("/api/v1/review/tasks", headers=headers).json()
    task = next(t for t in tasks if t["question_id"] == bank_question.id)
    before = client.get(f"/api/v1/questions/{bank_question.id}/memory-state", headers=headers).json()
    r = client.post(f"/api/v1/review/tasks/{task['id']}/skip", headers=headers)
    assert r.status_code == 200
    after = client.get(f"/api/v1/questions/{bank_question.id}/memory-state", headers=headers).json()
    assert after["review_count"] == before["review_count"]  # skip is NOT a review


def test_memory_forecast_curve(client, auth_headers, bank_question):
    headers, user = auth_headers
    client.post(f"/api/v1/questions/{bank_question.id}/favorite", headers=headers)
    _practice_one(client, headers, bank_question)
    fc = client.get(f"/api/v1/questions/{bank_question.id}/memory-forecast", headers=headers).json()
    assert len(fc["points"]) >= 7
    assert fc["points"][0]["retrievability"] >= fc["points"][-1]["retrievability"]


def test_onboarding_profile(client, auth_headers):
    headers, _ = auth_headers
    p = client.put("/api/v1/review/profile", headers=headers, json={
        "grade": "高一", "daily_minutes": 30, "preferred_time": "21:00",
        "target_retention": 0.9, "exam_date": "2026-09-30T00:00:00Z",
    })
    assert p.status_code == 200 and p.json()["onboarded"] is True
    g = client.get("/api/v1/review/profile", headers=headers).json()
    assert g["daily_minutes"] == 30


def test_mastered_suspends_not_deletes(client, auth_headers, bank_question):
    headers, user = auth_headers
    client.post(f"/api/v1/questions/{bank_question.id}/favorite", headers=headers)
    _practice_one(client, headers, bank_question)
    tasks = client.get("/api/v1/review/tasks", headers=headers).json()
    task = next(t for t in tasks if t["question_id"] == bank_question.id)
    r = client.post(f"/api/v1/review/tasks/{task['id']}/mastered", headers=headers)
    assert r.status_code == 200
    ms = client.get(f"/api/v1/questions/{bank_question.id}/memory-state", headers=headers).json()
    assert ms["next_review_at"]  # still exists, far future
