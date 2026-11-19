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
MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
YEAR4 = r"(?:19|20)\d{2}"
# Date tokens: "Mar 2021", "March, 2021", "Jan'19", "03/2021", "03-2021", "2021-03", "2021"
TOKEN = rf"(?:{MONTH}\.?,?\s*(?:{YEAR4}|'\s?\d{{2}})|(?:0?[1-9]|1[0-2])[/.\-]{YEAR4}|{YEAR4}[/.\-](?:0?[1-9]|1[0-2])(?!\d)|{YEAR4})"
PRESENT = r"(?:till date|to date|till now|till present|present|current|now|ongoing|today)"
SEP = r"\s*(?:-|–|—|\bto\b|\buntil\b|\btill\b|\bthrough\b)\s*"
RANGE = re.compile(rf"(?<![A-Za-z0-9/])(?P<s>{TOKEN}){SEP}(?:(?P<e>{TOKEN})|(?P<p>{PRESENT}))(?![A-Za-z0-9])", re.I)
SINCE = re.compile(rf"\bsince\s+(?P<s>{TOKEN})", re.I)
EDU_CTX = re.compile("|".join(pat for _, pat in EDU_PATTERNS) + r"|\b(university|college|institute|school|academy|polytechnic)\b", re.I)


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


def _gutter(words: list, width: float):
    """x-position of an empty vertical channel between two text columns, or None for single-column pages."""
    n = int(width) + 2
    cover = [0] * n
    for w in words:
        for x in range(int(w["x0"]), min(int(w["x1"]) + 1, n)):
            cover[x] += 1
    lo, hi, best, run = int(n * 0.25), int(n * 0.75), None, 0
    for x in range(lo, hi + 1):
        if x < hi and cover[x] == 0:
            run += 1
            continue
        if run >= 10 and (best is None or run > best[1] - best[0]):
            best = (x - run, x)
        run = 0
    if not best:
        return None
    mid = (best[0] + best[1]) / 2
    left = sum(1 for w in words if w["x1"] <= mid)
    right = sum(1 for w in words if w["x0"] >= mid)
    ok = left >= 0.15 * len(words) and right >= 0.15 * len(words) and left + right >= 0.95 * len(words)
    return mid if ok else None


def _page_text(page) -> str:
    """Two-column layouts are read column by column instead of line by line (which would interleave them)."""
    try:
        words = page.extract_words()
        mid = _gutter(words, page.width) if len(words) > 30 else None
        if mid:
            cols = (page.within_bbox((0, 0, mid, page.height)).extract_text(), page.within_bbox((mid, 0, page.width, page.height)).extract_text())
            return "\n".join(c for c in cols if c)
    except Exception:
        pass
    return page.extract_text() or ""


def _pdf_text(data: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(_page_text(p) for p in pdf.pages)
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
def _parse_token(tok: str, today: dt.date):
    t = tok.strip().lower()
    m = re.fullmatch(rf"({MONTH})\.?,?\s*(?:({YEAR4})|'\s?(\d{{2}}))", t)
    if m:
        yy = int(m.group(2)) if m.group(2) else 2000 + int(m.group(3))
        if yy > today.year + 1:
            yy -= 100
        return yy, MONTHS[m.group(1)[:3]]
    m = re.fullmatch(rf"(\d{{1,2}})[/.\-]({YEAR4})", t)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.fullmatch(rf"({YEAR4})[/.\-](\d{{1,2}})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    return int(t), None


def compute_years(exp_text: str) -> float:
    """Union of all date ranges found (any supported format), so overlaps are not double counted.
    Ranges on education lines are ignored, which matters for resumes without section headings."""
    today = dt.date.today()
    now = today.year * 12 + today.month
    spans, prev = [], ""
    for raw in exp_text.replace("’", "'").replace("‘", "'").splitlines():
        line = raw.strip()
        if not line:
            continue
        for m in [*RANGE.finditer(line), *SINCE.finditer(line)]:
            date_only = len(line) - len(m.group(0)) < 8        # the date sits on its own line
            if EDU_CTX.search(line + (" " + prev if date_only else "")):
                continue
            sy, sm = _parse_token(m.group("s"), today)
            s = sy * 12 + (sm or 1)
            if "e" not in m.groupdict() or not (m.group("e") or m.group("p")):
                e = now                                           # "since 2019"
            elif m.group("p"):
                e = now
            else:
                ey, em = _parse_token(m.group("e"), today)
                e = ey * 12 + (em or 1)
            e = min(e, now)
            if sy >= 1970 and e >= s:
                spans.append((s, e))
        prev = line
    spans.sort()
    total, cs, ce = 0, None, None
    for a, b in spans:
        if ce is None or a > ce:
            if ce is not None:
                total += ce - cs
            cs, ce = a, b
        else:
            ce = max(ce, b)
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


ROLE_WORDS = re.compile(r"engineer|developer|analyst|manager|designer|scientist|consultant|architect|intern|specialist|administrator|lead|senior|junior|executive|summary|experience|education|skills", re.I)


def guess_name(lines: list[str]) -> str | None:
    for l in lines[:8]:
        s = l.strip()
        # header lines like "PRIYA SHARMA | priya@x.com | +91 ..." -> look at the first segment only
        cand = re.split(r"\s*[|•·,]\s*", s)[0] if re.search(r"[|•·@\d]", s) else s
        cand = re.sub(r"\s+(summary|profile|objective|experience|education|skills|projects)\s*$", "", cand, flags=re.I)  # merged columns
        if not cand or "@" in cand or re.search(r"\d", cand) or re.search(r"resume|curriculum|vitae|\bcv\b|profile|contact", cand, re.I) or ROLE_WORDS.search(cand):
            continue
        w = cand.split()
        if 2 <= len(w) <= 4 and all(re.fullmatch(r"[A-Za-z.'\-]+", x) for x in w):
            return cand.title() if cand.isupper() else cand
    return None


# ------------------------------------------------------------------ resume
def parse_resume(text: str, filename: str = "") -> dict:
    lines = [l for l in text.splitlines() if l.strip()]
    sec = split_sections(text)
    name = guess_name(lines)
    title = None
    if name:
        i = next((k for k, l in enumerate(lines[:8]) if l.strip().lower().startswith(name.lower())), None)
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
