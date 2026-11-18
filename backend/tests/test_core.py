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
