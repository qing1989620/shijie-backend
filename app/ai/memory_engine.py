"""Memory Engine — FSRS-4.5 (Free Spaced Repetition Scheduler) implementation.

Scientific layer, deliberately separated from product heuristics (see
docs/ai/REVIEW_ALGORITHM.md). Formulas follow the FSRS-4.5 reference
implementation (open-spaced-repetition/py-fsrs, MIT License).

R(t, S) = (1 + t / (9 * S)) ^ DECAY          — retrievability after t days
S' (success) = S * (1 + e^w8 * (11 - D) * S^(-w9) * (e^(w10*(1-R)) - 1)
                   * HARD_PENALTY * EASY_BONUS)
S' (lapse)   = w11 * D^(-w12) * ((S + 1) ^ w13 - 1) * e^(w14 * (1 - R))
D' (rating)  = clamp(D - w6 * (rating - 3), 1, 10)          — per-review drift
D'' (mean reversion) = w5 * D0(rating) + (1 - w5) * D'

Interval to next review at target retention r*: I = 9 * S * (r*^(1/DECAY) - 1)
"""
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# FSRS-4.5 default weights (17 params, from open-spaced-repetition, MIT)
W = [
    0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031,
    1.6474, 0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755,
]
DECAY = -0.5
FACTOR = 0.9 ** (1.0 / DECAY) - 1.0  # ≈ 19/81
HARD_PENALTY = 1.0 + W[15]
EASY_BONUS = 1.0 + W[16]

RATING_AGAIN, RATING_HARD, RATING_GOOD, RATING_EASY = 1, 2, 3, 4

SCHEDULER_VERSION = "fsrs45-baseline"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class MemorySnapshot:
    """Algorithm-level view of one (user, question) memory state."""

    difficulty: float = 5.0
    stability: float = 0.5
    last_review_at: datetime | None = None
    review_count: int = 0
    lapse_count: int = 0
    scheduler_version: str = SCHEDULER_VERSION

    def as_params(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "stability": self.stability,
            "last_review_at": self.last_review_at,
            "review_count": self.review_count,
            "lapse_count": self.lapse_count,
            "scheduler_version": self.scheduler_version,
        }


def retrievability(now: datetime, last_review_at: datetime | None, stability: float) -> float:
    """Estimated recall probability right now (0..1). New card (never reviewed) -> 0."""
    if last_review_at is None or stability <= 0:
        return 0.0
    elapsed_days = max(0.0, (now - last_review_at).total_seconds() / 86400.0)
    return clamp((1.0 + FACTOR * elapsed_days / stability) ** DECAY, 0.0, 1.0)


def initial_stability(rating: int) -> float:
    return W[rating - 1]


def initial_difficulty(rating: int) -> float:
    return clamp(W[4] - (rating - 3) * W[5], 1.0, 10.0)


def next_difficulty(d: float, rating: int) -> float:
    return clamp(d - W[6] * (rating - 3), 1.0, 10.0)


def mean_reversion(d_new: float, rating: int) -> float:
    return clamp(W[5] * initial_difficulty(rating) + (1 - W[5]) * d_new, 1.0, 10.0)


def next_stability(d: float, s: float, r: float, rating: int) -> float:
    if rating == RATING_AGAIN:
        return clamp(
            W[11] * d ** (-W[12]) * ((s + 1.0) ** W[13] - 1.0) * math.exp(W[14] * (1.0 - r)),
            0.1,
            36500.0,
        )
    hard = HARD_PENALTY if rating == RATING_HARD else 1.0
    easy = EASY_BONUS if rating == RATING_EASY else 1.0
    return clamp(
        s
        * (1.0 + math.exp(W[8]) * (11.0 - d) * s ** (-W[9]) * (math.exp(W[10] * (1.0 - r)) - 1.0) * hard * easy),
        0.1,
        36500.0,
    )


def next_interval(stability: float, target_retention: float = 0.9) -> int:
    """Days until retrievability decays to target_retention."""
    if stability <= 0:
        return 1
    days = 9.0 * stability * (target_retention ** (1.0 / DECAY) - 1.0)
    return max(1, round(days))


@dataclass
class ReviewOutcome:
    snapshot: MemorySnapshot
    retrievability: float
    next_due_at: datetime
    interval_days: int
    rating: int


class MemoryEngine:
    """Layer 1: answers 'when will this question start to fade?'.

    Takes raw behaviour (correctness, latency, hints, confidence...) and maps it
    to an FSRS rating, updates the snapshot, returns the next due date.
    """

    def __init__(self, target_retention: float = 0.9) -> None:
        self.target_retention = clamp(target_retention, 0.7, 0.98)

    # -- rating mapping ------------------------------------------------------
    def map_rating(
        self,
        is_correct: bool | None,
        duration_ms: int | None = None,
        hint_count: int = 0,
        confidence: int | None = None,
        answer_change_count: int = 0,
    ) -> int:
        """Map raw behaviour -> internal FSRS rating (Again/Hard/Good/Easy).

        Deterministic program logic (NOT an AI decision) per docs/ai/REVIEW_ALGORITHM.md.
        """
        if is_correct is False:
            return RATING_AGAIN
        conf = confidence or 3
        if is_correct is True:
            if hint_count >= 2 or conf <= 2 or (answer_change_count or 0) >= 2:
                return RATING_HARD
            if conf >= 5 and (duration_ms or 60_000) < 45_000 and hint_count == 0:
                return RATING_EASY
            return RATING_GOOD
        # unknown correctness (subjective, self-graded None): lean conservative
        return RATING_HARD if conf <= 3 else RATING_GOOD

    # -- core update ----------------------------------------------------------
    def update(
        self,
        snapshot: MemorySnapshot,
        rating: int,
        now: datetime | None = None,
    ) -> ReviewOutcome:
        now = now or datetime.now(UTC)
        r = retrievability(now, snapshot.last_review_at, snapshot.stability)
        # Engineering guard: at r≈1 (e.g. immediate re-review) the FSRS success branch
        # yields zero growth; clamp to 0.99 so every review produces strictly positive learning.
        r_for_growth = min(r, 0.99)
        if snapshot.review_count == 0:
            s_new = initial_stability(rating)
            d_new = initial_difficulty(rating)
        else:
            s_new = next_stability(snapshot.difficulty, snapshot.stability, r_for_growth, rating)
            d_drift = next_difficulty(snapshot.difficulty, rating)
            d_new = mean_reversion(d_drift, rating)
        interval_days = next_interval(s_new, self.target_retention)
        out = MemorySnapshot(
            difficulty=d_new,
            stability=s_new,
            last_review_at=now,
            review_count=snapshot.review_count + 1,
            lapse_count=snapshot.lapse_count + (1 if rating == RATING_AGAIN else 0),
            scheduler_version=SCHEDULER_VERSION,
        )
        return ReviewOutcome(
            snapshot=out,
            retrievability=r,
            next_due_at=now + timedelta(days=interval_days),
            interval_days=interval_days,
            rating=rating,
        )

    # -- forecasting -----------------------------------------------------------
    def forecast(
        self, snapshot: MemorySnapshot, horizon_days: int = 30, now: datetime | None = None
    ) -> list[dict]:
        now = now or datetime.now(UTC)
        points = []
        for day in range(horizon_days + 1):
            t = now + timedelta(days=day)
            points.append(
                {
                    "date": t.date().isoformat(),
                    "day": day,
                    "retrievability": round(retrievability(t, snapshot.last_review_at, snapshot.stability), 4)
                    if snapshot.last_review_at
                    else 0.0,
                }
            )
        return points
