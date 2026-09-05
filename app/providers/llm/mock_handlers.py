"""MockLLM deterministic handlers: one per prompt version.

Each handler receives the serialized request payload (JSON string) and returns a
dict matching the corresponding Pydantic output schema. They implement *shaping*,
not understanding — when a real key is configured the OpenRouterProvider takes over.
"""
import json
import re


def _segments_from_payload(user: str) -> list[str]:
    data = json.loads(user)
    return data.get("segments", [])


# ------------------------------------------------------------- lesson_summary_v1


def lesson_summary_v1(user: str) -> dict:
    data = json.loads(user)
    segments: list[str] = data.get("segments", [])
    subject: str = data.get("subject") or "通用"
    topics: list[dict] = []
    key_concepts: list[dict] = []
    seen_spans: list[tuple[int, int]] = []
    chunk = max(1, len(segments) // 6)
    idx = 0
    while idx < len(segments):
        span = segments[idx : idx + chunk]
        joined = "".join(span)
        m = re.search(r"([\u4e00-\u9fff]{2,8}(?:定理|方程|公式|性质|概念|法则|定义))", joined)
        topic = m.group(1) if m else f"第{idx + 1}部分内容"
        start_id = data["segment_ids"][idx]
        end_id = data["segment_ids"][min(idx + chunk - 1, len(data["segment_ids"]) - 1)]
        topics.append(
            {
                "topic": topic,
                "summary": f"老师讲解了「{topic}」的相关内容并进行了例题演示。",
                "source_segment_ids": [start_id, end_id],
                "timestamp_range": [
                    data["timestamps"][idx] if idx < len(data["timestamps"]) else 0,
                    data["timestamps"][min(idx + chunk, len(data["timestamps"]) - 1)] if data["timestamps"] else 0,
                ],
            }
        )
        if m:
            key_concepts.append(
                {"concept": m.group(1), "definition": f"本节课中「{m.group(1)}」出现的要点，详见对应课堂片段。"}
            )
        seen_spans.append((idx, idx + chunk))
        idx += chunk
    return {
        "title": f"{subject}课堂笔记",
        "overview": f"本节{subject}课堂共 {len(segments)} 个转写片段，覆盖 {len(topics)} 个主题。",
        "topics": topics,
        "key_concepts": key_concepts,
        "definitions": [],
        "formulas": [],
        "teacher_emphasis": [t["topic"] for t in topics[:3]],
        "examples": [],
        "common_mistakes": [],
        "knowledge_points": list({t["topic"] for t in topics})[:8],
        "review_focus": [t["topic"] for t in topics[:2]],
        "uncertain": len(segments) < 3,
    }


# ------------------------------------------------------------- exercise_query_rewrite_v1


def exercise_query_rewrite_v1(user: str) -> dict:
    data = json.loads(user)
    kps = data.get("knowledge_points") or []
    subject = data.get("subject") or ""
    grade = data.get("grade") or ""
    return {
        "keywords": [kp for kp in kps][:6],
        "subject": subject,
        "grade": grade,
        "difficulty_hint": data.get("difficulty_hint"),
        "rationale": "基于课堂知识点与学科信息构造检索关键词。",
    }


# ------------------------------------------------------------- question_analysis_v1


def question_analysis_v1(user: str) -> dict:
    """Build a 3-level tree: core -> prerequisite/method/extension.

    Canonicalization: normalize_kp_name() in the analysis agent has already
    de-duplicated names before this handler is invoked.
    """
    data = json.loads(user)
    stem: str = data.get("stem", "")
    core = data.get("candidate_core") or "综合应用"
    prereqs = data.get("candidate_prereqs") or []

    def node(name: str, role: str, level: int, children: list) -> dict:
        return {
            "name": name,
            "role": role,
            "level": level,
            "description": f"解答本题所需的{role}知识点：{name}",
            "importance": 0.9 if role == "core" else 0.5,
            "confidence": 0.6,
            "children": children,
        }

    children = [node(p, "prerequisite", 2, []) for p in prereqs[:4]]
    if any(k in stem for k in ("最值", "最大", "最小", "取值范围")):
        children.append(node("最值方法", "method", 2, []))
    tree = node(core, "core", 1, children)
    return {
        "root": tree,
        "summary": f"本题主要考察「{core}」" + (f"，并综合运用 {'、'.join(prereqs[:3])}。" if prereqs else "。"),
        "mastery_signals": ["作答正确率", "用时", "提示使用次数"],
    }
