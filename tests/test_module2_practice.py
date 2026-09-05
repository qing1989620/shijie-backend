"""Module 2 flow: import / OCR preview->confirm / analysis->tree / specialized search / practice."""
import io

from tests.conftest import wait_job


def test_import_and_analysis_tree(client, auth_headers, bank_question):
    headers, _ = auth_headers
    qid = bank_question.id
    job = client.post(f"/api/v1/questions/{qid}/analysis-jobs", headers=headers).json()
    done = wait_job(client, headers, job["job_id"])
    assert done["status"] == "succeeded", done

    tree = client.get(f"/api/v1/questions/{qid}/knowledge-tree", headers=headers).json()
    assert tree["tree"]["role"] == "core"
    names = [tree["tree"]["name"]] + [c["name"] for c in tree["tree"].get("children", [])]
    assert any("椭圆" in n for n in names), "canonical KP must appear in tree"


def test_ocr_preview_then_confirm(client, auth_headers):
    headers, _ = auth_headers
    payload = ("已知椭圆 $\\frac{x^2}{16}+\\frac{y^2}{12}=1$，求它的离心率。\n\n"
               "A. $\\frac{1}{2}$\n\nB. $\\frac{\\sqrt{7}}{4}$\n\n答案：A")
    r = client.post("/api/v1/questions/ocr", headers=headers,
                    files={"file": ("wrong.png", io.BytesIO(payload.encode("utf-8")), "image/png")})
    assert r.status_code == 202, r.text
    preview = r.json()
    assert preview["needs_review"] is True and preview["text"]
    # user corrects/confirms -> import
    imp = client.post("/api/v1/questions/import", headers=headers, json={
        "subject": "数学", "grade": "高一", "question_type": "single_choice",
        "stem": preview["blocks"][0]["content"], "answer": "A", "difficulty": 3, "origin": "upload",
        "source_name": "错题本拍照",
    })
    assert imp.status_code == 201
    assert imp.json()["origin"] == "upload"
    # duplicate import must not create a second question (content hash dedup)
    imp2 = client.post("/api/v1/questions/import", headers=headers, json={
        "subject": "数学", "stem": preview["blocks"][0]["content"], "answer": "A", "difficulty": 3, "origin": "upload",
    })
    assert imp2.json()["id"] == imp.json()["id"]


def test_kp_specialized_search(client, auth_headers, bank_question, seeded_kp):
    headers, _ = auth_headers
    qid = bank_question.id
    # favorite so user-question relation exists
    client.post(f"/api/v1/questions/{qid}/favorite", headers=headers)
    search = client.post(f"/api/v1/knowledge-points/{seeded_kp.id}/exercise-searches", headers=headers).json()
    assert search["status"] == "succeeded"
    assert search["scope"] == "knowledge_point"
    assert len(search["results"]) >= 1
    bands = {r["band"] for r in search["results"]}
    assert bands <= {"basic", "same_level", "advanced"}


def test_random_and_smart_practice_attempt(client, auth_headers, bank_question):
    headers, user = auth_headers
    client.post(f"/api/v1/questions/{bank_question.id}/favorite", headers=headers)
    ps = client.post("/api/v1/practice-sets", headers=headers,
                     json={"mode": "random", "count": 3}).json()
    assert len(ps["items"]) >= 1
    q = ps["items"][0]["question"]
    # submit attempt (correct answer A)
    r = client.post(f"/api/v1/practice-sets/{ps['id']}/attempts", headers=headers, json={
        "question_id": q["id"], "answer": "A", "duration_ms": 25000, "confidence": 4,
    })
    assert r.status_code == 201, r.text
    assert r.json()["created_memory_state"] is True
    # smart set works too
    ps2 = client.post("/api/v1/practice-sets", headers=headers, json={"mode": "smart", "count": 2}).json()
    assert ps2["id"] != ps["id"]
    # frozen ordering: same items on re-fetch
    refetch = client.get(f"/api/v1/practice-sets/{ps['id']}", headers=headers).json()
    assert [i["question"]["id"] for i in refetch["items"]] == [i["question"]["id"] for i in ps["items"]]


def test_subjective_requires_self_grading(client, auth_headers):
    headers, _ = auth_headers
    imp = client.post("/api/v1/questions/import", headers=headers, json={
        "subject": "数学", "question_type": "subjective", "stem": "证明：$a^2+b^2\\ge 2ab$。", "answer": "", "difficulty": 3,
    })
    qid = imp.json()["id"]
    r = client.post("/api/v1/attempts", headers=headers, json={"question_id": qid, "answer": "证略"})
    assert r.status_code == 422  # cannot fake grading for subjective
    r2 = client.post("/api/v1/attempts", headers=headers,
                     json={"question_id": qid, "answer": "证略", "is_correct": True, "grading_source": "self"})
    assert r2.status_code == 201
