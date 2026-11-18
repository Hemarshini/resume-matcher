"""Generates 12 synthetic resumes (PDF + DOCX) and nothing else - no real personal data.
Usage: python scripts/generate_samples.py"""
import datetime as dt
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parents[1] / "sample_resumes"
TODAY = dt.date.today()
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

BULLETS = {
    "java": ["Designed and built RESTful microservices serving 2M+ daily requests.",
             "Optimised slow database queries and reduced API latency by 40%.",
             "Wrote unit and integration tests and led code reviews for a team of six.",
             "Automated build and release pipelines to ship to production weekly."],
    "python": ["Built asynchronous REST APIs and background workers for a data-heavy product.",
               "Modelled relational data, tuned queries and added caching to cut response times.",
               "Deployed services as containers and monitored them in production.",
               "Mentored junior engineers and introduced automated testing."],
    "fullstack": ["Developed responsive single-page applications and the APIs behind them.",
                  "Integrated third-party payment and notification services.",
                  "Improved page load time by 35% through code splitting and caching.",
                  "Collaborated with designers and product managers in two-week sprints."],
    "data": ["Built dashboards and weekly reports for the sales and finance teams.",
             "Wrote complex queries to analyse customer behaviour and churn.",
             "Cleaned and transformed large datasets for forecasting.",
             "Presented insights to stakeholders and recommended pricing changes."],
    "devops": ["Managed cloud infrastructure as code and reduced provisioning time by 60%.",
               "Operated container clusters and defined autoscaling and rollout strategies.",
               "Built continuous delivery pipelines plus monitoring and alerting dashboards.",
               "Cut incident response time through runbooks and on-call improvements."],
    "stuffer": ["Entered and verified customer records in the company spreadsheet.",
                "Assisted the support team with daily tickets and reports.",
                "Attended internal training sessions on office tools.",
                "Helped colleagues prepare weekly status updates."],
    "paraphrase": ["Led design of HTTP and JSON services handling payment traffic across a service-oriented architecture.",
                   "Tuned Postgres queries and indexing to cut p95 latency by 45%.",
                   "Mentored six engineers and owned reliability of the transaction platform.",
                   "Packaged services as containers and rolled them out through automated pipelines."],
    "frontend": ["Built reusable component libraries and accessible user interfaces.",
                 "Implemented state management and client-side routing for large web apps.",
                 "Optimised rendering performance and cross-browser compatibility.",
                 "Worked with designers to translate mockups into pixel-perfect pages."],
}

# name, title, years, family, skills, education, (company1, company2), summary
PROFILES = [
    ("Aarav Mehta", "Senior Java Developer", 7, "java", "Java, Spring Boot, Microservices, PostgreSQL, SQL, Docker, Kubernetes, AWS, Kafka, Jenkins, Git, Distributed Systems", "B.Tech in Computer Science, Nirma Institute of Technology", ("Finpay Systems", "Orbit Soft"), "Backend engineer with 7 years of experience building payment services in Java and Spring Boot."),
    ("Priya Nair", "Backend Engineer", 5, "java", "Java, Spring Boot, Postgres, Docker, Git, Redis, JUnit", "M.Tech in Software Engineering, Kerala Institute of Technology", ("CartNest", "Brightwave Labs"), "Backend engineer who ships reliable Java services and cares about clean APIs."),
    ("Rohan Verma", "Java Developer", 4, "java", "Java, Spring Boot, MySQL, Git, Maven", "B.E. in Information Technology, Pune College of Engineering", ("Medisys", "Kiwi Apps"), "Java developer building internal healthcare tools."),
    ("Sneha Kulkarni", "Software Engineer", 3, "java", "Java, SQL, JUnit, Git", "B.Sc in Computer Science, Mumbai Science College", ("DataPulse", "Zenith Infotech"), "Software engineer focused on core Java and relational databases."),
    ("Karan Singh", "Full Stack Developer", 6, "fullstack", "Node.js, React, TypeScript, MongoDB, Docker, AWS, Git", "B.Tech in Computer Science, Delhi Technical University", ("ShopLoop", "PixelForge"), "Full stack developer shipping React and Node.js products."),
    ("Ananya Iyer", "Python Backend Engineer", 5, "python", "Python, Django, FastAPI, PostgreSQL, Docker, Kubernetes, AWS, Kafka, Git", "B.Tech in Computer Science, Chennai Institute of Technology", ("LedgerLoop", "StreamKart"), "Python backend engineer experienced with microservices and event streaming."),
    ("Vikram Rao", "Lead Backend Engineer", 8, "java", "Kotlin, Java, Spring Boot, Microservices, MySQL, RabbitMQ, Docker, GCP, Distributed Systems, Git", "M.S. in Computer Science, Texas State University", ("Cloudbridge", "Nimbus Pay"), "Lead engineer designing JVM-based distributed services."),
    ("Meera Joshi", "Data Analyst", 3, "data", "SQL, Python, Tableau, Excel, Pandas", "B.Sc in Statistics, Pune University", ("RetailIQ", "Insightly"), "Data analyst turning sales data into decisions."),
    ("Arjun Das", "Junior Java Developer", 1, "java", "Java, Spring Boot, MySQL, Git", "B.Tech in Computer Science, Kolkata Engineering College", ("Greenleaf Tech",), "Early-career Java developer eager to grow in backend engineering."),
    ("Neha Gupta", "DevOps Engineer", 6, "devops", "Docker, Kubernetes, AWS, Terraform, Jenkins, Python, Linux, Git, CI/CD", "B.Tech in Electronics, Jaipur Institute of Technology", ("CloudNine", "OpsWorks India"), "DevOps engineer automating infrastructure and delivery."),
    ("Imran Sheikh", "Java Solutions Architect", 10, "java", "Java, Spring Boot, Microservices, PostgreSQL, Oracle, Docker, Kubernetes, Kafka, Redis, AWS, CI/CD, Distributed Systems, Git", "B.E. in Computer Engineering, Hyderabad Institute of Technology", ("Banksy Tech", "Pay2Go", "Trident Systems"), "Architect with 10 years of experience designing high-throughput Java platforms for banking."),
    ("Kavya Reddy", "Software Trainee", 1, "stuffer", "Java, Spring Boot, REST APIs, Microservices, Distributed Systems, SQL, PostgreSQL, Docker, Git, Kubernetes, AWS, Kafka, CI/CD, Redis", "B.Sc in Mathematics, Hyderabad Science College", ("Prime Data Services",), "Motivated fresher with strong knowledge of every modern backend technology."),
    ("Rahul Bhatt", "Principal Software Engineer", 8, "paraphrase", "Kotlin, Java, Spring, Postgres, Docker, Git, Kubernetes", "B.Tech in Computer Science, Ahmedabad Institute of Technology", ("Remit Labs", "Coreline Systems"), "Principal engineer building high-volume payment services on the JVM."),
    ("Divya Menon", "Frontend Developer", 4, "frontend", "React, JavaScript, HTML, CSS, Tailwind CSS, Git", "B.Sc in Computer Applications, Bengaluru Arts and Science College", ("PixelCraft", "Bloom Studio"), "Frontend developer who loves crafting accessible interfaces."),
]


def months_back(y, m, n):
    t = y * 12 + (m - 1) - n
    return t // 12, t % 12 + 1


def fmt(ym):
    return f"{MON[ym[1] - 1]} {ym[0]}"


def build(idx, p):
    name, title, years, fam, skills, edu, cos, summary = p
    first, last = name.lower().split()
    lines = [("name", name), ("title", title),
             ("contact", f"{first}.{last}@example.com | +91 98765 {10000 + idx * 137} | India"),
             ("h", "SUMMARY"), ("body", summary), ("h", "SKILLS"), ("body", skills), ("h", "EXPERIENCE")]
    d1 = years if len(cos) == 1 else max(1, round(years * 0.6))
    jobs, end = [], None
    start = months_back(TODAY.year, TODAY.month, d1 * 12)
    jobs.append((title, cos[0], f"{fmt(start)} – Present", BULLETS[fam][:4]))
    if len(cos) > 1:
        rest, cur_end = years - d1, start
        per = rest / (len(cos) - 1)
        for k, co in enumerate(cos[1:]):
            s = months_back(*cur_end, round(per * 12))
            jobs.append(("Software Engineer" if fam != "data" else "Analyst", co, f"{fmt(s)} – {fmt(cur_end)}", BULLETS[fam][1:4]))
            cur_end = s
    for n, (t, co, dates, bl) in enumerate(jobs):
        lines += [("job", f"{t}, {co}"), ("date", dates)] + [("bullet", b) for b in bl]
        if fam != "stuffer":  # genuine candidates evidence their stack inside the job
            lines.append(("body", "Tech stack: " + ", ".join(skills.split(", ")[: 99 if n == 0 else 5])))
    lines += [("h", "EDUCATION"), ("body", edu), ("body", f"Graduated {TODAY.year - years - 1}")]
    return lines


def write_docx(lines, path):
    d = Document()
    for kind, text in lines:
        if kind == "name":
            d.add_heading(text, 0)
        elif kind == "h":
            d.add_heading(text, 2)
        elif kind == "bullet":
            d.add_paragraph(text, style="List Bullet")
        elif kind == "job":
            d.add_paragraph().add_run(text).bold = True
        else:
            d.add_paragraph(text)
    d.save(path)


def write_pdf(lines, path):
    ss = getSampleStyleSheet()
    st = {"name": ParagraphStyle("n", parent=ss["Title"], alignment=0, fontSize=22),
          "h": ParagraphStyle("h", parent=ss["Heading3"], spaceBefore=10, textColor="#1f3a5f"),
          "job": ParagraphStyle("j", parent=ss["BodyText"], fontName="Helvetica-Bold"),
          "bullet": ParagraphStyle("b", parent=ss["BodyText"], leftIndent=14, bulletIndent=2)}
    story = []
    for kind, text in lines:
        if kind == "bullet":
            story.append(Paragraph(text, st["bullet"], bulletText="•"))
        else:
            story.append(Paragraph(text, st.get(kind, ss["BodyText"])))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=40, bottomMargin=40).build(story)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    for i, p in enumerate(PROFILES):
        lines, base = build(i, p), f"{i + 1:02d}_{p[0].replace(' ', '_')}"
        (write_pdf if i % 2 == 0 else write_docx)(lines, OUT / (base + (".pdf" if i % 2 == 0 else ".docx")))
    print(f"Wrote {len(PROFILES)} resumes to {OUT}")
