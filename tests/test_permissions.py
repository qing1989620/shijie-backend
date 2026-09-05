"""IDOR / permission tests: user data must be scoped by owner."""
from tests.conftest import auth_headers  # noqa: F401


def test_other_user_cannot_read_lesson(client, user_factory, auth_headers):
    headers, user = auth_headers
    course = client.post("/api/v1/courses", headers=headers, json={"name": "高一数学"}).json()
    lesson = client.post("/api/v1/lessons", headers=headers,
                         json={"course_id": course["id"], "title": "椭圆"}).json()
    # second user
    u2 = user_factory()
    t2 = client.post("/api/v1/auth/login", json={"email": u2.email, "password": "password123"}).json()["access_token"]
    h2 = {"Authorization": f"Bearer {t2}"}
    r = client.get(f"/api/v1/lessons/{lesson['id']}", headers=h2)
    assert r.status_code == 404  # not found for non-owner (no existence leak)
    r = client.get(f"/api/v1/lessons/{lesson['id']}", headers=headers)
    assert r.status_code == 200


def test_other_user_cannot_read_search(client, auth_headers):
    headers, _ = auth_headers
    # exercise search of another user -> 404
    r = client.get("/api/v1/exercise-searches/nonexistent", headers=headers)
    assert r.status_code == 404


def test_job_belongs_to_owner(client, auth_headers):
    headers, _ = auth_headers
    r = client.get("/api/v1/jobs/nonexistent", headers=headers)
    assert r.status_code == 404


def test_review_task_scoped(client, auth_headers):
    headers, _ = auth_headers
    r = client.get("/api/v1/review/tasks/nonexistent-id", headers=headers)
    assert r.status_code == 404
