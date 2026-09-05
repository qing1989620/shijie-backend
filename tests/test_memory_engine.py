"""Memory Engine (FSRS-4.5) tests — the scientific layer must behave correctly."""
from datetime import UTC, datetime, timedelta

from app.ai.memory_engine import (
    RATING_AGAIN,
    RATING_EASY,
    RATING_GOOD,
    MemoryEngine,
    MemorySnapshot,
    retrievability,
)


def test_new_card_gets_initial_stability_by_rating():
    engine = MemoryEngine()
    snap = MemorySnapshot()
    out_good = engine.update(snap, RATING_GOOD, now=datetime(2026, 1, 1, tzinfo=UTC))
    out_easy = engine.update(snap, RATING_EASY, now=datetime(2026, 1, 1, tzinfo=UTC))
    assert out_easy.snapshot.stability > out_good.snapshot.stability
    assert out_good.interval_days >= 1


def test_correct_answer_extends_interval():
    engine = MemoryEngine()
    snap = MemorySnapshot()
    first = engine.update(snap, RATING_GOOD, now=datetime(2026, 1, 1, tzinfo=UTC))
    second = engine.update(first.snapshot, RATING_GOOD, now=datetime(2026, 1, 8, tzinfo=UTC))
    assert second.interval_days > first.interval_days


def test_lapse_shortens_interval_and_raises_difficulty():
    engine = MemoryEngine()
    snap = MemorySnapshot(review_count=3, stability=10.0, difficulty=5.0, last_review_at=datetime(2026, 1, 1, tzinfo=UTC))
    before_difficulty = snap.difficulty
    out = engine.update(snap, RATING_AGAIN, now=datetime(2026, 1, 10, tzinfo=UTC))
    out_good = engine.update(snap, RATING_GOOD, now=datetime(2026, 1, 10, tzinfo=UTC))
    assert out.snapshot.lapse_count == 1
    assert out.snapshot.stability < out_good.snapshot.stability
    assert out.snapshot.difficulty > before_difficulty  # harder after failure
    assert out.snapshot.difficulty > out_good.snapshot.difficulty  # failure hurts much more (FSRS mean reversion applies on success)


def test_retrievability_decays_over_time():
    last = datetime(2026, 1, 1, tzinfo=UTC)
    now = datetime(2026, 1, 2, tzinfo=UTC)
    r1 = retrievability(now, last, stability=5.0)
    r2 = retrievability(now + timedelta(days=5), last, stability=5.0)
    assert 0.9 < r1 <= 1.0
    assert r2 < r1


def test_rating_mapping_from_behaviour():
    engine = MemoryEngine()
    assert engine.map_rating(is_correct=False) == RATING_AGAIN
    assert engine.map_rating(is_correct=True, hint_count=3) in {RATING_AGAIN - 1, 2}  # hard=2
    assert engine.map_rating(is_correct=True, confidence=5, duration_ms=10000) == RATING_EASY
    assert engine.map_rating(is_correct=True) == RATING_GOOD


def test_forecast_monotonic_decay():
    engine = MemoryEngine()
    snap = MemorySnapshot(stability=3.0, last_review_at=datetime.now(UTC) - timedelta(days=1))
    pts = engine.forecast(snap, horizon_days=5)
    vals = [p["retrievability"] for p in pts]
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))


def test_question_states_are_independent():
    """Each (user, question) pair evolves independently — engine is stateless per snapshot."""
    engine = MemoryEngine()
    a = engine.update(MemorySnapshot(), RATING_GOOD, now=datetime(2026, 1, 1, tzinfo=UTC))
    b = engine.update(MemorySnapshot(), RATING_AGAIN, now=datetime(2026, 1, 1, tzinfo=UTC))
    assert a.snapshot.stability != b.snapshot.stability
    assert a.snapshot.lapse_count == 0 and b.snapshot.lapse_count == 1
