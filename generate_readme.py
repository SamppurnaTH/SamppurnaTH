#!/usr/bin/env python3
"""
Profile README generator for github.com/SamppurnaTH.

Everything on the profile is computed from the GitHub GraphQL API at build time:
contributions (all-time, streaks, weekly activity), repositories, languages,
tech stack (parsed from each repo's dependency files), featured projects and
recent commits. Stats cards are rendered as local SVGs in assets/, so the
profile does not depend on third-party card services that rate-limit or go down.

Only PUBLIC, non-fork repositories are ever listed or named.

Run locally:   GITHUB_TOKEN=$(gh auth token) python generate_readme.py
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

# ════════════════════════════════════════════════════════════════════════════
# CONFIG — the only hand-written part. Everything else comes from the API.
# ════════════════════════════════════════════════════════════════════════════
USERNAME = os.environ.get("PROFILE_USER", "SamppurnaTH")
HEADLINE = "Full-Stack Developer  •  AI / ML Engineer  •  Builder"
TAGLINE = "I build AI products end-to-end, from model to production."
FEATURED_COUNT = 6           # project cards shown in the grid
EXCLUDE_REPOS = {USERNAME}   # never list these (the profile repo itself)
ALWAYS_SKILLS = ["git", "github", "vscode", "linux"]  # tools no dependency file reveals
ACCENT = "#a78bfa"
ACCENT_DEEP = "#7c3aed"

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
API = "https://api.github.com/graphql"
NOW = datetime.now(timezone.utc)

# ════════════════════════════════════════════════════════════════════════════
# GitHub API
# ════════════════════════════════════════════════════════════════════════════

def rest(path: str) -> dict:
    req = urllib.request.Request(f"https://api.github.com{path}", headers={
        "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
        "Accept": "application/vnd.github+json", "User-Agent": "profile-readme-generator"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def graphql(query: str, variables: dict | None = None) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is required")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "profile-readme-generator",
    })
    for attempt in range(5):           # GitHub returns 502/503 on busy or heavy queries
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 4:
                raise
            print(f"GitHub API {e.code}, retrying ({attempt + 1}/4)…")
            time.sleep(5 * (attempt + 1))
    if payload.get("errors"):
        sys.exit(f"GraphQL error: {payload['errors']}")
    return payload["data"]


DEP_FILES = {
    "req": "requirements.txt", "pyp": "pyproject.toml", "pkg": "package.json",
    "pom": "pom.xml", "gradle": "build.gradle",
}
DEP_DIRS = {"": "", "fe": "frontend/", "be": "backend/"}


def _blob_fields() -> str:
    out = []
    for dk, d in DEP_DIRS.items():
        for fk, f in DEP_FILES.items():
            out.append(f'{fk}{dk}: object(expression: "HEAD:{d}{f}") {{ ... on Blob {{ text }} }}')
    return "\n".join(out)


USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    id name login bio location websiteUrl isHireable createdAt avatarUrl
    followers { totalCount } following { totalCount }
    socialAccounts(first: 10) { nodes { provider url displayName } }
    pinnedItems(first: 6, types: REPOSITORY) { nodes { ... on Repository { name } } }
    pullRequests { totalCount }
    contributionsCollection {
      contributionYears
      totalCommitContributions totalPullRequestContributions
      totalPullRequestReviewContributions totalIssueContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

REPO_QUERY = """
query($login: String!, $cursor: String, $uid: ID!) {
  user(login: $login) {
    repositories(first: 15, after: $cursor, privacy: PUBLIC, isFork: false,
                 ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name description url homepageUrl stargazerCount forkCount isArchived
        pushedAt createdAt diskUsage
        repositoryTopics(first: 10) { nodes { topic { name } } }
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          totalSize edges { size node { name color } }
        }
        defaultBranchRef { target { ... on Commit {
          all: history(first: 1) { totalCount }
          mine: history(first: 5, author: {id: $uid}) { nodes { committedDate messageHeadline url } }
          latest: history(first: 1) { nodes { committedDate } }
        } } }
        readme: object(expression: "HEAD:README.md") { ... on Blob { text } }
        root: object(expression: "HEAD:") { ... on Tree { entries { name } } }
        workflows: object(expression: "HEAD:.github/workflows") { ... on Tree { entries { name } } }
        %BLOBS%
      }
    }
  }
}""".replace("%BLOBS%", _blob_fields())

YEAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) { contributionsCollection(from: $from, to: $to) {
    contributionCalendar { weeks { contributionDays { date contributionCount } } }
  } }
}"""


def fetch_all() -> tuple[dict, list[dict], dict[date, int]]:
    user = graphql(USER_QUERY, {"login": USERNAME})["user"]
    user["email"] = rest(f"/users/{USERNAME}").get("email")  # public email only

    repos, cursor = [], None
    while True:
        page = graphql(REPO_QUERY, {"login": USERNAME, "cursor": cursor, "uid": user["id"]})["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    user["public_repo_count"] = len(repos)
    repos = [r for r in repos if r["name"] not in EXCLUDE_REPOS and not r["isArchived"]]

    # Daily contributions for every year the account has been active.
    days: dict[date, int] = {}
    for year in user["contributionsCollection"]["contributionYears"]:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = min(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), NOW)
        cal = graphql(YEAR_QUERY, {"login": USERNAME, "from": start.isoformat(),
                                   "to": end.isoformat()})
        for w in cal["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]
    return user, repos, days

# ════════════════════════════════════════════════════════════════════════════
# Analysis
# ════════════════════════════════════════════════════════════════════════════

def streaks(days: dict[date, int]) -> tuple[int, int]:
    today = NOW.date()
    longest = run = 0
    for d in sorted(days):
        if d > today:
            break
        run = run + 1 if days[d] > 0 else 0
        longest = max(longest, run)
    current, d = 0, today
    if days.get(d, 0) == 0:          # today not counted yet → streak still alive
        d -= timedelta(days=1)
    while days.get(d, 0) > 0:
        current += 1
        d -= timedelta(days=1)
    return current, longest


def language_shares(repos: list[dict]) -> list[tuple[str, float, str]]:
    """Each repo contributes equally; languages under 3% of a repo are noise
    (vendored files, committed virtualenvs) and are dropped."""
    score, colors = Counter(), {}
    for r in repos:
        total = r["languages"]["totalSize"] or 0
        if not total:
            continue
        for e in r["languages"]["edges"]:
            share = e["size"] / total
            if share >= 0.03:
                score[e["node"]["name"]] += share
                colors[e["node"]["name"]] = e["node"]["color"] or "#8b949e"
    s = sum(score.values()) or 1
    return [(n, v / s, colors[n]) for n, v in score.most_common()]


# (regex on dependency name, display name, skillicons id or None, simple-icons slug, category)
TECH = [
    (r"^react$", "React", "react", "react", "Frontend"),
    (r"^next$", "Next.js", "nextjs", "nextdotjs", "Frontend"),
    (r"^vite$|^@vitejs/", "Vite", "vite", "vite", "Frontend"),
    (r"tailwindcss", "Tailwind CSS", "tailwind", "tailwindcss", "Frontend"),
    (r"^framer-motion$", "Framer Motion", None, "framer", "Frontend"),
    (r"^@radix-ui/", "Radix UI", None, "radixui", "Frontend"),
    (r"^redux$|^@reduxjs/", "Redux", "redux", "redux", "Frontend"),
    (r"^zustand$", "Zustand", None, None, "Frontend"),
    (r"^@tanstack/react-query$", "TanStack Query", None, "reactquery", "Frontend"),
    (r"^typescript$", "TypeScript", "ts", "typescript", "Languages"),
    (r"^express$", "Express", "express", "express", "Backend"),
    (r"^fastapi$", "FastAPI", "fastapi", "fastapi", "Backend"),
    (r"^flask$", "Flask", "flask", "flask", "Backend"),
    (r"^django$", "Django", "django", "django", "Backend"),
    (r"^spring-boot", "Spring Boot", "spring", "springboot", "Backend"),
    (r"^spring-cloud", "Spring Cloud", None, "spring", "Backend"),
    (r"^sqlalchemy$", "SQLAlchemy", None, "sqlalchemy", "Backend"),
    (r"^pydantic$", "Pydantic", None, "pydantic", "Backend"),
    (r"^springdoc|swagger", "OpenAPI", None, "swagger", "Backend"),
    (r"mongo", "MongoDB", "mongodb", "mongodb", "Data & Infra"),
    (r"postgres|asyncpg|psycopg", "PostgreSQL", "postgres", "postgresql", "Data & Infra"),
    (r"redis|bullmq", "Redis", "redis", "redis", "Data & Infra"),
    (r"kafka", "Kafka", "kafka", "apachekafka", "Data & Infra"),
    (r"^@prisma/|^prisma$", "Prisma", "prisma", "prisma", "Data & Infra"),
    (r"^@aws-sdk/|^boto3$", "AWS", "aws", "amazonwebservices", "Data & Infra"),
    (r"^torch$", "PyTorch", "pytorch", "pytorch", "AI / ML"),
    (r"^tensorflow|^keras$", "TensorFlow", "tensorflow", "tensorflow", "AI / ML"),
    (r"^scikit-learn$", "scikit-learn", "sklearn", "scikitlearn", "AI / ML"),
    (r"^transformers$|^datasets$", "Hugging Face", None, "huggingface", "AI / ML"),
    (r"^xgboost$", "XGBoost", None, None, "AI / ML"),
    (r"^opencv", "OpenCV", "opencv", "opencv", "AI / ML"),
    (r"^openai$|^@google/genai$|^@google/generative-ai$|^anthropic$", "LLM APIs", None, "openai", "AI / ML"),
    (r"^pandas$", "pandas", None, "pandas", "AI / ML"),
    (r"^numpy$", "NumPy", None, "numpy", "AI / ML"),
    (r"^matplotlib$|^seaborn$|^plotly$", "Matplotlib / Plotly", None, "plotly", "AI / ML"),
    (r"^streamlit$", "Streamlit", None, "streamlit", "AI / ML"),
    (r"^pytest$", "pytest", None, "pytest", "Testing"),
    (r"^jest$", "Jest", "jest", "jest", "Testing"),
    (r"^@testing-library/", "Testing Library", None, "testinglibrary", "Testing"),
    (r"^junit|^jqwik$", "JUnit", None, "junit5", "Testing"),
    (r"^testcontainers", "Testcontainers", None, None, "Testing"),
    (r"^playwright$|^@playwright/", "Playwright", None, None, "Testing"),
]
LANG_ICONS = {
    "Python": "py", "Java": "java", "TypeScript": "ts", "JavaScript": "js", "C#": "cs",
    "HTML": "html", "CSS": "css", "Shell": "bash", "PowerShell": "powershell",
    "Go": "go", "Rust": "rust", "C++": "cpp", "Kotlin": "kotlin", "Dart": "dart",
}
ML_NAMES = {"PyTorch", "TensorFlow", "scikit-learn", "Hugging Face", "XGBoost", "OpenCV", "LLM APIs"}
CATEGORY_ORDER = ["Languages", "Frontend", "Backend", "AI / ML", "Data & Infra", "Testing", "DevOps & Tools"]


def parse_deps(repo: dict) -> set[str]:
    names: set[str] = set()
    for dk in DEP_DIRS:
        for fk in DEP_FILES:
            blob = repo.get(f"{fk}{dk}")
            text = (blob or {}).get("text") or ""
            if not text:
                continue
            if fk == "req":
                for line in text.splitlines():
                    line = line.strip().lstrip("﻿")
                    if line and not line.startswith(("#", "-")):
                        names.add(re.split(r"[\s\[<>=!~;@]", line, 1)[0].lower())
            elif fk == "pyp":
                names |= {m.lower() for m in re.findall(r'^\s*"([A-Za-z0-9_.\-]+)', text, re.M)}
                names |= {m.lower() for m in re.findall(r'^([A-Za-z0-9_.\-]+)\s*=', text, re.M)}
            elif fk == "pkg":
                try:
                    j = json.loads(text)
                    names |= set(j.get("dependencies", {})) | set(j.get("devDependencies", {}))
                except ValueError:
                    pass
            elif fk in ("pom", "gradle"):
                names |= set(re.findall(r"<artifactId>([^<]+)</artifactId>", text))
                names |= set(re.findall(r"['\"][\w.\-]+:([\w.\-]+)", text))
    return names


def detect_tech(repo: dict) -> dict[str, tuple]:
    found: dict[str, tuple] = {}
    for dep in parse_deps(repo):
        for pat, name, icon, slug, cat in TECH:
            if re.search(pat, dep):
                found[name] = (icon, slug, cat)
    files = {e["name"] for e in ((repo.get("root") or {}).get("entries") or [])}
    if files & {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"} or any(
            f.startswith("docker-compose") for f in files):
        found["Docker"] = ("docker", "docker", "DevOps & Tools")
    if (repo.get("workflows") or {}).get("entries"):
        found["GitHub Actions"] = ("githubactions", "githubactions", "DevOps & Tools")
    home = repo.get("homepageUrl") or ""
    if "vercel.app" in home or "vercel.json" in files:
        found["Vercel"] = ("vercel", "vercel", "DevOps & Tools")
    if "onrender.com" in home or "render.yaml" in files:
        found["Render"] = (None, "render", "DevOps & Tools")
    if any(f.endswith(".ipynb") for f in files):
        found["Jupyter"] = (None, "jupyter", "AI / ML")
    for e in repo["languages"]["edges"]:
        if e["size"] / (repo["languages"]["totalSize"] or 1) >= 0.03 and e["node"]["name"] in LANG_ICONS:
            found[e["node"]["name"]] = (LANG_ICONS[e["node"]["name"]], None, "Languages")
    return found


def clean_readme_summary(text: str) -> str:
    """Summary from a README when the repo has no description: the first real
    sentence of the intro (text before the second heading), else the H1 title."""
    text = re.sub(r"<!--.*?-->|```.*?```", " ", text, flags=re.S)
    title, headings = "", 0
    for raw in text.splitlines():
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw)               # images / badges
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)            # links → text
        line = re.sub(r"<[^>]+>", "", line)                             # html tags
        line = re.sub(r"[*_`]+", "", line).strip()
        if line.startswith("#") or re.fullmatch(r"=+|-{3,}", line):
            headings += 1
            if not title and line.startswith("# "):
                title = re.sub(r"^[^\w]+", "", line[2:]).strip()
            if headings >= 2 and title:
                break
            continue
        if (len(line) < 30 or line.endswith(":") or line.startswith(("|", ">", "-", "[", "!", "$"))
                or re.match(r"^[A-Z][\w /&-]{0,25}:\s", line) or "://" in line):
            continue
        return html.unescape(re.split(r"(?<=[.!?])\s", line, 1)[0])
    return html.unescape(title)


def enrich(repos: list[dict]) -> None:
    for r in repos:
        r["tech"] = detect_tech(r)
        desc = (r["description"] or "").strip().strip("”“\"")
        r["summary"] = desc or clean_readme_summary((r.get("readme") or {}).get("text") or "") \
            or r["name"].replace("-", " ").replace("_", " ").title()
        target = (r.get("defaultBranchRef") or {}).get("target") or {}
        r["commits"] = (target.get("all") or {}).get("totalCount", 0)
        # Commits authored by me (bot / CI commits excluded) drive recency.
        r["recent"] = [c for c in (target.get("mine") or {}).get("nodes", [])
                       if "[skip ci]" not in c["messageHeadline"]]
        # Repos updated only by CI bots fall back to their latest commit date.
        latest = ((target.get("latest") or {}).get("nodes") or [{}])[0].get("committedDate")
        r["active"] = r["recent"][0]["committedDate"] if r["recent"] else (latest or r["pushedAt"])
        langs = r["languages"]["edges"]
        r["lang"] = (langs[0]["node"]["name"], langs[0]["node"]["color"]) if langs else ("—", "#8b949e")
        names = set(r["tech"])
        has_front = any(r["tech"][n][2] == "Frontend" for n in names)
        has_back = any(r["tech"][n][2] == "Backend" for n in names) or "Java" in names
        has_front = has_front or any(
            e["node"]["name"] in ("TypeScript", "JavaScript", "HTML", "Vue", "Svelte")
            and e["size"] / (r["languages"]["totalSize"] or 1) >= 0.1 for e in langs)
        nb_share = sum(e["size"] for e in langs if e["node"]["name"] == "Jupyter Notebook") / (
            r["languages"]["totalSize"] or 1)
        tags = []
        if names & ML_NAMES or nb_share > 0.2:
            tags.append("AI / ML")
        if has_front and has_back:
            tags.append("Full-stack")
        elif has_back:
            tags.append("Backend")
        elif has_front:
            tags.append("Frontend")
        if r.get("homepageUrl"):
            tags.append("Live")
        r["tags"] = tags
        age_days = (NOW - datetime.fromisoformat(r["active"].replace("Z", "+00:00"))).days
        r["age_days"] = age_days
        # Ranking: stars, recency, depth of work, shipped demo, CI, multi-stack.
        r["score"] = (r["stargazerCount"] * 6 + r["forkCount"] * 4
                      + max(0, 30 - age_days / 12)
                      + min(25, math.log1p(r["commits"]) * 5)
                      + (12 if r.get("homepageUrl") else 0)
                      + (6 if "GitHub Actions" in names else 0)
                      + (8 if "Full-stack" in tags else 0)
                      + min(10, len(names)))


def aggregate_tech(repos: list[dict]) -> dict[str, list[tuple[str, str | None, str | None, int]]]:
    count, meta = Counter(), {}
    for r in repos:
        for name, m in r["tech"].items():
            count[name] += 1
            meta[name] = m
    by_cat = defaultdict(list)
    for name, n in count.most_common():
        icon, slug, cat = meta[name]
        by_cat[cat].append((name, icon, slug, n))
    for s in ALWAYS_SKILLS:
        by_cat["DevOps & Tools"].append((s, s, None, 0))
    return {c: by_cat[c] for c in CATEGORY_ORDER if by_cat.get(c)}


def ago(iso: str) -> str:
    d = NOW - datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if d.days >= 365:
        return f"{d.days // 365}y ago"
    if d.days >= 30:
        return f"{d.days // 30}mo ago"
    if d.days >= 1:
        return f"{d.days}d ago"
    return f"{max(1, d.seconds // 3600)}h ago"

# ════════════════════════════════════════════════════════════════════════════
# SVG rendering (dark + light variants, CSS animations work inside <img> SVGs)
# ════════════════════════════════════════════════════════════════════════════
THEMES = {
    "dark": dict(bg="#0d1117", bg2="#151229", border="#2d2a4a", text="#f0f6fc", muted="#9198a1",
                 accent="#a78bfa", accent2="#22d3ee", grid="#1f2433", pill="#231d3d",
                 glow=".55", shade="#000000"),
    "light": dict(bg="#ffffff", bg2="#f6f3ff", border="#ddd6fe", text="#1f2328", muted="#59636e",
                  accent="#7c3aed", accent2="#0891b2", grid="#eef0f4", pill="#f1ebff",
                  glow=".25", shade="#7c3aed"),
}
TAG_COLORS = {"AI / ML": "#f472b6", "Full-stack": "#a78bfa", "Backend": "#38bdf8",
              "Frontend": "#34d399", "Live": "#22c55e"}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',monospace"
esc = html.escape
md_esc = lambda s: html.escape(s, quote=False)

# 16×16 icon paths (Octicons, MIT)
ICON = {
    "commit": "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z",
    "pr": "M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354Z",
    "repo": "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8Z",
    "pulse": "M6 2c.306 0 .582.187.696.471L10 10.731l1.304-3.26A.751.751 0 0 1 12 7h3.25a.75.75 0 0 1 0 1.5h-2.742l-1.812 4.528a.751.751 0 0 1-1.392 0L6 4.77 4.696 8.03A.75.75 0 0 1 4 8.5H.75a.75.75 0 0 1 0-1.5h2.742l1.812-4.529A.751.751 0 0 1 6 2Z",
    "calendar": "M4.75 0a.75.75 0 0 1 .75.75V2h5V.75a.75.75 0 0 1 1.5 0V2h1.25c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0 1 13.25 16H2.75A1.75 1.75 0 0 1 1 14.25V3.75C1 2.784 1.784 2 2.75 2H4V.75A.75.75 0 0 1 4.75 0ZM2.5 7.5v6.75c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25V7.5Zm10.75-4H2.75a.25.25 0 0 0-.25.25V6h11V3.75a.25.25 0 0 0-.25-.25Z",
    "flame": "M9.533.753V.752c.217 2.385 1.463 3.626 2.653 4.81C13.37 6.74 14.498 7.863 14.498 10c0 3.5-3 6-6.5 6S1.5 13.512 1.5 10c0-1.298.536-2.56 1.425-3.286.376-.308.862 0 1.035.454C4.46 8.487 5.581 8.419 6 8c.44-.439.555-1.124.13-2.094-.807-1.843-.82-3.77.39-5.082.398-.432 1.042-.152 1.093.432Z",
    "clock": "M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm7-3.25v2.992l2.028.812a.75.75 0 0 1-.557 1.392l-2.5-1A.751.751 0 0 1 7 8.25v-3.5a.75.75 0 0 1 1.5 0Z",
    "pin": "m11.536 3.464 2.829 2.829a.75.75 0 0 1-.106 1.155l-2.05 1.38.976 3.416a.75.75 0 0 1-1.248.739L8.5 9.555 4.53 13.53a.749.749 0 1 1-1.06-1.06L7.445 8.5 4.017 5.063a.75.75 0 0 1 .739-1.248l3.416.976 1.38-2.05a.75.75 0 0 1 1.155-.106Z",
}


def icon(name: str, x: float, y: float, color: str, size: float = 14) -> str:
    s = size / 16
    return f'<path transform="translate({x:.1f} {y:.1f}) scale({s:.3f})" d="{ICON[name]}" fill="{color}"/>'


def svg_wrap(w: int, h: int, t: dict, body: str, title: str, defs: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
            f'<title>{esc(title)}</title>'
            f'<style>text{{font-family:{FONT};fill:{t["text"]}}}.m{{fill:{t["muted"]}}}.a{{fill:{t["accent"]}}}'
            f'.mono{{font-family:{MONO}}}'
            f'.fade{{animation:fade .7s ease-out both}}@keyframes fade{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}'
            f'.grow{{transform-box:fill-box;transform-origin:left;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}}'
            f'@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}'
            f'.draw{{animation:draw 2.2s ease-out both}}@keyframes draw{{to{{stroke-dashoffset:0}}}}'
            f'</style><defs>'
            f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{t["bg"]}"/>'
            f'<stop offset="1" stop-color="{t["bg2"]}"/></linearGradient>'
            f'<linearGradient id="ac" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{t["accent"]}"/>'
            f'<stop offset="1" stop-color="{t["accent2"]}"/></linearGradient>{defs}</defs>'
            f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="14" fill="url(#bg)" stroke="{t["border"]}"/>'
            f'{body}</svg>')


def fmt(n: int) -> str:
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def title_row(text: str, sub: str, w: int) -> str:
    return (f'<rect x="24" y="24" width="4" height="18" rx="2" fill="url(#ac)"/>'
            f'<text x="36" y="39" font-size="16" font-weight="700">{esc(text)}</text>'
            f'<text x="{w-24}" y="39" font-size="11" class="m" text-anchor="end">{esc(sub)}</text>')


def hero_svg(t: dict, h: dict) -> str:
    W, H = 1000, 270
    defs = (f'<clipPath id="av"><circle cx="845" cy="135" r="74"/></clipPath>'
            f'<radialGradient id="b1"><stop offset="0" stop-color="{t["accent"]}" stop-opacity="{t["glow"]}"/>'
            f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="b2"><stop offset="0" stop-color="{t["accent2"]}" stop-opacity="{t["glow"]}"/>'
            f'<stop offset="1" stop-color="{t["accent2"]}" stop-opacity="0"/></radialGradient>'
            f'<linearGradient id="nm" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{t["text"]}"/>'
            f'<stop offset=".55" stop-color="{t["accent"]}"/><stop offset="1" stop-color="{t["accent2"]}"/></linearGradient>'
            f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
            f'<circle cx="2" cy="2" r="1" fill="{t["muted"]}" opacity=".18"/></pattern>'
            f'<clipPath id="card"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14"/></clipPath>')
    blobs = (f'<g clip-path="url(#card)"><rect width="{W}" height="{H}" fill="url(#dots)"/>'
             f'<ellipse cx="180" cy="40" rx="320" ry="200" fill="url(#b1)">'
             f'<animate attributeName="cx" values="180;320;180" dur="14s" repeatCount="indefinite"/></ellipse>'
             f'<ellipse cx="820" cy="260" rx="300" ry="190" fill="url(#b2)">'
             f'<animate attributeName="cx" values="820;660;820" dur="17s" repeatCount="indefinite"/></ellipse></g>')
    chips, x = [], 48
    for ic, label in h["chips"]:
        w = 40 + len(label) * 7.1
        chips.append(f'<g class="fade" style="animation-delay:{0.5 + len(chips)*0.15:.2f}s">'
                     f'<rect x="{x}" y="196" width="{w:.0f}" height="32" rx="16" fill="{t["pill"]}" stroke="{t["border"]}"/>'
                     f'{icon(ic, x + 13, 205, t["accent"])}'
                     f'<text x="{x + 33}" y="217" font-size="13" font-weight="600">{esc(label)}</text></g>')
        x += w + 10
    status = ""
    if h["hireable"]:
        status = (f'<g class="fade" style="animation-delay:.2s"><rect x="48" y="34" width="190" height="26" rx="13" '
                  f'fill="#22c55e" fill-opacity=".12" stroke="#22c55e" stroke-opacity=".5"/>'
                  f'<circle cx="64" cy="47" r="4" fill="#22c55e"><animate attributeName="opacity" values="1;.25;1" '
                  f'dur="1.8s" repeatCount="indefinite"/></circle>'
                  f'<text x="76" y="51.5" font-size="12" font-weight="600" style="fill:#22c55e">Open to opportunities</text></g>')
    avatar = ""
    if h["avatar"]:
        avatar = (f'<circle cx="845" cy="135" r="82" fill="none" stroke="url(#ac)" stroke-width="3" '
                  f'stroke-dasharray="14 10"><animateTransform attributeName="transform" type="rotate" '
                  f'from="0 845 135" to="360 845 135" dur="30s" repeatCount="indefinite"/></circle>'
                  f'<image x="771" y="61" width="148" height="148" clip-path="url(#av)" '
                  f'preserveAspectRatio="xMidYMid slice" href="{h["avatar"]}" xlink:href="{h["avatar"]}"/>'
                  f'<circle cx="845" cy="135" r="74" fill="none" stroke="{t["bg"]}" stroke-width="3"/>')
    body = (blobs + status +
            f'<text x="46" y="122" font-size="58" font-weight="800" fill="url(#nm)" style="fill:url(#nm)" '
            f'class="fade" letter-spacing="-1">{esc(h["name"])}</text>'
            f'<text x="48" y="158" font-size="18" font-weight="600" class="a fade" style="animation-delay:.25s">'
            f'{esc(h["headline"])}</text>'
            f'<text x="48" y="182" font-size="14" class="m fade mono" style="animation-delay:.4s">'
            f'{esc(h["sub"])}</text>' + "".join(chips) + avatar)
    return svg_wrap(W, H, t, body, f'{h["name"]}: {h["headline"]}', defs)


def stats_svg(t: dict, s: dict) -> str:
    W, H = 470, 250
    rows = [
        ("pulse", "All-time contributions", fmt(s["all_time"])),
        ("calendar", "Contributions, past year", fmt(s["year"])),
        ("commit", "Commits, past year", fmt(s["commits"])),
        ("pr", "Pull requests", fmt(s["prs"])),
        ("repo", "Public repositories", fmt(s["repos"])),
        ("star", "Stars earned", fmt(s["stars"])),
    ]
    body = [title_row("GitHub Stats", "", W)]
    for i, (ic, label, val) in enumerate(rows):
        y = 78 + i * 28
        body.append(f'<g class="fade" style="animation-delay:{i*90}ms">{icon(ic, 26, y - 12, t["accent"])}'
                    f'<text x="50" y="{y}" font-size="13" class="m">{label}</text>'
                    f'<text x="292" y="{y}" font-size="14" font-weight="700" text-anchor="end">{val}</text></g>')
    cx, cy, r = 385, 128, 48
    circ = 2 * math.pi * r
    frac = min(1, s["cur"] / max(1, s["long"])) if s["cur"] else 0
    body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{t["grid"]}" stroke-width="8"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#ac)" stroke-width="8" stroke-linecap="round" '
                f'stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ*(1-max(frac, .02)):.1f}" transform="rotate(-90 {cx} {cy})">'
                f'<animate attributeName="stroke-dashoffset" from="{circ:.1f}" to="{circ*(1-max(frac, .02)):.1f}" '
                f'dur="1.6s" fill="freeze"/></circle>'
                f'{icon("flame", cx - 7, cy - 32, "#fb923c")}'
                f'<text x="{cx}" y="{cy+12}" font-size="30" font-weight="800" text-anchor="middle">{s["cur"]}</text>'
                f'<text x="{cx}" y="{cy+74}" font-size="12.5" font-weight="600" text-anchor="middle">day streak</text>'
                f'<text x="{cx}" y="{cy+92}" font-size="11" class="m" text-anchor="middle">best {s["long"]} days</text>')
    return svg_wrap(W, H, t, "".join(body), "GitHub stats")


def langs_svg(t: dict, langs: list[tuple[str, float, str]]) -> str:
    W, H = 360, 250
    top = [(n.replace("Jupyter Notebook", "Jupyter"), p, c) for n, p, c in langs[:6]]
    body = [title_row("Languages", "share across public repos", W)]
    # stacked bar
    x = 24.0
    body.append('<clipPath id="sb"><rect x="24" y="58" width="312" height="8" rx="4"/></clipPath><g clip-path="url(#sb)">')
    rest = 1 - sum(p for _, p, _ in top)
    for name, p, color in top + ([("Other", rest, t["muted"])] if rest > 0.003 else []):
        body.append(f'<rect class="grow" x="{x:.2f}" y="58" width="{312*p + .6:.2f}" height="8" fill="{color}"/>')
        x += 312 * p
    body.append("</g>")
    peak = top[0][1] if top else 1
    for i, (name, p, color) in enumerate(top):
        y = 96 + i * 26
        w = max(4, 160 * p / peak)
        body.append(f'<g class="fade" style="animation-delay:{i*80}ms">'
                    f'<circle cx="29" cy="{y-4}" r="5" fill="{color}"/>'
                    f'<text x="42" y="{y}" font-size="12.5" font-weight="500">{esc(name)}</text>'
                    f'<rect x="122" y="{y-9}" width="160" height="7" rx="3.5" fill="{t["grid"]}"/>'
                    f'<rect class="grow" style="animation-delay:{i*80}ms" x="122" y="{y-9}" width="{w:.1f}" height="7" rx="3.5" fill="{color}"/>'
                    f'<text x="336" y="{y}" font-size="12" class="m mono" text-anchor="end">{p*100:.1f}%</text></g>')
    return svg_wrap(W, H, t, "".join(body), "Most used languages")


def smooth_path(pts: list[tuple[float, float]]) -> str:
    """Catmull-Rom spline through the points, as cubic Béziers."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(0, i - 1)], pts[i], pts[i + 1]
        p3 = pts[min(len(pts) - 1, i + 2)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def activity_svg(t: dict, days: dict[date, int]) -> str:
    end = NOW.date()
    start = end - timedelta(days=7 * 52 - 1)
    weeks = [sum(days.get(start + timedelta(days=w * 7 + i), 0) for i in range(7)) for w in range(52)]
    W, H, L, R, T, B = 1000, 260, 56, 28, 70, 40
    pw, ph = W - L - R, H - T - B
    peak = max(weeks) or 1
    # Square-root scale keeps one huge week from flattening the rest; labels show real values.
    top = math.ceil(math.sqrt(peak)) ** 2
    yv = lambda v: T + ph * (1 - math.sqrt(v / top))
    pts = [(L + pw * i / 51, yv(v)) for i, v in enumerate(weeks)]
    line = smooth_path(pts)
    area = line + f" L{L+pw},{T+ph} L{L},{T+ph} Z"
    total, active_weeks = sum(weeks), sum(1 for v in weeks if v)
    best = max(range(52), key=lambda i: weeks[i])
    defs = (f'<linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["accent"]}" stop-opacity=".45"/>'
            f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></linearGradient>')
    body = [title_row("Contribution activity", f"{total:,} contributions · {active_weeks}/52 active weeks · weekly", W)]
    for k in range(5):
        v = round(top * (k / 4) ** 2)
        y = yv(v)
        body.append(f'<line x1="{L}" x2="{L+pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{t["grid"]}" stroke-dasharray="{"" if k == 0 else "3 4"}"/>'
                    f'<text x="{L-10}" y="{y+4:.1f}" font-size="10.5" class="m mono" text-anchor="end">{v}</text>')
    last_month = None
    for i in range(52):
        d = start + timedelta(days=i * 7)
        if d.month != last_month and i < 50:
            last_month = d.month
            body.append(f'<text x="{L + pw*i/51:.1f}" y="{H-16}" font-size="11" class="m">{d.strftime("%b")}</text>')
    plen = sum(math.dist(pts[i], pts[i + 1]) for i in range(51)) * 1.15
    body.append(f'<path d="{area}" fill="url(#ar)" class="fade" style="animation-duration:2s"/>'
                f'<path d="{line}" fill="none" stroke="url(#ac)" stroke-width="2.6" stroke-linecap="round" '
                f'stroke-dasharray="{plen:.0f}" stroke-dashoffset="{plen:.0f}" class="draw"/>')
    bx, by = pts[best]
    lx = min(max(bx, L + 60), W - R - 60)
    body.append(f'<g class="fade" style="animation-delay:1.6s"><circle cx="{bx:.1f}" cy="{by:.1f}" r="5" fill="{t["accent"]}" '
                f'stroke="{t["bg"]}" stroke-width="2.5"/>'
                f'<rect x="{lx-52:.1f}" y="{by-34:.1f}" width="104" height="22" rx="11" fill="{t["pill"]}" stroke="{t["border"]}"/>'
                f'<text x="{lx:.1f}" y="{by-19:.1f}" font-size="11" font-weight="600" text-anchor="middle">peak · {weeks[best]} / week</text></g>')
    lx2, ly2 = pts[-1]
    body.append(f'<circle cx="{lx2:.1f}" cy="{ly2:.1f}" r="4" fill="{t["accent2"]}">'
                f'<animate attributeName="r" values="4;7;4" dur="2s" repeatCount="indefinite"/></circle>')
    return svg_wrap(W, H, t, "".join(body), "Weekly contribution activity", defs)


def wrap(text: str, width: int, lines: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            out.append(cur)
            cur = w
            if len(out) == lines:
                break
        else:
            cur = f"{cur} {w}".strip()
    else:
        out.append(cur)
    out = [o for o in out if o][:lines]
    if len(" ".join(out)) < len(text.strip()) and out:
        out[-1] = out[-1][: width - 1].rstrip(" ,.;:—-") + "…"
    return out


def card_svg(t: dict, r: dict) -> str:
    W, H = 480, 200
    lang, color = r["lang"]
    defs = (f'<linearGradient id="st" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{color}"/>'
            f'<stop offset="1" stop-color="{t["accent"]}"/></linearGradient>'
            f'<clipPath id="cc"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14"/></clipPath>'
            f'<radialGradient id="gl"><stop offset="0" stop-color="{color}" stop-opacity=".22"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')
    body = [f'<g clip-path="url(#cc)"><rect width="{W}" height="4" fill="url(#st)"/>'
            f'<ellipse cx="{W-40}" cy="0" rx="190" ry="120" fill="url(#gl)"/></g>',
            f'{icon("repo", 24, 27, t["accent"], 16)}'
            f'<text x="48" y="41" font-size="17" font-weight="700" class="fade">{esc(r["name"])}</text>']
    if r["stargazerCount"]:
        body.append(f'{icon("star", W - 52, 28, "#eab308")}'
                    f'<text x="{W-24}" y="40" font-size="13" font-weight="600" text-anchor="end">{r["stargazerCount"]}</text>')
    for i, line in enumerate(wrap(r["summary"], 64, 3)):
        body.append(f'<text x="24" y="{70 + i*20}" font-size="13" class="m fade" style="animation-delay:.15s">{esc(line)}</text>')
    x = 24
    for tag in r["tags"]:
        c = TAG_COLORS.get(tag, t["accent"])
        w = 18 + len(tag) * 6.6
        body.append(f'<g class="fade" style="animation-delay:.3s"><rect x="{x}" y="134" width="{w:.0f}" height="22" rx="11" '
                    f'fill="{c}" fill-opacity=".14" stroke="{c}" stroke-opacity=".45"/>'
                    f'<text x="{x + w/2:.0f}" y="149" font-size="11" font-weight="600" text-anchor="middle" style="fill:{c}">{esc(tag)}</text></g>')
        x += w + 7
    body.append(f'<line x1="24" x2="{W-24}" y1="168" y2="168" stroke="{t["grid"]}"/>'
                f'<circle cx="30" cy="184" r="5.5" fill="{color}"/><text x="42" y="188" font-size="12" font-weight="500">{esc(lang)}</text>'
                f'{icon("commit", W - 250, 177, t["muted"], 13)}'
                f'<text x="{W-232}" y="188" font-size="12" class="m">{r["commits"]:,} commits</text>'
                f'{icon("clock", W - 128, 177, t["muted"], 13)}'
                f'<text x="{W-110}" y="188" font-size="12" class="m">{ago(r["active"])}</text>')
    return svg_wrap(W, H, t, "".join(body), r["name"], defs)


def divider_svg(t: dict) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="14" viewBox="0 0 1000 14">'
            f'<defs><linearGradient id="d" x1="0" x2="1"><stop offset="0" stop-color="{t["accent"]}" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="{t["accent"]}"/><stop offset="1" stop-color="{t["accent2"]}" stop-opacity="0"/>'
            f'</linearGradient></defs><rect y="6" width="1000" height="2" rx="1" fill="url(#d)"/>'
            f'<circle cx="500" cy="7" r="4" fill="{t["accent"]}"><animate attributeName="cx" values="120;880;120" '
            f'dur="9s" repeatCount="indefinite"/></circle></svg>')


def footer_svg(t: dict, text: str) -> str:
    W, H = 1000, 120
    d1 = "M0,40 C160,90 340,0 500,40 C660,80 840,10 1000,45 L1000,120 L0,120 Z"
    d2 = "M0,60 C200,20 320,100 520,62 C700,30 860,100 1000,70 L1000,120 L0,120 Z"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<defs><linearGradient id="w" x1="0" x2="1"><stop offset="0" stop-color="{t["accent"]}"/>'
            f'<stop offset="1" stop-color="{t["accent2"]}"/></linearGradient></defs>'
            f'<path d="{d1}" fill="url(#w)" opacity=".25"><animate attributeName="d" dur="10s" repeatCount="indefinite" '
            f'values="{d1};{d2};{d1}"/></path>'
            f'<path d="{d2}" fill="url(#w)" opacity=".55"><animate attributeName="d" dur="12s" repeatCount="indefinite" '
            f'values="{d2};{d1};{d2}"/></path>'
            f'<text x="500" y="102" font-family="{FONT}" font-size="14" font-weight="600" fill="#ffffff" '
            f'text-anchor="middle">{esc(text)}</text></svg>')


def write_svg(name: str, render) -> str:
    for theme, t in THEMES.items():
        (ASSETS / f"{name}-{theme}.svg").write_text(render(t), encoding="utf-8")
    return name


def picture(name: str, alt: str, width: str | None = None) -> str:
    w = f' width="{width}"' if width else ""
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<source media="(prefers-color-scheme: light)" srcset="assets/{name}-light.svg">'
            f'<img src="assets/{name}-dark.svg" alt="{esc(alt)}"{w}></picture>')


def fetch_avatar(url: str) -> str:
    local = ASSETS / "avatar.jpg"          # a committed photo overrides the GitHub avatar
    if local.exists():
        return "data:image/jpeg;base64," + base64.b64encode(local.read_bytes()).decode()
    try:
        req = urllib.request.Request(url + ("&" if "?" in url else "?") + "s=300",
                                     headers={"User-Agent": "profile-readme-generator"})
        with urllib.request.urlopen(req, timeout=30) as r:
            kind = r.headers.get_content_type() or "image/png"
            return f"data:{kind};base64," + base64.b64encode(r.read()).decode()
    except Exception as e:  # avatar is decoration; never fail the build over it
        print(f"avatar skipped: {e}")
        return ""

# ════════════════════════════════════════════════════════════════════════════
# Markdown
# ════════════════════════════════════════════════════════════════════════════

def badge(label: str, msg: str, color: str, logo: str | None = None, link: str | None = None,
          style: str = "for-the-badge") -> str:
    q = lambda s: quote(s.replace("-", "--").replace("_", "__"), safe="")
    url = (f"https://img.shields.io/badge/{q(label)}-{q(msg)}-{color.lstrip('#')}?style={style}"
           if msg else f"https://img.shields.io/badge/{q(label)}-{color.lstrip('#')}?style={style}")
    if logo:
        url += f"&logo={logo}&logoColor=white"
    img = f'<img src="{url}" alt="{esc(label)}">'
    return f'<a href="{link}">{img}</a>' if link else img


SOCIAL = {
    "LINKEDIN": ("LinkedIn", "0A66C2", "linkedin"), "TWITTER": ("X", "000000", "x"),
    "YOUTUBE": ("YouTube", "FF0000", "youtube"), "INSTAGRAM": ("Instagram", "E4405F", "instagram"),
    "MEDIUM": ("Medium", "000000", "medium"), "DEV": ("DEV", "0A0A0A", "devdotto"),
    "MASTODON": ("Mastodon", "6364FF", "mastodon"), "BLUESKY": ("Bluesky", "0285FF", "bluesky"),
}
COMMIT_EMOJI = [(r"^feat", "✨"), (r"^fix", "🐛"), (r"^docs?|readme", "📝"), (r"^refactor", "♻️"),
                (r"^test", "✅"), (r"^perf", "⚡"), (r"^(ci|build)", "🏗️"), (r"^chore", "🔧"),
                (r"demo|video", "🎬"), (r"^add", "➕"), (r"secur|harden", "🔒"), (r"", "🔨")]


def section(title: str) -> str:
    return f'\n<br/>\n\n<h2 align="left">{title}</h2>\n\n{picture("divider", "", "100%")}\n'


def build(user: dict, repos: list[dict], days: dict[date, int]) -> str:
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "cards").mkdir(exist_ok=True)
    for old in (ASSETS / "cards").glob("*.svg"):
        old.unlink()

    enrich(repos)
    cc = user["contributionsCollection"]
    cur, longest = streaks(days)
    stats = dict(all_time=sum(days.values()), year=cc["contributionCalendar"]["totalContributions"],
                 commits=cc["totalCommitContributions"], prs=user["pullRequests"]["totalCount"],
                 repos=user["public_repo_count"], stars=sum(r["stargazerCount"] for r in repos),
                 cur=cur, long=longest)
    langs = language_shares(repos)
    tech = aggregate_tech(repos)

    name = user["name"] or USERNAME
    first = name.split()[0].title()
    blog = (user["websiteUrl"] or "").strip()
    if blog and not blog.startswith("http"):
        blog = "https://" + blog
    location = re.sub(r"\s*,\s*", ", ", user["location"] or "").strip()
    human = [r for r in repos if r["recent"]]
    building = min(human, key=lambda r: r["age_days"]) if human else None
    top_lang_names = [n for n, _, _ in langs[:3]]
    generated = NOW.strftime("%d %b %Y, %H:%M UTC")

    hero = dict(name=name.title() if name.isupper() else name, headline=HEADLINE, hireable=user["isHireable"],
                sub=f"📍 {location}" + (f"  ·  building {building['name']}" if building else ""),
                avatar=fetch_avatar(user["avatarUrl"]),
                chips=[("pulse", f"{fmt(stats['all_time'])} contributions"),
                       ("repo", f"{stats['repos']} public repos"),
                       ("flame", f"{cur}-day streak" if cur else f"best streak {longest}d"),
                       ("pr", f"{fmt(stats['prs'])} pull requests")])
    write_svg("hero", lambda t: hero_svg(t, hero))
    write_svg("stats", lambda t: stats_svg(t, stats))
    write_svg("languages", lambda t: langs_svg(t, langs))
    write_svg("activity", lambda t: activity_svg(t, days))
    write_svg("divider", divider_svg)
    write_svg("footer", lambda t: footer_svg(t, f"Thanks for visiting, {first}'s profile refreshes itself every 6 hours"))

    pinned = [n["name"] for n in user["pinnedItems"]["nodes"] if n]
    ranked = sorted(repos, key=lambda r: (r["name"] not in pinned, -r["score"]))
    featured, rest = ranked[:FEATURED_COUNT], ranked[FEATURED_COUNT:]
    for r in featured:
        write_svg(f"cards/{r['name']}", lambda t, r=r: card_svg(t, r))

    # ── header ──
    typing = ";".join(quote(s) for s in [
        TAGLINE,
        f"{stats['all_time']:,} contributions since {user['createdAt'][:4]}",
        *([f"Currently building {building['name']}"] if building else []),
        f"Shipping with {' · '.join(top_lang_names)}",
    ])
    links = [badge("Portfolio", "", ACCENT_DEEP, "googlechrome", blog)] if blog else []
    for acc in user["socialAccounts"]["nodes"]:
        label, color, logo = SOCIAL.get(acc["provider"], ("Link", "555555", None))
        if acc["provider"] == "GENERIC":
            label = acc["displayName"] or "Link"
        links.append(badge(label, "", color, logo, acc["url"]))
    if user["email"]:
        links.append(badge("Email", "", "D14836", "gmail", f"mailto:{user['email']}"))
    links.append(badge("GitHub", "", "181717", "github", f"https://github.com/{USERNAME}?tab=repositories"))

    md = [f"""<a href="{blog or f'https://github.com/{USERNAME}'}">{picture('hero', f'{name}: {HEADLINE}', '100%')}</a>

<div align="center">

<a href="https://github.com/{USERNAME}"><img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=18&duration=3000&pause=1000&color={ACCENT.lstrip('#').upper()}&center=true&vCenter=true&width=760&height=40&lines={typing}" alt="{esc(TAGLINE)}"/></a>

{' '.join(links)}

<img src="https://komarev.com/ghpvc/?username={USERNAME}&color=7c3aed&style=flat-square&label=profile+views" alt="Profile views"/>
<img src="https://img.shields.io/github/followers/{USERNAME}?style=flat-square&color=7c3aed&label=followers&logo=github" alt="Followers"/>
<img src="https://img.shields.io/badge/stars_earned-{stats['stars']}-7c3aed?style=flat-square&logo=githubsponsors&logoColor=white" alt="Stars"/>

</div>
"""]

    # ── about ──
    md.append(section("👋 About me"))
    md.append(f"> {md_esc(user['bio'] or TAGLINE)}\n")
    facts = [("📍", "Based in", f"**{md_esc(location or 'Earth')}**"),
             ("🗓️", "On GitHub since", f"**{datetime.fromisoformat(user['createdAt'][:10]).strftime('%B %Y')}**")]
    if building:
        facts.append(("🔭", "Currently building", f"**[{building['name']}]({building['url']})**: {md_esc(building['summary'])}"))
    focus = [c for c in ("AI / ML", "Full-stack", "Backend") if any(c in r["tags"] for r in repos)]
    if focus:
        facts.append(("🧠", "Focus areas", f"**{' · '.join(focus)}** across {len(repos)} public projects"))
    facts.append(("⚡", "Past year", f"**{stats['year']:,}** contributions · **{cur}**-day streak (best **{longest}**)"))
    if user["isHireable"]:
        facts.append(("🤝", "Open to", "full-time roles, freelance work and collaborations"))
    md.append("<table>\n" + "\n".join(
        f"<tr><td>{e}</td><td><b>{k}</b></td><td>\n\n{v}\n\n</td></tr>" for e, k, v in facts) + "\n</table>")

    # ── stats ──
    md.append(section("📊 GitHub at a glance"))
    md.append(f"""<div align="center">

<a href="https://github.com/{USERNAME}?tab=repositories">{picture('stats', 'GitHub stats', '56.3%')}</a><a href="https://github.com/{USERNAME}?tab=repositories">{picture('languages', 'Top languages', '43.1%')}</a>

{picture('activity', 'Weekly contribution activity', '100%')}

</div>""")

    # ── featured ──
    md.append(section("🚀 Featured projects"))
    md.append('<table>')
    for i in range(0, len(featured), 2):
        md.append("<tr>")
        for r in featured[i:i + 2]:
            links = [f'<a href="{r["url"]}"><b>Source</b></a>']
            if r.get("homepageUrl"):
                links.insert(0, f'<a href="{r["homepageUrl"]}"><b>🌐 Live demo</b></a>')
            stack = [n for n in r["tech"] if r["tech"][n][2] not in ("DevOps & Tools",)][:6]
            md.append(f'<td width="50%" valign="top"><a href="{r["url"]}">'
                      f'{picture("cards/" + r["name"], r["name"], "100%")}</a>\n\n'
                      f'<p align="center"><sub>{" &nbsp;·&nbsp; ".join(links)}'
                      f'{"<br/>" + " · ".join(f"<code>{esc(s)}</code>" for s in stack) if stack else ""}</sub></p>\n\n</td>')
        md.append("</tr>")
    md.append("</table>")

    if rest:
        md.append(f"\n<details>\n<summary><b>📂 More public projects ({len(rest)})</b></summary>\n\n"
                  "| Project | What it does | Stack | Active |\n|:--|:--|:--|--:|")
        for r in rest:
            stack = ", ".join(f"`{n}`" for n in r["tech"] if r["tech"][n][2] not in ("DevOps & Tools", "Languages"))
            md.append(f"| **[{r['name']}]({r['url']})** | {md_esc(wrap(r['summary'], 90, 1)[0]).replace('|', '/')} "
                      f"| {stack or r['lang'][0]} | {ago(r['active'])} |")
        md.append("\n</details>")

    # ── tech stack ──
    md.append(section("🛠️ Tech stack"))
    md.append("<sub>Auto-detected from the dependency files of my public repositories. "
              "The number on each badge is how many projects use it.</sub>\n\n<table>")
    for cat, items in tech.items():
        icons = list(dict.fromkeys(i for _, i, _, _ in items if i))
        badges = [badge(n, str(c), "1f2433", slug, style="flat-square") for n, i, slug, c in items if not i]
        cell = ""
        if icons:
            ic = ",".join(icons)
            cell += (f'<picture><source media="(prefers-color-scheme: light)" '
                     f'srcset="https://skillicons.dev/icons?i={ic}&theme=light&perline=14">'
                     f'<img src="https://skillicons.dev/icons?i={ic}&theme=dark&perline=14" '
                     f'height="40" alt="{esc(cat)}"></picture>')
        if badges:
            cell += ("<br/>" if icons else "") + " ".join(badges)
        md.append(f'<tr><td align="right" width="130"><b>{esc(cat)}</b></td><td>{cell}</td></tr>')
    md.append("</table>")

    # ── recent commits ──
    commits = sorted(((c["committedDate"], r["name"], r["url"], c["messageHeadline"], c["url"])
                      for r in repos for c in r["recent"]), reverse=True)
    if commits:
        md.append(section("📝 Recent commits"))
        md.append("| | Repository | Commit | When |\n|:-:|:--|:--|--:|")
        seen = Counter()
        for when, repo, rurl, msg, url in commits:
            if seen[repo] >= 2:
                continue
            seen[repo] += 1
            emoji = next(e for p, e in COMMIT_EMOJI if re.search(p, msg, re.I))
            msg = msg if len(msg) <= 72 else msg[:71] + "…"
            msg = md_esc(msg).replace("[", "(").replace("]", ")").replace("|", "/")
            md.append(f"| {emoji} | [**{repo}**]({rurl}) | [{msg}]({url}) | <sub>{ago(when)}</sub> |")
            if sum(seen.values()) >= 6:
                break

    # ── snake + footer ──
    md.append(section("🐍 Contribution snake"))
    md.append(f"""<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake.svg">
  <img alt="Contribution snake" src="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
</picture>
</div>

<br/>

{picture('footer', 'Thanks for visiting', '100%')}

<p align="center"><sub>🤖 Generated from live GitHub data by <a href="generate_readme.py">generate_readme.py</a> · last refresh {generated}</sub></p>
""")
    return "\n".join(md)


if __name__ == "__main__":
    user, repos, days = fetch_all()
    readme = build(user, repos, days)
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    print(f"README.md generated: {len(repos)} public repos, {sum(days.values())} all-time contributions")
