"""Text extraction + structured parsing for resumes and job descriptions."""
import io
import re
import zipfile
import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path

from .skills import extract_skills

BULLET = r"^[-•*▪●◦·]\s*"
MON = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
MONTHS = {m: i + 1 for i, m in enumerate(MON.split("|"))}
LEVEL_LABEL = {4: "PhD", 3: "Master's", 2: "Bachelor's", 1: "Diploma"}
EDU_PATTERNS = [
    (4, r"\bph\.?\s?d\b|doctorate|doctoral"),
    (3, r"\bmaster'?s?\b|\bm\.?\s?tech\b|\bm\.sc\b|\bmsc\b|\bm\.s\.|\bmca\b|\bmba\b"),
    (2, r"\bbachelor'?s?\b|\bb\.?\s?tech\b|\bb\.e\.?\b|\bb\.sc\b|\bbsc\b|\bb\.s\.|\bbca\b|\bundergraduate\b|\bdegree\b"),
    (1, r"\bdiploma\b"),
]
HEADINGS = {
    "summary": r"summary|profile|objective|about( me)?|professional summary|career objective",
    "experience": r"(work |professional |relevant )?experience|employment( history)?|work history|career history",
    "education": r"education|academics?|academic (background|qualifications?)|qualifications?",
    "skills": r"(technical |key |core )?skills|technologies|tech stack|competencies",
    "projects": r"(personal )?projects?",
    "other": r"certifications?|achievements?|awards?|publications?|languages|interests|references|hobbies",
}
RANGE = re.compile(
    rf"(?:\b({MON})[a-z]*\.?,?\s+)?\b((?:19|20)\d{{2}})\s*(?:-|–|—|to|until)\s*"
    rf"(?:(?:\b({MON})[a-z]*\.?,?\s+)?\b((?:19|20)\d{{2}})\b|(present|current|now|ongoing|till date))",
    re.I,
)


# ---------------------------------------------------------------- extraction
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(data: bytes) -> str:
    """Reads .docx with the standard library only (no lxml / python-docx), so it works on locked-down machines."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    lines = []
    for para in root.iter(W + "p"):  # includes paragraphs inside tables
        parts = []
        for node in para.iter():
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag in (W + "tab", W + "br"):
                parts.append(" ")
        lines.append("".join(parts))
    return "\n".join(lines)


def _pdf_text(data: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:  # pdfplumber missing or blocked -> pure-Python reader
        from pypdf import PdfReader
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(data)).pages)


def extract_text(filename: str, data: bytes, allow_text: bool = False) -> str:
    """Resumes: PDF/DOCX only. allow_text=True additionally accepts .txt (used for job descriptions).
    File *content* is verified, so a text file renamed to .pdf is rejected."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext == "pdf":
        if b"%PDF-" not in data[:1024]:
            raise ValueError("not a real PDF (the content is not PDF data; was the file renamed?)")
        text = _pdf_text(data)
    elif ext == "docx":
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise ValueError("not a real DOCX (the content is not a Word document; was the file renamed?)")
        try:
            text = _docx_text(data)
        except (KeyError, ET.ParseError):
            raise ValueError("not a valid DOCX file")
    elif ext == "txt" and allow_text:
        text = data.decode("utf-8", "ignore")
    else:
        raise ValueError(f"unsupported file type '.{ext}'. Only PDF and DOCX are accepted" + (" (or TXT)" if allow_text else ""))
    text = normalize(text)
    if len(text) < 30:
        raise ValueError("no readable text found (scanned PDF? try an OCR'd copy)")
    return text


def normalize(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def split_sections(text: str) -> dict[str, str]:
    cur, out = "header", {"header": []}
    for line in text.splitlines():
        s = line.strip().strip(":").strip().lower()
        key = next((k for k, p in HEADINGS.items() if s and len(s) <= 40 and re.fullmatch(p, s)), None)
        if key:
            cur = key
            out.setdefault(cur, [])
        else:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


# ------------------------------------------------------------------ helpers
def compute_years(exp_text: str) -> float:
    """Union of all 'Mon YYYY - Mon YYYY/Present' ranges, so overlaps are not double counted."""
    today = dt.date.today()
    now = today.year * 12 + today.month
    spans = []
    for m in RANGE.finditer(exp_text):
        m1, y1, m2, y2, pres = m.groups()
        s = int(y1) * 12 + (MONTHS[m1.lower()[:3]] if m1 else 1)
        e = now if pres else int(y2) * 12 + (MONTHS[m2.lower()[:3]] if m2 else 1)
        e = min(e, now)
        if e >= s and int(y1) >= 1970:
            spans.append((s, e))
    spans.sort()
    total, cs, ce = 0, None, None
    for s, e in spans:
        if ce is None or s > ce:
            if ce is not None:
                total += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    if ce is not None:
        total += ce - cs
    return round(total / 12, 1)


def stated_years(text: str) -> float | None:
    vals = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?\s+(?:[\w-]+\s+){0,3}?experience", text, re.I)
    vals += re.findall(r"experience\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text, re.I)
    vals = [float(v) for v in vals if float(v) <= 40]
    return max(vals) if vals else None


def education_level(text: str, lowest: bool = False):
    levels = [lvl for lvl, p in EDU_PATTERNS if re.search(p, text, re.I)]
    if not levels:
        return None
    return min(levels) if lowest else max(levels)


def guess_name(lines: list[str]) -> str | None:
    for l in lines[:6]:
        s = l.strip()
        if not s or "@" in s or re.search(r"\d", s) or re.search(r"resume|curriculum|vitae|\bcv\b", s, re.I):
            continue
        w = s.split()
        if 2 <= len(w) <= 4 and all(re.fullmatch(r"[A-Za-z.'\-]+", x) for x in w):
            return s.title() if s.isupper() else s
    return None


# ------------------------------------------------------------------ resume
def parse_resume(text: str, filename: str = "") -> dict:
    lines = [l for l in text.splitlines() if l.strip()]
    sec = split_sections(text)
    name = guess_name(lines)
    title = None
    if name:
        i = next((k for k, l in enumerate(lines[:6]) if l.strip().lower() == name.lower()), None)
        if i is not None and i + 1 < len(lines):
            c = lines[i + 1].strip()
            if len(c.split()) <= 8 and "@" not in c and not re.search(r"\d{4}", c):
                title = c
    email = (re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text) or [None])[0]
    phone = (re.search(r"(\+?\d[\d\s().-]{8,}\d)", text) or [None])[0]

    exp_text = sec.get("experience") or text.replace(sec.get("education", "\0"), "")
    computed = compute_years(exp_text)
    claimed = stated_years(text)
    years, source = (computed, "date ranges") if computed > 0 else (claimed or 0.0, "stated in text" if claimed else "not found")

    edu_src = sec.get("education") or text
    edu_lines = [l.strip()[:110] for l in edu_src.splitlines() if any(re.search(p, l, re.I) for _, p in EDU_PATTERNS)]
    evidence = "\n".join(sec.get(k, "") for k in ("experience", "projects", "summary"))
    all_skills = extract_skills(text, add_implied=True)
    return {
        "evidenced_skills": extract_skills(evidence, add_implied=True) if sec.get("experience") else all_skills,
        "name": name or Path(filename).stem.replace("_", " ").title() or "Unknown",
        "title": title,
        "email": email,
        "phone": phone.strip() if phone else None,
        "years": years,
        "years_source": source,
        "skills": all_skills,
        "education": edu_lines[:3],
        "education_level": education_level(edu_src),
        "summary": " ".join(sec.get("summary", "").split())[:260] or None,
    }


# ---------------------------------------------------------------------- JD
def parse_jd(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    req, pref, bullets, mode = [], [], [], "req"
    for l in lines:
        low = l.lower()
        is_bullet = bool(re.match(BULLET, l))
        head = len(l) < 60 and not is_bullet
        if head and re.search(r"preferred|nice to have|good to have|bonus|desirable|plus", low):
            mode = "pref"
            continue
        if head and re.search(r"required|requirements|must have|responsibilit|qualification|what you|about|skills|who you", low):
            mode = "req"
            continue
        is_pref = mode == "pref" or re.search(r"\(preferred\)|nice to have|(is|are) a plus|good to have|bonus", low)
        for s in extract_skills(l):
            (pref if is_pref else req).append(s)
        if is_bullet:
            bullets.append(re.sub(BULLET, "", l))
    req = list(dict.fromkeys(req))
    pref = [s for s in dict.fromkeys(pref) if s not in req]
    # Core skills count more: named in the job title, or repeated across the description
    title_skills = set(extract_skills(lines[0])) if lines else set()
    counts: dict[str, int] = {}
    for l in lines:
        for s in extract_skills(l):
            counts[s] = counts.get(s, 0) + 1
    skill_weights = {s: round(1.0 + (1.0 if s in title_skills else 0.0) + 0.25 * min(counts.get(s, 1) - 1, 2), 2) for s in req}

    years = None
    m = re.search(r"(\d{1,2})\s*(?:-|–|to)\s*\d{1,2}\s*\+?\s*(?:years?|yrs?)", text, re.I) \
        or re.search(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text, re.I)
    if m:
        years = float(m.group(1))
    level = education_level(text, lowest=True)
    return {
        "title": re.sub(BULLET, "", lines[0])[:100] if lines else "Job description",
        "required_skills": req,
        "preferred_skills": pref,
        "skill_weights": skill_weights,
        "core_skills": [s for s, w in skill_weights.items() if w >= 1.5],
        "min_years": years,
        "education_level": level,
        "education_label": LEVEL_LABEL.get(level),
        "requirements": bullets[:12],
    }


# ------------------------------------------------------------ blind screening
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
PROTECTED_LINE = re.compile(r"^\s*(gender|sex|dob|date of birth|age|marital status|nationality|religion|father'?s name)\b.*$", re.I | re.M)
GENDERED = re.compile(r"\b(he|she|him|her|hers|his|himself|herself|mr|mrs|ms|miss)\b\.?", re.I)


def anonymize(text: str, name: str | None) -> str:
    """Remove identity signals before scoring: name, contact details, gendered words, protected attributes."""
    t = PROTECTED_LINE.sub("", text)
    t = EMAIL_RE.sub("", t)
    t = PHONE_RE.sub("", t)
    if name:
        for part in sorted({name, *name.split()}, key=len, reverse=True):
            if len(part) > 1:
                t = re.sub(re.escape(part), "", t, flags=re.I)
    t = GENDERED.sub("they", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()
