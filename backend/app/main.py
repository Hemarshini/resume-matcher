from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import store
from .matching import Embedder, score_candidate
from .parsing import anonymize, extract_text, normalize, parse_jd, parse_resume

ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title="AI Resume Matcher", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
EMB: Embedder | None = None


def embedder() -> Embedder:
    global EMB
    if EMB is None:
        EMB = Embedder()
    return EMB


@app.on_event("startup")
def _warm():
    embedder()


def analyze(jd_text: str, files: list[tuple[str, bytes]], blind: bool = False) -> dict:
    jd_text = normalize(jd_text)
    words = len(jd_text.split())
    if words < 25:
        raise HTTPException(400, f"The job description has only {words} words. Paste the full text (at least 25 words) with the skills and requirements.")
    if not files:
        raise HTTPException(400, "Upload at least one resume (PDF or DOCX).")
    emb, jd = embedder(), parse_jd(jd_text)
    if not (jd["required_skills"] or jd["preferred_skills"] or jd["min_years"] or jd["education_level"]):
        raise HTTPException(400, "No skills, experience or education requirements were recognised in this job description. Please add the actual requirements.")
    jd["warnings"] = []
    if len(jd_text.splitlines()) < 4 and words > 40:
        jd["warnings"].append("This job description has almost no line breaks, so headings such as 'Preferred' may have been lost and nice-to-have skills counted as required. Paste it with its original line breaks.")
    candidates, errors = [], []
    for i, (fname, data) in enumerate(files):
        try:
            text = extract_text(fname, data)
            if len(text.split()) < 15:
                raise ValueError(f"only {len(text.split())} words of text, which is too little for a resume")
            info = parse_resume(text, fname)
            if not info["skills"] and not info["email"] and not info["years"]:
                raise ValueError("this does not look like a resume (no skills, contact details or work dates found)")
            if blind:  # score on anonymised text; hide identity everywhere
                text = anonymize(text, info["name"])
                info = {**info, "name": f"Candidate {i + 1:02d}", "email": None, "phone": None, "summary": None}
                fname = f"resume_{i + 1:02d}{Path(fname).suffix}"
            res = score_candidate(emb, jd, jd_text, text, info)
        except Exception as exc:
            errors.append({"filename": fname, "error": str(exc)})
            continue
        candidates.append({"id": f"c{i}", "filename": fname, **info, **res, "text": text})
    candidates.sort(key=lambda c: (-c["score"], -(c["breakdown"]["skills"]["score"] or 0)))
    for r, c in enumerate(candidates, 1):
        c["rank"] = r
    payload = {"jd": jd, "model": emb.name, "blind": blind, "candidates": candidates, "errors": errors}
    payload["session_id"] = store.save(payload)
    return _public(payload)


def _public(payload: dict) -> dict:
    """List view: everything except the (large) raw resume text."""
    return {**payload, "candidates": [{k: v for k, v in c.items() if k != "text"} for c in payload["candidates"]]}


@app.get("/api/health")
def health():
    return {"ok": True, "model": embedder().name}


@app.post("/api/analyze")
async def analyze_endpoint(
    jd_text: str = Form(""),
    jd_file: UploadFile | None = File(None),
    resumes: list[UploadFile] = File(...),
    blind: bool = Form(False),
):
    if jd_file is not None and jd_file.filename:
        try:
            jd_text = extract_text(jd_file.filename, await jd_file.read(), allow_text=True)
        except ValueError as exc:
            raise HTTPException(400, f"Job description file: {exc}")
    files = [(f.filename, await f.read()) for f in resumes]
    return analyze(jd_text, files, blind)


@app.post("/api/demo")
def demo(blind: bool = False):
    folder = ROOT / "sample_resumes"
    jd_path = ROOT / "sample_jd.txt"
    if not jd_path.exists() or not folder.exists():
        raise HTTPException(404, "Run `python scripts/generate_samples.py` first.")
    files = [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.suffix in (".pdf", ".docx")]
    out = analyze(jd_path.read_text(), files, blind)
    out["jd_text"] = jd_path.read_text()
    return out


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    data = store.load(sid)
    if not data:
        raise HTTPException(404, "Session not found")
    return _public(data)


@app.get("/api/sessions/{sid}/candidates/{cid}")
def get_candidate(sid: str, cid: str):
    data = store.load(sid)
    cand = next((c for c in (data or {}).get("candidates", []) if c["id"] == cid), None)
    if not cand:
        raise HTTPException(404, "Candidate not found")
    return {**cand, "jd": data["jd"]}


_EVAL_CACHE: dict = {}


@app.get("/api/evaluate")
def evaluate():
    """Validation report: baselines vs hybrid, held-out weight tuning, fairness test."""
    from .evaluation import run
    if "r" not in _EVAL_CACHE:
        _EVAL_CACHE["r"] = run(embedder())
    return _EVAL_CACHE["r"]


@app.post("/api/sessions/{sid}/candidates/{cid}/summary")
def candidate_summary(sid: str, cid: str):
    from .summary import summarize
    data = store.load(sid)
    cand = next((c for c in (data or {}).get("candidates", []) if c["id"] == cid), None)
    if not cand:
        raise HTTPException(404, "Candidate not found")
    return summarize(cand, data["jd"])
