"""Pytest fixtures: isolated per-test database + FastAPI TestClient."""
import os
import tempfile
import time
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="shijie-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir) / 'test.db'}"
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["ASR_PROVIDER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import KnowledgePoint, Question, User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def user_factory(db):
    import uuid

    def make(email_suffix: str = ""):
        u = User(
            email=f"user-{uuid.uuid4().hex[:10]}{email_suffix}@test.dev",
            password_hash=hash_password("password123"),
            display_name="测试用户",
        )
        db.add(u)
        db.commit()
        return u

    return make


@pytest.fixture()
def auth_headers(client, user_factory):
    user = user_factory()
    resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "password123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture()
def seeded_kp(db):
    kp = KnowledgePoint(name="椭圆标准方程", slug=f"ellipse-std-{time.time_ns()}", subject="数学")
    db.add(kp)
    db.commit()
    return kp


@pytest.fixture()
def bank_question(db, seeded_kp):
    from app.models import QuestionKnowledgePoint, QuestionSource

    src = QuestionSource(source_type="local_bank", source_name="测试题库", license="CC0")
    db.add(src)
    db.flush()
    q = Question(
        subject="数学", grade="高一", question_type="single_choice", stem="椭圆 $\\frac{x^2}{9}+\\frac{y^2}{4}=1$ 的离心率是？",
        options=[{"key": "A", "text": "$\\frac{\\sqrt{5}}{3}$"}, {"key": "B", "text": "$\\frac{2}{3}$"}],
        answer="A", solution="$c=\\sqrt{9-4}=\\sqrt5$", difficulty=3,
        source_id=src.id, content_hash=f"hash-{time.time_ns()}", is_global=True,
    )
    db.add(q)
    db.flush()
    db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=seeded_kp.id, role="core"))
    db.commit()
    return q


def wait_job(client, headers, job_id: str, timeout=15.0) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        r = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        if r.status_code == 200 and r.json()["status"] in {"succeeded", "failed"}:
            return r.json()
        time.sleep(0.2)
    raise TimeoutError(f"job {job_id} did not finish")
