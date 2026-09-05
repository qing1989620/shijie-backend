"""Courses & lessons routes (Module 1 CRUD)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, owner_or_404
from app.core.db import get_db
from app.core.errors import AppError
from app.models import Course, DomainEvent, Lesson, User
from app.schemas.schemas import CourseIn, CourseOut, CoursePageOut, LessonIn, LessonOut, LessonPageOut, LessonPatchIn

router = APIRouter(tags=["courses", "lessons"])


# ---------------------------------------------------------------- courses


@router.get("/courses", response_model=CoursePageOut, operation_id="courses_list")
def courses_list(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=50, le=100),
):
    rows = (
        db.query(Course)
        .filter(Course.user_id == user.id, Course.deleted_at.is_(None))
        .order_by(Course.created_at.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    items = [CourseOut.model_validate(r) for r in rows[:limit]]
    return CoursePageOut(items=items, has_more=has_more)


@router.post("/courses", response_model=CourseOut, status_code=201, operation_id="courses_create")
def courses_create(body: CourseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models import Subject

    data = body.model_dump()
    subject_name = data.pop("subject", None)
    subject_id = None
    if subject_name:
        subj = db.query(Subject).filter(Subject.name == subject_name).first()
        if not subj:
            import re
            import uuid

            subj = Subject(name=subject_name, slug=re.sub(r"[^a-z0-9]+", "-", subject_name.lower()) or f"subj-{uuid.uuid4().hex[:6]}")
            db.add(subj)
            db.flush()
        subject_id = subj.id
    course = Course(user_id=user.id, subject_id=subject_id, **data)
    db.add(course)
    db.add(DomainEvent(event_type="course_created", user_id=user.id, payload={"course_id": course.id}))
    db.commit()
    # respond with the requested subject name for round-trip consistency
    course_out = CourseOut(
        id=course.id, name=course.name, subject=subject_name, teacher=course.teacher,
        grade=course.grade, description=course.description, color=course.color, created_at=course.created_at,
    )
    return course_out


@router.get("/courses/{course_id}", response_model=CourseOut, operation_id="course_get")
def course_get(course_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return owner_or_404(
        db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first(), user.id
    )


@router.patch("/courses/{course_id}", response_model=CourseOut, operation_id="course_update")
def course_update(
    course_id: str, body: CourseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    from app.models import Subject

    course = owner_or_404(
        db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first(), user.id
    )
    data = body.model_dump(exclude_unset=True)
    subject_name = data.pop("subject", None)
    if subject_name is not None:
        subj = db.query(Subject).filter(Subject.name == subject_name).first()
        if not subj:
            import re
            import uuid

            subj = Subject(name=subject_name, slug=re.sub(r"[^a-z0-9]+", "-", subject_name.lower()) or f"subj-{uuid.uuid4().hex[:6]}")
            db.add(subj)
            db.flush()
        course.subject_id = subj.id
        course.subject_ref = subj
    for k, v in data.items():
        setattr(course, k, v)
    db.commit()
    return course


@router.delete("/courses/{course_id}", status_code=204, operation_id="course_delete")
def course_delete(course_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import UTC, datetime

    course = owner_or_404(
        db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first(), user.id
    )
    course.deleted_at = datetime.now(UTC)
    db.commit()
    return None


# ---------------------------------------------------------------- lessons


@router.get("/lessons", response_model=LessonPageOut, operation_id="lessons_list")
def lessons_list(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=20, le=100),
    cursor: int | None = None,
):
    q = db.query(Lesson).filter(Lesson.user_id == user.id, Lesson.deleted_at.is_(None))
    if course_id:
        q = q.filter(Lesson.course_id == course_id)
    if status:
        q = q.filter(Lesson.status == status)
    rows = q.order_by(Lesson.created_at.desc()).offset(cursor or 0).limit(limit + 1).all()
    has_more = len(rows) > limit
    items = [LessonOut.model_validate(r) for r in rows[:limit]]
    next_cursor = (cursor or 0) + limit if has_more else None
    return LessonPageOut(items=items, next_cursor=str(next_cursor) if next_cursor else None, has_more=has_more)


@router.post("/lessons", response_model=LessonOut, status_code=201, operation_id="lessons_create")
def lessons_create(body: LessonIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lesson = Lesson(user_id=user.id, **body.model_dump())
    db.add(lesson)
    db.add(DomainEvent(event_type="lesson_created", user_id=user.id, payload={"lesson_id": lesson.id}))
    db.commit()
    return lesson


@router.get("/lessons/{lesson_id}", response_model=LessonOut, operation_id="lesson_get")
def lesson_get(lesson_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return owner_or_404(
        db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.deleted_at.is_(None)).first(), user.id
    )


@router.patch("/lessons/{lesson_id}", response_model=LessonOut, operation_id="lesson_update")
def lesson_update(
    lesson_id: str, body: LessonPatchIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    lesson = owner_or_404(
        db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.deleted_at.is_(None)).first(), user.id
    )
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in {"draft", "recording", "processing", "ready", "failed", "archived"}:
        raise AppError("VALIDATION_ERROR", "invalid lesson status")
    for k, v in data.items():
        setattr(lesson, k, v)
    db.commit()
    return lesson


@router.delete("/lessons/{lesson_id}", status_code=204, operation_id="lesson_delete")
def lesson_delete(lesson_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Soft delete; hard deletion of audio/transcript/RAG chunks is the worker's job."""
    from datetime import UTC, datetime

    lesson = owner_or_404(
        db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.deleted_at.is_(None)).first(), user.id
    )
    lesson.deleted_at = datetime.now(UTC)
    lesson.status = "archived"
    db.add(DomainEvent(event_type="lesson_deleted", user_id=user.id, payload={"lesson_id": lesson.id}))
    db.commit()
    return None
