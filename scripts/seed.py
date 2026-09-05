"""Seed the database: subjects + CC0 local question bank + a demo user.

Usage: .venv/Scripts/python.exe scripts/seed.py
Idempotent: skips subjects/questions that already exist (by content_hash).
"""
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    QuestionSource,
    Subject,
    User,
)

SEED_FILE = Path(__file__).parent / "seed_questions.json"
DEMO_EMAIL = "demo@shijie.app"
DEMO_PASSWORD = "demo12345"


def content_hash(stem: str, options: list) -> str:
    normalized = "".join((stem or "").split()).lower()
    opts = "".join(sorted(o.get("text", "") for o in options or []))
    return hashlib.sha256((normalized + opts).encode()).hexdigest()


def main() -> None:
    Base.metadata.create_all(engine)  # dev bootstrap only; migrations own schema in CI/prod
    db = SessionLocal()
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    for s in data["subjects"]:
        if not db.query(Subject).filter(Subject.slug == s["slug"]).first():
            db.add(Subject(name=s["name"], slug=s["slug"]))
    db.commit()

    source = db.query(QuestionSource).filter(QuestionSource.source_name == data["source_name"]).first()
    if not source:
        source = QuestionSource(
            source_type="local_bank", source_name=data["source_name"], license="CC0-1.0",
            retrieved_at=datetime.now(UTC),
        )
        db.add(source)
        db.commit()

    added = 0
    for item in data["questions"]:
        h = content_hash(item["stem"], item.get("options"))
        if db.query(Question).filter(Question.content_hash == h).first():
            continue
        q = Question(
            subject=item["subject"], grade=item["grade"], question_type=item["type"],
            stem=item["stem"], options=item.get("options"), answer=item.get("answer"),
            solution=item.get("solution"), difficulty=item["difficulty"],
            source_id=source.id, content_hash=h, is_global=True,
        )
        db.add(q)
        db.flush()
        for kp_name in item.get("kp", []):
            kp = db.query(KnowledgePoint).filter(KnowledgePoint.name == kp_name).first()
            if not kp:
                import re
                import uuid

                slug = re.sub(r"[^a-z0-9]+", "-", kp_name.lower()).strip("-") or "kp"
                kp = KnowledgePoint(name=kp_name, slug=f"{slug}-{uuid.uuid4().hex[:6]}", subject=item["subject"])
                db.add(kp)
                db.flush()
            if not db.query(QuestionKnowledgePoint).filter(
                QuestionKnowledgePoint.question_id == q.id, QuestionKnowledgePoint.knowledge_point_id == kp.id
            ).first():
                db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=kp.id, role="core"))
        added += 1
    db.commit()

    if not db.query(User).filter(User.email == DEMO_EMAIL).first():
        db.add(User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), display_name="演示用户"))
        db.commit()

    print(f"seeded: subjects={len(data['subjects'])} questions_added={added} demo_user={DEMO_EMAIL}/{DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
