"""Validation harness: does the hybrid scorer rank like a recruiter would?

* Ground truth: graded relevance labels (0-3) in sample_ground_truth.json
* Metrics: NDCG@5, Spearman rho, pairwise ordering accuracy
* Baselines: keyword overlap, whole-document similarity, single components (ablation)
* Weight tuning: grid search with 2-fold cross-validation (tune on one half, test on the other)
* Fairness: swap the candidate's name for names from other backgrounds, measure score change
"""
import json
from itertools import product
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from .matching import WEIGHTS, combine, score_candidate
from .parsing import anonymize, extract_text, parse_jd, parse_resume

ROOT = Path(__file__).resolve().parents[2]
ALT_NAMES = ["Mohammed Al-Farsi", "Emily Johnson", "Wei Zhang", "Olga Petrova", "Adaeze Okafor"]


def ndcg(scores, rels, k=5):
    order = np.argsort(-np.asarray(scores), kind="stable")[:k]
    gain = lambda idx: sum((2 ** rels[i] - 1) / np.log2(r + 2) for r, i in enumerate(idx))
    ideal = np.argsort(-np.asarray(rels), kind="stable")[:k]
    return gain(order) / gain(ideal) if gain(ideal) else 0.0


def pairwise(scores, rels):
    ok = tot = 0.0
    for i in range(len(rels)):
        for j in range(len(rels)):
            if rels[i] > rels[j]:
                tot += 1
                ok += 1 if scores[i] > scores[j] else 0.5 if scores[i] == scores[j] else 0
    return ok / tot if tot else 0.0


def metrics(scores, rels):
    rho = spearmanr(scores, rels)[0]
    return {"ndcg5": round(float(ndcg(scores, rels)), 3), "spearman": round(float(0 if np.isnan(rho) else rho), 3),
            "pairwise": round(float(pairwise(scores, rels)), 3)}


def _objective(m):
    return m["ndcg5"] + m["spearman"] + m["pairwise"]


def _grid(step=0.1):
    n = round(1 / step)
    for a in product(range(n + 1), repeat=3):
        if sum(a) <= n:
            yield dict(zip(WEIGHTS, [x * step for x in (*a, n - sum(a))]))


def _scores(comps, w):
    return [combine(c, w)[0] for c in comps]


def _tune(comps, rels):
    """Best weights on the given rows; ties broken toward the default weights (regularisation)."""
    def key(w):
        return (-_objective(metrics(_scores(comps, w), rels)), sum(abs(w[k] - WEIGHTS[k]) for k in WEIGHTS))
    return min(_grid(), key=key)


def run(emb) -> dict:
    jd_text = (ROOT / "sample_jd.txt").read_text()
    jd, truth = parse_jd(jd_text), json.loads((ROOT / "sample_ground_truth.json").read_text())
    rows = []
    for p in sorted((ROOT / "sample_resumes").iterdir()):
        if p.suffix not in (".pdf", ".docx"):
            continue
        text = extract_text(p.name, p.read_bytes())
        info = parse_resume(text, p.name)
        rows.append((text, info, score_candidate(emb, jd, jd_text, text, info), truth.get(info["name"], 0)))
    rels = [r[3] for r in rows]
    comps = [{k: (r[2]["breakdown"][k]["score"] / 100 if r[2]["breakdown"][k]["score"] is not None else None) for k in WEIGHTS} for r in rows]

    def kw(res):  # keyword overlap: exact matches only, no semantic/related credit
        m = res["skills_match"]
        tot = sum(x["w"] for x in m["missing"] + m["partial"]) + sum(1.0 if x["required"] else 0.5 for x in m["matched"])
        return sum(1.0 if x["required"] else 0.5 for x in m["matched"]) / tot if tot else 0

    table = [
        ("Keyword overlap (baseline)", [kw(r[2]) for r in rows]),
        ("Whole-document similarity (baseline)", [r[2]["semantic"]["doc_similarity"] for r in rows]),
        ("Skills component only", [c["skills"] or 0 for c in comps]),
        ("Semantic component only", [c["semantic"] or 0 for c in comps]),
        ("Hybrid (default weights)", [r[2]["score"] for r in rows]),
    ]
    results = [{"method": n, **metrics(s, rels)} for n, s in table]

    # 2-fold cross-validation of the weights: tune on one half, evaluate on the other
    idx = list(range(len(rows))); folds = [idx[0::2], idx[1::2]]; held_def, held_tuned = [], []
    for tr, te in (folds, folds[::-1]):
        w = _tune([comps[i] for i in tr], [rels[i] for i in tr])
        held_tuned.append(metrics(_scores([comps[i] for i in te], w), [rels[i] for i in te]))
        held_def.append(metrics(_scores([comps[i] for i in te], WEIGHTS), [rels[i] for i in te]))
    avg = lambda ms: {k: round(float(np.mean([m[k] for m in ms])), 3) for k in ms[0]}
    final_w = _tune(comps, rels)

    # fairness: same resume, different name
    def delta(blind):
        worst = 0.0
        for text, info, res, _ in rows:
            base = res["score"] if not blind else score_candidate(emb, jd, jd_text, anonymize(text, info["name"]), info)["score"]
            for alt in ALT_NAMES:
                t = text.replace(info["name"], alt) if info["name"] else text
                i2 = parse_resume(t)
                t2 = anonymize(t, i2["name"]) if blind else t
                worst = max(worst, abs(score_candidate(emb, jd, jd_text, t2, i2)["score"] - base))
        return round(worst, 2)

    return {
        "model": emb.name, "n_resumes": len(rows), "methods": results,
        "tuning": {"default_weights": WEIGHTS, "tuned_weights": {k: round(v, 2) for k, v in final_w.items()},
                   "held_out_default": avg(held_def), "held_out_tuned": avg(held_tuned)},
        "fairness": {"names_tested": len(ALT_NAMES), "max_score_change_standard": delta(False), "max_score_change_blind": delta(True)},
    }
