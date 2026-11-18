"""Skills taxonomy. Each line: Canonical | alias | alias ...
Aliases are matched case-insensitively on word boundaries (so 'java' never matches 'javascript').
Extend this list freely - it is the only place skills are defined."""
import re

RAW = """
Python|python3
Java|core java|java 8|java 11|java 17|j2ee|jdk
JavaScript|js|ecmascript|es6
TypeScript
C++|cpp
C#|csharp|c sharp
.NET|dotnet|asp.net
Golang|go lang
Kotlin
Scala
Rust
PHP
Ruby|ruby on rails
Swift
SQL|t-sql|pl/sql|plsql
PostgreSQL|postgres|psql
MySQL|mariadb
SQL Server|mssql|microsoft sql server
Oracle|oracle db
MongoDB|mongo
Redis
Elasticsearch|elastic search|opensearch
DynamoDB
Cassandra
Snowflake
Spring|spring framework|spring mvc|spring core
Spring Boot|springboot|spring-boot
Hibernate|jpa
Django
Flask
FastAPI
Node.js|nodejs|node js
Express|express.js|expressjs
React|reactjs|react.js
Angular|angularjs
Vue.js|vue|vuejs
Next.js|nextjs
HTML|html5
CSS|css3|sass|scss
Tailwind CSS|tailwind
REST APIs|restful|rest api|rest apis|restful api|restful apis|rest services|restful services
GraphQL
gRPC
Microservices|microservice|micro-services|microservice architecture
Docker|containerization|containerisation|dockerfile
Kubernetes|k8s|eks|aks|gke
AWS|amazon web services|ec2|s3
Azure|microsoft azure
GCP|google cloud|google cloud platform
Terraform
Ansible
Jenkins
GitHub Actions
GitLab CI
CI/CD|cicd|ci cd|continuous integration|continuous delivery|continuous deployment
Git|github|gitlab|bitbucket
Linux|unix|bash|shell scripting
Kafka|apache kafka
RabbitMQ
Maven
Gradle
JUnit|mockito|testng
Pytest
Selenium
Agile|scrum|kanban
Machine Learning|ml
Deep Learning
NLP|natural language processing
PyTorch
TensorFlow
scikit-learn|sklearn
Pandas
NumPy
Spark|pyspark|apache spark
Airflow|apache airflow
Tableau
Power BI|powerbi
Excel|ms excel|microsoft excel
Data Structures|algorithms|dsa
Distributed Systems|system design
Prometheus
Grafana
"""

# Canonical names that are ordinary English words: only their aliases are matched
NO_SELF = {"Spring", "Express", "Excel", "Spark"}

# Having the key implies the listed skills (a Spring Boot developer knows Java)
IMPLIES = {
    "Spring Boot": ["Spring", "Java"], "Spring": ["Java"], "Hibernate": ["Java"],
    "JUnit": ["Java"], "Maven": ["Java"], "Gradle": ["Java"],
    "Django": ["Python"], "Flask": ["Python"], "FastAPI": ["Python"],
    "Pandas": ["Python"], "NumPy": ["Python"], "Pytest": ["Python"],
    "React": ["JavaScript"], "Next.js": ["React", "JavaScript"], "Node.js": ["JavaScript"],
    "Express": ["JavaScript"], "Vue.js": ["JavaScript"], "TypeScript": ["JavaScript"],
    "PostgreSQL": ["SQL"], "MySQL": ["SQL"], "SQL Server": ["SQL"], "Oracle": ["SQL"],
}

# Transferable-skill groups: a different member earns partial credit
GROUPS = [
    ["PostgreSQL", "MySQL", "SQL Server", "Oracle"],
    ["React", "Angular", "Vue.js", "Next.js"],
    ["AWS", "Azure", "GCP"],
    ["Kafka", "RabbitMQ"],
    ["Java", "Kotlin", "C#", ".NET"],
    ["Spring", "Spring Boot"],
    ["Jenkins", "GitHub Actions", "GitLab CI", "CI/CD"],
    ["PyTorch", "TensorFlow"],
    ["Django", "Flask", "FastAPI"],
    ["Docker", "Kubernetes"],
    ["MongoDB", "DynamoDB", "Cassandra"],
    ["Terraform", "Ansible"],
    ["Redis", "Elasticsearch"],
    ["Python", "Golang"],
]


def _compile():
    out = []
    for line in RAW.strip().splitlines():
        parts = [p.strip() for p in line.split("|") if p.strip()]
        name, aliases = parts[0], parts[1:]
        if name not in NO_SELF:
            aliases = [name] + aliases
        alt = "|".join(sorted({re.escape(a.lower()) for a in aliases}, key=len, reverse=True))
        out.append((name, re.compile(rf"(?<![\w+#.])(?:{alt})(?![\w+#])")))
    return out


_PATTERNS = _compile()


def extract_skills(text: str, add_implied: bool = False) -> list[str]:
    low = text.lower()
    hits = [(m.start(), n) for n, p in _PATTERNS if (m := p.search(low))]
    found = [n for _, n in sorted(hits)]
    if add_implied:
        for n in list(found):
            for imp in IMPLIES.get(n, []):
                if imp not in found:
                    found.append(imp)
    return found


def related(a: str, b: str) -> bool:
    return a != b and any(a in g and b in g for g in GROUPS)
