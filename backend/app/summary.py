"""Recruiter-facing candidate summary.

The LLM only ever sees the *structured facts* produced by the scorer (never the raw resume), so it
cannot invent experience and, in blind mode, never sees identity information. Without an API key
(or on any error) a deterministic template is used, so the feature always works."""
import os

import httpx

MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")


def facts(c: dict, jd: dict) -> dict:
    sm = c["skills_match"]
    return {
        "role": jd["title"], "current_title": c.get("title"), "score": c["score"], "verdict": c["verdict"],
        "years_experience": c["years"], "relevant_years": c["experience"].get("relevant"), "years_required": jd["min_years"],
        "education": c["education_match"]["candidate"], "education_required": c["education_match"]["required"],
        "matched_required": [m["skill"] for m in sm["matched"] if m["required"]],
        "listed_but_unproven": [m["skill"] for m in sm["matched"] if not m["verified"]],
        "related_only": [f"{p['skill']} (has {p['via']})" for p in sm["partial"]],
        "missing_required": [m["skill"] for m in sm["missing"] if m["required"]],
        "missing_preferred": [m["skill"] for m in sm["missing"] if not m["required"]],
    }


def template_summary(c: dict, jd: dict) -> str:
    f = facts(c, jd)
    who = f["current_title"] or "The candidate"
    rel = f" (about {f['relevant_years']:g} relevant)" if f["relevant_years"] is not None else ""
    s = f"{who} scores {f['score']:.0f}/100 ({f['verdict'].lower()}) for {f['role']}, with {f['years_experience']:g} years of experience{rel}"
    s += f" against {f['years_required']:g} required. " if f["years_required"] else ". "
    s += f"Covers {len(f['matched_required'])} required skills" + (f" including {', '.join(f['matched_required'][:4])}. " if f["matched_required"] else ". ")
    if f["missing_required"]:
        s += f"Gaps: {', '.join(f['missing_required'][:4])}. "
    if f["listed_but_unproven"]:
        s += f"{', '.join(f['listed_but_unproven'][:3])} appear in the skills list without supporting experience. "
    focus = (f["missing_required"] or f["listed_but_unproven"] or f["missing_preferred"] or ["depth on the core stack"])[0]
    return s + f"Suggested interview focus: {focus}."


def llm_summary(c: dict, jd: dict) -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    prompt = ("You support a recruiter. Using ONLY the JSON facts below, write a neutral 3-4 sentence summary of how well "
              "this candidate fits the role, then one sentence starting 'Suggested interview focus:'. Do not invent details, "
              "do not mention gender, age, nationality or name.\n\n" + str(facts(c, jd)))
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=30,
                   headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                   json={"model": MODEL, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def summarize(c: dict, jd: dict) -> dict:
    try:
        text = llm_summary(c, jd)
        if text:
            return {"text": text, "source": f"Claude ({MODEL})"}
    except Exception as exc:
        print(f"[warn] LLM summary failed, using template: {exc!s:.100}")
    return {"text": template_summary(c, jd), "source": "template"}
