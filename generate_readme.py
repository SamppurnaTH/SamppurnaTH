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

import html
import json
import math
import os
import re
import sys
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
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read().decode("utf-8"))
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
    repositories(first: 50, after: $cursor, privacy: PUBLIC, isFork: false,
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
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"", line)            # links → text
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
# SVG rendering (dark + light variants)
# ════════════════════════════════════════════════════════════════════════════
THEMES = {
    "dark": dict(bg="#0d1117", panel="#161b22", border="#30363d", text="#e6edf3",
                 muted="#8b949e", accent=ACCENT, grid="#21262d", pill="#2a2140"),
    "light": dict(bg="#ffffff", panel="#f6f8fa", border="#d0d7de", text="#1f2328",
                  muted="#59636e", accent=ACCENT_DEEP, grid="#eaeef2", pill="#efe9ff"),
}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
esc = html.escape
md_esc = lambda s: html.escape(s, quote=False)


def svg_wrap(w: int, h: int, t: dict, body: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(title)}"><title>{esc(title)}</title>'
            f'<style>text{{font-family:{FONT};fill:{t["text"]}}}.m{{fill:{t["muted"]}}}'
            f'.a{{fill:{t["accent"]}}}.fade{{animation:f .8s ease-out both}}'
            f'@keyframes f{{from{{opacity:0}}to{{opacity:1}}}}</style>'
            f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>'
            f'{body}</svg>')


def fmt(n: int) -> str:
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def stats_svg(t: dict, s: dict) -> str:
    rows = [
        ("All-time contributions", fmt(s["all_time"])),
        ("Contributions (past year)", fmt(s["year"])),
        ("Commits (past year)", fmt(s["commits"])),
        ("Pull requests", fmt(s["prs"])),
        ("Public repositories", fmt(s["repos"])),
        ("Stars earned", fmt(s["stars"])),
    ]
    body = [f'<text x="24" y="38" font-size="17" font-weight="600" class="a">GitHub Stats</text>']
    for i, (label, val) in enumerate(rows):
        y = 72 + i * 27
        body.append(f'<g class="fade" style="animation-delay:{i*90}ms">'
                    f'<text x="24" y="{y}" font-size="13" class="m">{label}</text>'
                    f'<text x="268" y="{y}" font-size="13.5" font-weight="600" text-anchor="end">{val}</text></g>')
    # streak ring
    cx, cy = 370, 128
    body.append(f'<circle cx="{cx}" cy="{cy}" r="46" fill="none" stroke="{t["grid"]}" stroke-width="7"/>'
                f'<circle cx="{cx}" cy="{cy}" r="46" fill="none" stroke="{t["accent"]}" stroke-width="7" '
                f'stroke-linecap="round" stroke-dasharray="{min(1, s["cur"]/max(1, s["long"]))*289:.0f} 289" '
                f'transform="rotate(-90 {cx} {cy})"/>'
                f'<text x="{cx}" y="{cy+8}" font-size="26" font-weight="700" text-anchor="middle">{s["cur"]}</text>'
                f'<text x="{cx}" y="{cy+66}" font-size="12" class="m" text-anchor="middle">day streak</text>'
                f'<text x="{cx}" y="{cy+84}" font-size="11" class="m" text-anchor="middle">best: {s["long"]} days</text>')
    return svg_wrap(450, 240, t, "".join(body), "GitHub stats")


def langs_svg(t: dict, langs: list[tuple[str, float, str]]) -> str:
    top = [(n.replace("Jupyter Notebook", "Jupyter"), p, c) for n, p, c in langs[:6]]
    body = [f'<text x="24" y="38" font-size="17" font-weight="600" class="a">Languages</text>',
            f'<text x="326" y="38" font-size="11" class="m" text-anchor="end">across public repos</text>']
    peak = top[0][1] if top else 1
    for i, (name, p, color) in enumerate(top):
        y = 70 + i * 28
        w = max(3, 150 * p / peak)
        body.append(f'<g class="fade" style="animation-delay:{i*80}ms">'
                    f'<circle cx="29" cy="{y-4}" r="5" fill="{color}"/>'
                    f'<text x="42" y="{y}" font-size="12.5">{esc(name)}</text>'
                    f'<rect x="128" y="{y-9}" width="150" height="8" rx="4" fill="{t["grid"]}"/>'
                    f'<rect x="128" y="{y-9}" width="{w:.1f}" height="8" rx="4" fill="{color}"/>'
                    f'<text x="326" y="{y}" font-size="12" class="m" text-anchor="end">{p*100:.1f}%</text></g>')
    return svg_wrap(350, 240, t, "".join(body), "Most used languages")


def activity_svg(t: dict, days: dict[date, int]) -> str:
    end = NOW.date()
    start = end - timedelta(days=7 * 52 - 1)
    weeks = [sum(days.get(start + timedelta(days=w * 7 + i), 0) for i in range(7)) for w in range(52)]
    W, H, L, R, T, B = 820, 230, 48, 20, 56, 36
    pw, ph = W - L - R, H - T - B
    peak = max(weeks) or 1
    nice = 10 ** math.floor(math.log10(peak)) if peak >= 10 else 1
    top = math.ceil(peak / nice) * nice
    pts = [(L + pw * i / 51, T + ph * (1 - v / top)) for i, v in enumerate(weeks)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{L},{T+ph} " + line + f" {L+pw},{T+ph}"
    total = sum(weeks)
    best = max(range(52), key=lambda i: weeks[i])
    body = [f'<text x="24" y="34" font-size="17" font-weight="600" class="a">Contribution activity</text>',
            f'<text x="{W-24}" y="34" font-size="12" class="m" text-anchor="end">{total:,} contributions · last 52 weeks</text>',
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["accent"]}" stop-opacity=".45"/>'
            f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></linearGradient></defs>']
    for k in range(5):
        y = T + ph * k / 4
        body.append(f'<line x1="{L}" x2="{L+pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{t["grid"]}"/>'
                    f'<text x="{L-8}" y="{y+4:.1f}" font-size="10" class="m" text-anchor="end">{int(top*(1-k/4))}</text>')
    last_month = None
    for i in range(52):
        d = start + timedelta(days=i * 7)
        if d.month != last_month and i < 50:
            last_month = d.month
            body.append(f'<text x="{L + pw*i/51:.1f}" y="{H-14}" font-size="10" class="m">{d.strftime("%b")}</text>')
    body.append(f'<polygon points="{area}" fill="url(#g)"/>'
                f'<polyline points="{line}" fill="none" stroke="{t["accent"]}" stroke-width="2.2" stroke-linejoin="round"/>')
    bx, by = pts[best]
    body.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="4.5" fill="{t["accent"]}" stroke="{t["bg"]}" stroke-width="2"/>'
                f'<text x="{min(bx, W-120):.1f}" y="{by-10:.1f}" font-size="11" text-anchor="middle">peak {weeks[best]}/wk</text>')
    return svg_wrap(W, H, t, "".join(body), "Weekly contribution activity")


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
        out[-1] = out[-1][: width - 1].rstrip(" ,.;:") + "…"
    return out


def card_svg(t: dict, r: dict) -> str:
    W, H = 400, 170
    body = [f'<text x="20" y="34" font-size="16" font-weight="600" class="a">{esc(r["name"])}</text>']
    if r["stargazerCount"]:
        body.append(f'<text x="{W-20}" y="34" font-size="12.5" class="m" text-anchor="end">★ {r["stargazerCount"]}</text>')
    for i, line in enumerate(wrap(r["summary"], 56, 3)):
        body.append(f'<text x="20" y="{60 + i*19}" font-size="12.5" class="m">{esc(line)}</text>')
    x = 20
    for tag in r["tags"]:
        w = 12 + len(tag) * 6.4
        body.append(f'<rect x="{x}" y="112" width="{w:.0f}" height="20" rx="10" fill="{t["pill"]}"/>'
                    f'<text x="{x + w/2:.0f}" y="126" font-size="10.5" text-anchor="middle" class="a">{esc(tag)}</text>')
        x += w + 6
    lang, color = r["lang"]
    body.append(f'<circle cx="26" cy="151" r="5" fill="{color}"/><text x="36" y="155" font-size="11.5" class="m">{esc(lang)}</text>'
                f'<text x="{W-20}" y="155" font-size="11.5" class="m" text-anchor="end">'
                f'{r["commits"]:,} commits · active {ago(r["active"])}</text>')
    return svg_wrap(W, H, t, "".join(body), r["name"])


def write_svg(name: str, render) -> str:
    for theme, t in THEMES.items():
        (ASSETS / f"{name}-{theme}.svg").write_text(render(t), encoding="utf-8")
    return name


def picture(name: str, alt: str, width: str | None = None) -> str:
    w = f' width="{width}"' if width else ""
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<source media="(prefers-color-scheme: light)" srcset="assets/{name}-light.svg">'
            f'<img src="assets/{name}-dark.svg" alt="{esc(alt)}"{w}></picture>')

# ════════════════════════════════════════════════════════════════════════════
# Markdown
# ════════════════════════════════════════════════════════════════════════════

def badge(label: str, msg: str, color: str, logo: str | None = None, link: str | None = None) -> str:
    q = lambda s: quote(s.replace("-", "--").replace("_", "__"), safe="")
    url = f"https://img.shields.io/badge/{q(label)}-{q(msg)}-{color.lstrip('#')}?style=for-the-badge"
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


def build(user: dict, repos: list[dict], days: dict[date, int]) -> str:
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "cards").mkdir(exist_ok=True)
    for old in (ASSETS / "cards").glob("*.svg"):
        old.unlink()

    enrich(repos)
    cc = user["contributionsCollection"]
    cur, longest = streaks(days)
    stats = dict(all_time=sum(days.values()), year=cc["contributionCalendar"]["totalContributions"],
                 commits=cc["totalCommitContributions"],
                 prs=user["pullRequests"]["totalCount"], repos=user["public_repo_count"],
                 stars=sum(r["stargazerCount"] for r in repos), cur=cur, long=longest)
    langs = language_shares(repos)
    tech = aggregate_tech(repos)

    write_svg("stats", lambda t: stats_svg(t, stats))
    write_svg("languages", lambda t: langs_svg(t, langs))
    write_svg("activity", lambda t: activity_svg(t, days))

    pinned = [n["name"] for n in user["pinnedItems"]["nodes"] if n]
    ranked = sorted(repos, key=lambda r: (r["name"] not in pinned, -r["score"]))
    featured, rest = ranked[:FEATURED_COUNT], ranked[FEATURED_COUNT:]
    for r in featured:
        write_svg(f"cards/{r['name']}", lambda t, r=r: card_svg(t, r))

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

    # ── header ──
    typing = ";".join(quote(s) for s in [
        TAGLINE,
        f"{stats['all_time']:,} contributions since {user['createdAt'][:4]}",
        *( [f"Currently building {building['name']}"] if building else [] ),
        f"Shipping with {' · '.join(top_lang_names)}",
    ])
    socials = [badge("Portfolio", blog.split("//")[-1].rstrip("/"), ACCENT_DEEP, "googlechrome", blog)] if blog else []
    for acc in user["socialAccounts"]["nodes"]:
        label, color, logo = SOCIAL.get(acc["provider"], ("Link", "555555", None))
        if acc["provider"] == "GENERIC":
            label = acc["displayName"] or "Link"
        socials.append(badge(label, "Connect", color, logo, acc["url"]))
    if user["email"]:
        socials.append(badge("Email", "Say hello", "D14836", "gmail", f"mailto:{user['email']}"))
    if user["isHireable"]:
        socials.append(badge("Status", "Open to opportunities", "2EA043", "github", f"https://github.com/{USERNAME}"))

    md = [f"""<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:7c3aed&height=200&section=header&text={quote(name)}&fontSize=54&fontColor=ffffff&animation=fadeIn&fontAlignY=36&desc={quote(HEADLINE)}&descSize=17&descAlignY=58&descColor=e9d5ff" alt="{esc(name)}"/>

<a href="https://github.com/{USERNAME}"><img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=500&size=19&duration=3200&pause=1100&color={ACCENT.lstrip('#').upper()}&center=true&vCenter=true&width=720&height=44&lines={typing}" alt="Typing intro"/></a>

{' '.join(socials)}

<img src="https://komarev.com/ghpvc/?username={USERNAME}&color=7c3aed&style=flat-square&label=profile+views" alt="Profile views"/>
<img src="https://img.shields.io/github/followers/{USERNAME}?style=flat-square&color=7c3aed&label=followers" alt="Followers"/>
<img src="https://img.shields.io/badge/stars_earned-{stats['stars']}-7c3aed?style=flat-square" alt="Stars"/>

</div>

## 👋 About me

{md_esc(user['bio'] or TAGLINE)}

- 📍 Based in **{esc(location or 'Earth')}**, on GitHub since **{datetime.fromisoformat(user['createdAt'][:10]).strftime('%B %Y')}**"""]
    if building:
        md.append(f"- 🔭 Currently building **[{building['name']}]({building['url']})**: {md_esc(building['summary'])}")
    focus = [c for c in ("AI / ML", "Full-stack", "Backend") if any(c in r["tags"] for r in repos)]
    if focus:
        md.append(f"- 🧠 Focus areas: **{' · '.join(focus)}**, across {len(repos)} public projects")
    md.append(f"- ⚡ **{stats['year']:,}** contributions in the past year · current streak **{cur} day{'s' if cur != 1 else ''}** (best {longest})")
    if user["isHireable"]:
        md.append("- 🤝 Open to full-time roles, freelance work and collaborations")

    # ── stats ──
    md.append(f"""
## 📊 GitHub at a glance

<div align="center">

<a href="https://github.com/{USERNAME}?tab=repositories">{picture('stats', 'GitHub stats', '55%')}</a><a href="https://github.com/{USERNAME}?tab=repositories">{picture('languages', 'Top languages', '42.8%')}</a>

{picture('activity', 'Weekly contribution activity', '100%')}

</div>""")

    # ── featured ──
    md.append("\n## 🚀 Featured projects\n\n<table>")
    for i in range(0, len(featured), 2):
        md.append("<tr>")
        for r in featured[i:i + 2]:
            links = [f'<a href="{r["url"]}">Code</a>']
            if r.get("homepageUrl"):
                links.insert(0, f'<a href="{r["homepageUrl"]}">Live demo</a>')
            md.append(f'<td width="50%" valign="top"><a href="{r["url"]}">'
                      f'{picture("cards/" + r["name"], r["name"], "100%")}</a><br/>'
                      f'<sub>{" · ".join(links)}</sub></td>')
        md.append("</tr>")
    md.append("</table>")

    if rest:
        md.append(f"\n<details>\n<summary><b>More public projects ({len(rest)})</b></summary>\n\n"
                  "| Project | What it does | Stack | Updated |\n|---|---|---|---|")
        for r in rest:
            stack = ", ".join(n for n in r["tech"] if r["tech"][n][2] != "DevOps & Tools")
            md.append(f"| [{r['name']}]({r['url']}) | {md_esc(wrap(r['summary'], 90, 1)[0]).replace('|', '/')} "
                      f"| {stack or r['lang'][0]} | {ago(r['active'])} |")
        md.append("\n</details>")

    # ── tech stack ──
    md.append("\n## 🛠️ Tech stack\n\n<sub>Detected from the dependency files of my public repositories; "
              "the number shows how many projects use it.</sub>\n\n<table>")
    for cat, items in tech.items():
        icons = [i for _, i, _, _ in items if i]
        badges = [badge(n, str(c), "30363d", slug) for n, i, slug, c in items if not i]
        cell = ""
        if icons:
            cell += f'<img src="https://skillicons.dev/icons?i={",".join(dict.fromkeys(icons))}&perline=12" alt="{esc(cat)}"/> '
        cell += " ".join(badges).replace("for-the-badge", "flat-square")
        md.append(f"<tr><td><b>{esc(cat)}</b></td><td>{cell}</td></tr>")
    md.append("</table>")

    # ── recent commits ──
    commits = []
    for r in repos:
        for c in r["recent"]:
            commits.append((c["committedDate"], r["name"], c["messageHeadline"], c["url"]))
    commits.sort(reverse=True)
    if commits:
        md.append("\n## 📝 Recent commits\n")
        seen = Counter()
        for when, repo, msg, url in commits:
            if seen[repo] >= 2:
                continue
            seen[repo] += 1
            msg = msg if len(msg) <= 80 else msg[:79] + "…"
            md.append(f"- **{repo}**: [{md_esc(msg).replace('[', '(').replace(']', ')')}]({url}) <sub>· {ago(when)}</sub>")
            if sum(seen.values()) >= 6:
                break

    # ── snake + footer ──
    md.append(f"""
## 🐍 Contribution snake

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake.svg">
  <img alt="Contribution snake" src="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
</picture>
</div>

<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:7c3aed&height=100&section=footer" alt=""/>

<sub>Thanks for stopping by, {esc(first)} here. This page rebuilds itself from live GitHub data every 6 hours · last update {generated}</sub>

</div>
""")
    return "\n".join(md)


if __name__ == "__main__":
    user, repos, days = fetch_all()
    readme = build(user, repos, days)
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    print(f"README.md generated: {len(repos)} public repos, {sum(days.values())} all-time contributions")
