"""Eight deliberately messy synthetic resumes + ground truth, used to test the parser (see backend/tests/test_messy.py).
spans: [[start_year, start_month, end_year_or_null, end_month]] - null end = 'Present'. Usage: python scripts/generate_messy_samples.py"""
import json
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parents[1] / "sample_resumes_messy"
ss = getSampleStyleSheet()


def pdf(path, lines):
    SimpleDocTemplate(str(path), pagesize=A4).build([Paragraph(l.replace("&", "&amp;") or "&nbsp;", ss["BodyText"]) for l in lines])


def docx(path, lines):
    d = Document()
    for l in lines:
        d.add_paragraph(l)
    d.save(path)


def two_col(path, left, right):
    cell = lambda ls: [Paragraph(l, ss["BodyText"]) for l in ls]
    t = Table([[cell(left), cell(right)]], colWidths=[170, 340])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    SimpleDocTemplate(str(path), pagesize=A4).build([t])


CASES = {
 "01_numeric_dates.pdf": (pdf, ["PRIYA SHARMA | priya.sharma@example.com | +91 98765 43210", "Backend Developer", "WORK EXPERIENCE",
   "Software Engineer - Acme Systems", "03/2021 - Present", "Built REST APIs in Java and Spring Boot with PostgreSQL.",
   "Junior Developer - Beta Labs", "06/2018 - 02/2021", "Maintained Java services and wrote SQL queries.",
   "SKILLS", "Java, Spring Boot, PostgreSQL, SQL, Docker, Git", "EDUCATION", "B.Tech in Computer Science, Delhi University, 2014 - 2018"],
   {"name": "Priya Sharma", "spans": [[2021, 3, None, None], [2018, 6, 2021, 2]], "skills": ["Java", "Spring Boot", "PostgreSQL", "Docker"], "edu": 2}),
 "02_apostrophe_iso.docx": (docx, ["Rahul Verma", "Data Engineer", "rahul.v@example.com | 9876543210", "EXPERIENCE",
   "Data Engineer, Gamma Corp (Jan'19 - Mar ’21)", "Senior Data Engineer, Delta Inc (2021-04 to current)", "SKILLS", "Python, SQL, Spark, Airflow, AWS"],
   {"name": "Rahul Verma", "spans": [[2019, 1, 2021, 3], [2021, 4, None, None]], "skills": ["Python", "SQL", "Spark", "AWS"], "edu": None}),
 "03_flat_no_headings.docx": (docx, ["Sneha Rao", "Full Stack Developer", "sneha.rao@example.com", "B.Tech Computer Science, XYZ University 2012 - 2016",
   "Developer at Foo Technologies, Jan 2017 - Dec 2019", "Senior Developer at Bar Solutions, Jan 2020 - Present", "Worked with React, Node.js, MongoDB and Docker."],
   {"name": "Sneha Rao", "spans": [[2017, 1, 2019, 12], [2020, 1, None, None]], "skills": ["React", "Node.js", "MongoDB", "Docker"], "edu": 2}),
 "04_stated_only.pdf": (pdf, ["Karthik Menon", "Python Developer", "karthik@example.com", "Senior Python developer with 8+ years of experience building APIs and data pipelines.",
   "Skills: Python, Django, PostgreSQL, Docker"],
   {"name": "Karthik Menon", "stated": 8.0, "skills": ["Python", "Django", "PostgreSQL", "Docker"], "edu": None}),
 "06_overlap_and_gap.docx": (docx, ["Arjun Kapoor", "Software Consultant", "arjun.k@example.com", "EXPERIENCE", "Freelance Developer - Self employed", "Jun 2020 - Jun 2023",
   "Backend Developer - Omega Ltd", "Jan 2019 - Dec 2021", "Consultant - Sigma Tech", "Mar 2024 - Present", "SKILLS", "Java, MySQL, Git"],
   {"name": "Arjun Kapoor", "spans": [[2020, 6, 2023, 6], [2019, 1, 2021, 12], [2024, 3, None, None]], "skills": ["Java", "MySQL", "Git"], "edu": None}),
 "07_month_names.pdf": (pdf, ["Neha Bansal", "QA Engineer", "neha.b@example.com", "EXPERIENCE", "QA Lead, Sigma Systems (September 2018 - Till date)",
   "QA Engineer, Tau Labs (Sept. 2015 - Aug 2018)", "SKILLS", "Selenium, Python, Agile, Jenkins"],
   {"name": "Neha Bansal", "spans": [[2018, 9, None, None], [2015, 9, 2018, 8]], "skills": ["Selenium", "Python", "Agile", "Jenkins"], "edu": None}),
 "08_name_not_first.docx": (docx, ["CURRICULUM VITAE", "", "Ananya Iyer", "Data Scientist", "ananya@example.com", "EXPERIENCE", "Data Scientist, Zeta AI", "Apr 2019 - Present",
   "SKILLS", "Python, Machine Learning, TensorFlow, Pandas, SQL"],
   {"name": "Ananya Iyer", "spans": [[2019, 4, None, None]], "skills": ["Python", "Machine Learning", "TensorFlow", "SQL"], "edu": None}),
}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for f in OUT.iterdir():
        f.unlink()
    expected = {}
    for name, (writer, lines, exp) in CASES.items():
        writer(OUT / name, lines); expected[name] = exp
    two_col(OUT / "05_two_column.pdf",
            ["<b>Divya Nair</b>", "divya.nair@example.com", "+91 90000 11111", "<b>SKILLS</b>", "Java, Spring Boot", "PostgreSQL, Docker", "Kubernetes, Git"],
            ["<b>SUMMARY</b>", "Backend engineer building payment services.", "<b>EXPERIENCE</b>", "Backend Engineer, Nova Pay", "Mar 2020 - Present", "Built microservices and REST APIs.",
             "Software Engineer, Orbit Soft", "Jul 2016 - Feb 2020", "Wrote Java services.", "<b>EDUCATION</b>", "B.Tech in Computer Science, 2012 - 2016"])
    expected["05_two_column.pdf"] = {"name": "Divya Nair", "spans": [[2020, 3, None, None], [2016, 7, 2020, 2]], "skills": ["Java", "Spring Boot", "PostgreSQL", "Docker"], "edu": 2}
    (OUT / "expected.json").write_text(json.dumps(expected, indent=1))
    print(f"Wrote {len(expected)} messy resumes to {OUT}")
