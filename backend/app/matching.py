"""Hybrid scoring engine.

Match % = 40% Skills + 30% Semantic + 20% Experience + 10% Education
(weights of components the JD does not specify are redistributed proportionally)
"""
import re
import numpy as np

from .skills import related
from .parsing import LEVEL_LABEL, BULLET

WEIGHTS = {"skills": 0.40, "semantic": 0.30, "experience": 0.20, "education": 0.10}


class Embedder:
    """Sentence-Transformers (all-MiniLM-L6-v2). Falls back to TF-IDF if the model is unavailable."""

    def __init__(self):
        self.model, self.name, self.cache = None, "TF-IDF (fallback)", {}
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            self.name = "all-MiniLM-L6-v2"
        except Exception as exc:  # offline / not installed
            print(f"[warn] sentence-transformers unavailable ({exc!s:.80}); using TF-IDF fallback")

    @property
    def semantic(self) -> bool:
        return self.model is not None

    def _enc(self, texts):
        new = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if new:
            vecs = self.model.encode(new, normalize_embeddings=True, show_progress_bar=False)
            self.cache.update(zip(new, vecs))
        return np.stack([self.cache[t] for t in texts])

    def sim(self, a: list[str], b: list[str]) -> np.ndarray:
        """Cosine-similarity matrix between two lists of texts."""
        if not a or not b:
            return np.zeros((max(len(a), 1), max(len(b), 1)))
        if self.model:
            return self._enc(a) @ self._enc(b).T
        from sklearn.feature_extraction.text import TfidfVectorizer
        try:
            v = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True).fit(a + b)
            return (v.transform(a) @ v.transform(b).T).toarray()
        except ValueError:
            return np.zeros((len(a), len(b)))


def chunks(text: str, max_words: int = 45) -> list[str]:
    lines = [re.sub(BULLET, "", l.strip()) for l in text.splitlines()]
    lines = [l for l in lines if len(l.split()) >= 3]
    out, cur, n = [], [], 0
    for l in lines:
        w = len(l.split())
        if cur and n + w > max_words:
            out.append(" ".join(cur)); cur, n = [], 0
        cur.append(l); n += w
    if cur:
        out.append(" ".join(cur))
    return out


# ---------------------------------------------------------------- components
def skills_component(emb: Embedder, jd: dict, rskills: list[str], evidenced: list[str]) -> dict:
    sw = jd.get("skill_weights", {})
    items = [(s, sw.get(s, 1.0), True) for s in jd["required_skills"]] + [(s, 0.5, False) for s in jd["preferred_skills"]]
    rset = set(rskills)
    matched, partial, missing, total, got = [], [], [], 0.0, 0.0
    for skill, w, is_req in items:
        total += w
        if skill in rset:
            verified = skill in evidenced  # listed AND shown in work history -> full credit; listed only -> 50%
            got += w * (1.0 if verified else 0.5)
            matched.append({"skill": skill, "required": is_req, "verified": verified})
            continue
        via, credit, kind = None, 0.0, None
        rel = [r for r in rskills if related(skill, r)]
        if rel:
            via, credit, kind = rel[0], 0.5, "related technology"
        elif emb.semantic and rskills:
            sims = emb.sim([skill], rskills)[0]
            j = int(sims.argmax())
            a, b = skill.lower(), rskills[j].lower()
            if sims[j] >= 0.80 and a not in b and b not in a:
                via, credit, kind = rskills[j], 0.6, f"semantic match ({sims[j]:.2f})"
        if credit:
            got += w * credit
            partial.append({"skill": skill, "required": is_req, "via": via, "kind": kind, "credit": credit, "w": w})
        else:
            missing.append({"skill": skill, "required": is_req, "w": w})
    wanted = {i[0] for i in items}
    return {
        "score": got / total if total else None, "total": total,
        "matched": matched, "partial": partial, "missing": missing,
        "extra": [s for s in rskills if s not in wanted][:14],
    }


def semantic_component(emb: Embedder, jd_text: str, res_text: str) -> dict:
    """0.35 * whole-document similarity + 0.65 * chunk-level coverage of the JD.
    Coverage = for each JD chunk, how well its best-matching resume chunk fits; averaged."""
    jc, rc = chunks(jd_text), chunks(res_text)
    doc = float(emb.sim([jd_text[:3000]], [res_text[:3000]])[0, 0])
    if jc and rc:
        M = emb.sim(jc, rc)
        best = M.max(axis=1)
        order = np.argsort(-best)
        evidence = [{"jd": jc[i][:150], "resume": rc[int(M[i].argmax())][:150], "similarity": round(float(best[i]), 2)} for i in order[:2]]
        gap = {"jd": jc[order[-1]][:150], "similarity": round(float(best[order[-1]]), 2)}
        cov = float(best.mean())
    else:
        evidence, gap, cov = [], None, doc
    raw = 0.35 * doc + 0.65 * cov
    lo, hi = (0.15, 0.60) if emb.semantic else (0.02, 0.30)  # rescale raw cosine to 0-1
    return {"score": float(np.clip((raw - lo) / (hi - lo), 0, 1)), "raw": round(raw, 3),
            "doc_similarity": round(doc, 3), "coverage": round(cov, 3), "evidence": evidence, "gap": gap}


def experience_component(cand_years: float, req: float | None, relevance: float = 1.0) -> dict:
    """Relevant experience = total years x relevance factor. Relevance (0-1) is how well the candidate's skills and
    content fit the role; >= 0.8 counts years in full, below that they are scaled down proportionally."""
    if not req:
        return {"score": None, "candidate": cand_years, "relevant": None, "relevance": None, "required": None, "ratio": None}
    rel_years = round(cand_years * min(1.0, relevance / 0.8), 1)
    ratio = min(rel_years / req, 1.0)
    return {"score": ratio, "candidate": cand_years, "relevant": rel_years, "relevance": round(relevance, 2),
            "required": req, "ratio": round(ratio, 2)}


def education_component(cand: int | None, req: int | None) -> dict:
    if not req:
        return {"score": None, "candidate": LEVEL_LABEL.get(cand), "required": None}
    c = cand or 0
    score = 1.0 if c >= req else 0.5 if c == req - 1 and c > 0 else 0.0
    return {"score": score, "candidate": LEVEL_LABEL.get(cand, "Not found"), "required": LEVEL_LABEL.get(req)}


# -------------------------------------------------------------------- score
def combine(comps: dict, weights: dict = WEIGHTS):
    """comps: {component: score 0-1 or None}. Components that are None are dropped and weights renormalised."""
    active = sum(w for k, w in weights.items() if comps[k] is not None)
    breakdown, total = {}, 0.0
    for k, w in weights.items():
        s = comps[k]
        eff = w / active if (s is not None and active) else 0.0
        pts = (s or 0.0) * eff * 100
        total += pts
        breakdown[k] = {"score": None if s is None else round(s * 100, 1), "weight": round(eff * 100, 1), "points": round(pts, 1)}
    return round(total, 1), breakdown


def verdict(score: float) -> str:
    return "Strong match" if score >= 80 else "Good match" if score >= 65 else "Partial match" if score >= 45 else "Weak match"


def score_candidate(emb: Embedder, jd: dict, jd_text: str, res_text: str, info: dict) -> dict:
    sk = skills_component(emb, jd, info["skills"], info.get("evidenced_skills", info["skills"]))
    sem = semantic_component(emb, jd_text, res_text)
    parts = [(v, w) for v, w in ((sk["score"], 0.6), (sem["score"], 0.4)) if v is not None]
    relevance = sum(v * w for v, w in parts) / sum(w for _, w in parts)
    exp = experience_component(info["years"], jd["min_years"], relevance)
    edu = education_component(info["education_level"], jd["education_level"])
    comps = {"skills": sk, "semantic": sem, "experience": exp, "education": edu}
    total, breakdown = combine({k: c["score"] for k, c in comps.items()})

    # Counterfactual: how many points would each gap add if it were closed?
    eff_sk, what_if = breakdown["skills"]["weight"] / 100, []
    if sk["total"]:
        for m in sk["missing"] + sk["partial"]:
            gain = m["w"] * (1 - m.get("credit", 0.0)) / sk["total"] * eff_sk * 100
            what_if.append({"skill": m["skill"], "gain": round(gain, 1), "required": m["required"]})
        what_if = sorted(what_if, key=lambda x: -x["gain"])[:4]

    reasons = []
    req_total = len(jd["required_skills"])
    if req_total:
        got = [m["skill"] for m in sk["matched"] if m["required"]]
        reasons.append(f"Has {len(got)} of {req_total} required skills" + (f" ({', '.join(got[:6])})." if got else "."))
    unv = [m["skill"] for m in sk["matched"] if not m["verified"]]
    if unv:
        reasons.append(f"{len(unv)} listed skills have no supporting work experience ({', '.join(unv[:4])}) - counted at 50%.")
    miss_req = [m["skill"] for m in sk["missing"] if m["required"]]
    if miss_req:
        reasons.append(f"Missing required: {', '.join(miss_req[:6])}.")
    for p in sk["partial"][:3]:
        reasons.append(f"{p['via']} earns partial credit for {p['skill']} ({p['kind']}).")
    if exp["required"]:
        c, r = exp["relevant"], exp["required"]
        reasons.append(f"{exp['candidate']:g} years in total, about {c:g} relevant to this role, vs {r:g} required" + (" - requirement met." if c >= r else f" - {r - c:g} years short ({exp['ratio'] * 100:.0f}% credit)."))
    if edu["required"]:
        reasons.append(f"Education: {edu['candidate']} vs {edu['required']} required" + (" - met." if edu["score"] == 1 else " - partially met." if edu["score"] else " - not met."))
    lvl = "high" if sem["score"] >= .7 else "moderate" if sem["score"] >= .4 else "low"
    reasons.append(f"Overall content alignment with the JD is {lvl} (semantic score {sem['score'] * 100:.0f}/100).")

    if what_if:
        reasons.append(f"Closing the top gaps ({', '.join(w['skill'] for w in what_if[:3])}) would add about +{sum(w['gain'] for w in what_if[:3]):.1f} points.")
    return {
        "what_if": what_if,
        "score": total, "verdict": verdict(total), "breakdown": breakdown,
        "skills_match": {k: sk[k] for k in ("matched", "partial", "missing", "extra")},
        "experience": exp, "education_match": edu,
        "semantic": {k: sem[k] for k in ("raw", "doc_similarity", "coverage", "evidence", "gap")},
        "reasons": reasons,
    }
