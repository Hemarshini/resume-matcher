import datetime as dt
from app.parsing import compute_years, parse_jd, parse_resume
from app.skills import extract_skills


def test_skill_boundaries():
    s = extract_skills("Strong JavaScript and Postgres; no Java here? Actually Java 17, C++ and .NET")
    assert "JavaScript" in s and "PostgreSQL" in s and "Java" in s and "C++" in s and ".NET" in s
    assert "Java" not in extract_skills("only javascript")


def test_years_merge_overlaps():
    y = dt.date.today().year
    assert compute_years(f"Jan {y-4} - Jan {y-2}\nJan {y-3} - Jan {y-1}") == 3.0


def test_jd_split_required_preferred():
    jd = parse_jd("Dev\nRequirements\n- 5+ years Java\n- Docker\nPreferred\n- Kubernetes")
    assert jd["min_years"] == 5 and "Java" in jd["required_skills"] and jd["preferred_skills"] == ["Kubernetes"]


def test_resume_parse():
    r = parse_resume("Jane Roe\nBackend Engineer\njane@x.com\nSKILLS\nSpring Boot, Postgres\nEXPERIENCE\nDev, X\nJan 2020 - Jan 2022\nEDUCATION\nB.Tech in CS")
    assert r["name"] == "Jane Roe" and r["years"] == 2.0 and "Java" in r["skills"] and r["education_level"] == 2


def test_blind_removes_identity():
    from app.parsing import anonymize
    t = anonymize("Jane Roe\njane@x.com | +91 98765 12345\nGender: F\nShe led the team. Her work shipped.", "Jane Roe")
    assert "Jane" not in t and "@" not in t and "98765" not in t and "Gender" not in t and "She" not in t


def test_combine_renormalises_missing_components():
    from app.matching import combine
    total, bd = combine({"skills": 1.0, "semantic": 1.0, "experience": None, "education": None})
    assert total == 100.0 and bd["experience"]["weight"] == 0 and abs(bd["skills"]["weight"] - 57.1) < 0.1


def test_listed_only_skills_get_half_credit():
    from app.matching import Embedder, skills_component
    jd = {"required_skills": ["Java", "Docker"], "preferred_skills": []}
    sk = skills_component.__wrapped__ if hasattr(skills_component, "__wrapped__") else skills_component
    class E:  # no semantic model needed
        semantic = False
    r = sk(E(), jd, ["Java", "Docker"], ["Java"])
    assert r["score"] == 0.75


def test_summary_falls_back_to_template(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/demo").json()
    s = c.post(f'/api/sessions/{r["session_id"]}/candidates/{r["candidates"][0]["id"]}/summary').json()
    assert s["source"] == "template" and "Suggested interview focus" in s["text"]


def test_renamed_files_and_wrong_types_rejected():
    import pytest
    from app.parsing import extract_text
    with pytest.raises(ValueError, match="not a real PDF"):
        extract_text("fake.pdf", b"John Smith\nJava developer with many years of experience in everything")
    with pytest.raises(ValueError, match="not a real DOCX"):
        extract_text("fake.docx", b"plain text pretending to be a word document, long enough to pass")
    with pytest.raises(ValueError, match="unsupported"):
        extract_text("cv.txt", b"x" * 100)          # resumes: no txt
    assert "Java" in extract_text("jd.txt", b"We need a Java developer for our backend team.", allow_text=True)


def test_api_rejects_bad_job_descriptions():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    f = [("resumes", ("a.pdf", open("../sample_resumes/01_Aarav_Mehta.pdf", "rb").read()))]
    r = c.post("/api/analyze", data={"jd_text": "need java dev now"}, files=f)
    assert r.status_code == 400 and "words" in r.json()["detail"]
    r = c.post("/api/analyze", data={"jd_text": "We want a hardworking and motivated person who works well in a team, communicates clearly with everybody, enjoys learning new things every day and always stays positive about the company"}, files=f)
    assert r.status_code == 400 and "recognised" in r.json()["detail"]


def test_fake_pdf_reported_but_batch_continues():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    jd = open("../sample_jd.txt").read()
    f = [("resumes", ("fake.pdf", b"John Smith\nA text file renamed to pdf" * 5)),
         ("resumes", ("ok.pdf", open("../sample_resumes/01_Aarav_Mehta.pdf", "rb").read()))]
    r = c.post("/api/analyze", data={"jd_text": jd}, files=f).json()
    assert len(r["candidates"]) == 1 and r["errors"][0]["filename"] == "fake.pdf"


def test_relevant_experience_scales_years():
    from app.matching import experience_component
    assert experience_component(7, 5, 0.9)["score"] == 1.0          # relevant background: years count in full
    off = experience_component(6, 5, 0.3)                            # same years, unrelated background
    assert off["relevant"] < 3 and off["score"] < 0.6


def test_core_skill_weighting():
    from app.parsing import parse_jd
    jd = parse_jd("Senior Java Engineer\nRequirements\n- 5 years of Java\n- Docker\n- Git")
    assert jd["skill_weights"]["Java"] > jd["skill_weights"]["Docker"] == 1.0 and "Java" in jd["core_skills"]
