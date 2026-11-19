# FitRank – AI-Based Resume Matching & Candidate Ranking

Paste a job description, upload 10+ resumes (PDF/DOCX) and get an **explainable 0–100 match score** for every candidate, a ranking dashboard, and a per-candidate analysis (matched/missing skills, experience comparison, reasons, evidence).

## Quick start

```bash
# 1. Backend (Python 3.10+)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                          # first run downloads the ~90 MB MiniLM model
python ../scripts/generate_samples.py                    # optional: regenerates 14 synthetic resumes
uvicorn app.main:app --reload --port 8000

# 2. Frontend (Node 18+) – new terminal
cd frontend && npm install && npm run dev                # http://localhost:5173
```
Click **Try with sample data** for an instant demo, or upload your own JD + resumes. Tests: `cd backend && pytest`.
If `sentence-transformers` cannot load (offline), the engine automatically falls back to TF-IDF so the app still runs; the UI shows which model is active.

**Docker (one command):** `docker compose up --build`, then open http://localhost:8080. Set `ANTHROPIC_API_KEY` in your environment first if you want Claude-written summaries.

## Architecture

```
React (Vite)  ──/api──▶  FastAPI
 Inputs · Ranking table      │  parsing.py   PDF/DOCX → text → structured fields (regex + section detection)
 Candidate drawer            │  skills.py    taxonomy (~100 skills, aliases, implied + related skills)
                             │  matching.py  hybrid scorer (skills / semantic / experience / education)
                             └  store.py     SQLite session store (results can be reopened by id)
```

| Endpoint | Purpose |
|---|---|
| `POST /api/analyze` | multipart: `jd_text` or `jd_file`, plus `resumes[]` → ranked results |
| `POST /api/demo` | runs the bundled sample JD + 14 synthetic resumes |
| `GET /api/sessions/{id}` | ranked list for a past analysis |
| `GET /api/sessions/{id}/candidates/{cid}` | full candidate analysis incl. parsed text |

**Storage:** SQLite (zero-config, a single table of JSON analysis sessions in `store.py`). The assignment lists PostgreSQL/MongoDB as preferred, not required; moving to either only means re-implementing the two functions `save`/`load`.

## Parsing

* **Text:** `pdfplumber` (PDF), `python-docx` (paragraphs + tables).
* **Sections:** headings (Summary / Experience / Education / Skills…) are detected so dates in *Education* are not counted as work experience.
* **Experience:** all date ranges in the work history are converted to months and **merged as a union**, so overlapping jobs and freelance work aren't double-counted. Supported formats: `Mar 2021`, `March, 2021`, `Sept. 2015`, `Jan'19`, `03/2021`, `03-2021`, `2021-03`, bare years, `Present / Current / Till date / Since 2019`. Ranges on education lines are ignored even when the resume has no headings. Falls back to "N years of experience" statements.
* **Layouts:** two-column PDFs are detected by an empty vertical gutter and read column by column; header lines like `NAME | email | phone` and names that are not on the first line are handled. Parser accuracy is regression-tested on 8 deliberately messy resumes (`sample_resumes_messy/`, `backend/tests/test_messy.py`).
* **Skills:** word-boundary regex over the taxonomy (`java` never matches `javascript`; `Postgres` → PostgreSQL). Implied skills are added (Spring Boot ⇒ Java).
* **JD:** skills under a *Preferred / Nice to have* heading (or marked "is a plus") are **preferred**, all others **required**; minimum years and education level are extracted by regex.

## Matching algorithm

```
Match % = 100 × ( 0.40·Skills + 0.30·Semantic + 0.20·Experience + 0.10·Education )
```
Components the JD does not specify (e.g. no education stated) are dropped and the remaining weights are **renormalised**, so a candidate is never penalised for something the JD didn't ask.

1. **Skills (40%)** – weighted coverage: required skill = 1.0, preferred = 0.5. **Core skills** (named in the job title or repeated through the JD, e.g. Java in a "Java Backend Engineer" role) weigh up to 2.5×, so a missing core language hurts more than a missing tool (marked ★ in the UI). Per skill the credit is
   *exact/alias/implied match = 1.0* · *related technology (e.g. MySQL for PostgreSQL) = 0.5* · *embedding similarity ≥ 0.80 between skill names = 0.6* · *otherwise 0*.
2. **Semantic (30%)** – goes beyond keywords. `all-MiniLM-L6-v2` embeds the JD and resume. `raw = 0.35 × whole-document cosine + 0.65 × coverage`, where **coverage** = for each JD chunk, the cosine of its best-matching resume chunk, averaged. Chunking avoids the 256-token truncation of sentence transformers and checks that *every* JD requirement is addressed. Raw cosines of related text cluster in 0.15–0.60, so they are rescaled linearly to 0–1.
3. **Relevant experience (20%)** – total years are scaled by a *relevance factor* = `0.6·skills + 0.4·semantic` (relevance ≥ 0.8 counts the years in full, lower values scale them down), then `min(relevant_years / required_years, 1)`. Six years as a Node.js developer therefore count for far less than six years of Java when the role is a Java role. No penalty for being over-qualified.
4. **Education (10%)** – 1.0 if the level is met, 0.5 if one level below, else 0 (Diploma < Bachelor's < Master's < PhD).

**Worked example** – JD needs 5 yrs, Bachelor's; skills 8/9 required (+ partial credit) → 0.88; semantic 0.62; experience 4 yrs → 0.8; education met → 1.0:
`100 × (0.40·0.88 + 0.30·0.62 + 0.20·0.80 + 0.10·1.0) = 79.8%`

**Explainability** – every number in the UI is traceable: the stacked bar shows the points each component contributed, the reasons list is generated from the sub-scores, and the "Strongest evidence / Least covered" panel shows the actual JD sentence matched to the resume sentence that satisfied it (or didn't).

## Beyond the brief: what makes the scoring trustworthy

1. **Claimed vs demonstrated skills.** A skill listed in the Skills section but never mentioned in the work history earns **50%** credit (shown as "listed only"). This defends against keyword stuffing: the bundled *Kavya Reddy* resume lists 14 JD keywords with 1 year of clerical experience; a pure keyword matcher would rank her near the top, while the hybrid scorer places her below the genuine senior Java candidates.
2. **Validation harness** (`backend/app/evaluation.py`, `GET /api/evaluate`, "Validation" button). Graded relevance labels (`sample_ground_truth.json`) are scored with **NDCG@5, Spearman ρ and pairwise ordering accuracy** against baselines (keyword overlap, whole-document similarity) and single components (ablation). The benchmark deliberately includes a keyword stuffer and a paraphraser. Weights are tuned by grid search with **2-fold cross-validation** (fit on one half, evaluate on the other) to avoid reporting in-sample numbers. Results with the real `all-MiniLM-L6-v2` model on the 14-resume benchmark:

| Method | NDCG@5 | Spearman | Pairwise |
|---|---|---|---|
| Keyword overlap (baseline) | 0.75 | 0.60 | 81% |
| Whole-document similarity (baseline) | 0.70 | 0.83 | 89% |
| Skills component only | 0.84 | 0.85 | 92% |
| Semantic component only | 0.82 | 0.69 | 86% |
| **Hybrid (default weights)** | **0.97** | **0.94** | **97%** |

The hybrid clearly beats both baselines: against keyword overlap NDCG@5 is 0.97 vs 0.75 and Spearman 0.94 vs 0.60; against whole-document similarity (a strong baseline) NDCG@5 is 0.97 vs 0.70 and Spearman 0.94 vs 0.83. NDCG@5 measures the quality of the top of the list, which is what recruiters actually read. Grid-searched weights (skills 20 / semantic 10 / experience 10 / education 60) fitted on one half **scored worse on the other half** (Spearman 0.77 vs 0.89), so they overfit; the hand-set defaults were deliberately kept.

**Honest note:** the scorer was refined (relevant-experience scaling, core-skill weighting; before them the hybrid scored NDCG@5 0.84 / Spearman 0.86) after inspecting failures on this same 14-resume benchmark, so these are development-set numbers and are optimistic. A second, untouched benchmark with a different job description is the right next step. The Validation view always evaluates this bundled benchmark, not the files you upload.
3. **Blind screening** (checkbox). Names, emails, phones, gendered words and protected-attribute lines (gender, DOB, marital status…) are removed *before* scoring and hidden in the UI. The fairness check re-scores every resume with five different names: with blind screening on the score change is exactly **0.0** (versus up to 2.2 points in standard mode with the real embedding model).
4. **Counterfactual "what-if".** For each gap we compute exactly how many points closing it would add ("Docker: +4.4 pts"), turning the score into actionable feedback.
5. **Live weight sliders.** Recruiters re-weight skills / semantics / experience / education per role and the ranking updates instantly; component scores are returned by the API, so no re-computation is needed.

6. **Recruiter summaries.** "Write recruiter summary" in the candidate panel asks Claude for a neutral 3–4 sentence assessment plus an interview focus. The model receives **only the structured scoring facts** (never the raw resume), which prevents invented experience and keeps blind mode blind. Without `ANTHROPIC_API_KEY`, or on any API error, a deterministic template is used, so the feature never breaks.

## Limitations & next steps

* The evaluation set is small and synthetic, so it demonstrates the *method*; defaults are a prior and should be refit on real recruiter labels.
* Parsing is heuristic (unusual date wording, header lines that span two columns, tables and text inside images are still weak spots); the skills taxonomy is finite — an NER model or LLM extraction would widen coverage.
* Scanned PDFs need OCR. Scores are a decision aid, not an automated hiring decision: review for bias before real use.
* Possible extensions: cross-encoder re-ranking, LLM-written summaries, bias-masking of names, PostgreSQL storage.

All bundled resumes are **synthetic**; no real personal data is used.
