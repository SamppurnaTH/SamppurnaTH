#!/usr/bin/env python3
"""
Professional README.md generator for GitHub profile.
Generates a polished, production-grade README matching your exact profile data.
"""

import os
import requests
from datetime import datetime, timezone
from urllib.parse import quote

# ── Configuration ─────────────────────────────────────────────────────────────
USERNAME    = "SamppurnaTH"
LINKEDIN    = "thotavenkatavenu"
PORTFOLIO   = "https://venu-profile.vercel.app"
EMAIL       = "venuthota009@gmail.com"
GITHUB_API  = "https://api.github.com"

SKIP_REPOS = {USERNAME, "raj3176", "teamFedWorks"}

ORG_CONTRIBS = [
    {"org": "teamFedWorks",       "repo": "NextGen-Backend",         "commits": 274, "lang": "TypeScript", "desc": "Production LMS backend with CI/CD"},
    {"org": "raj3176",            "repo": "nextgen-backend-aws-2026", "commits": 155, "lang": "Python",     "desc": "AWS-native backend infrastructure"},
    {"org": "deftia-com",         "repo": "nextgen-lms",             "commits": 22,  "lang": "TypeScript", "desc": "Next-gen learning management system"},
    {"org": "fly-hii",            "repo": "Flyhii-AIAgent",          "commits": 5,   "lang": "Python",     "desc": "AI agent for flight booking"},
]

# Profile data (fallbacks if API unavailable)
PROFILE_DATA = {
    "contributions_last_year": 1488,
    "april_2026_commits": 507,
    "april_2026_repos_created": 2,
}

# ── GitHub API helpers ────────────────────────────────────────────────────────
def gh(path, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.get(f"{GITHUB_API}{path}", headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  API: {path} — {str(e)[:50]}")
        return {} if "user" in path else []

def get_user(token):
    return gh(f"/users/{USERNAME}", token)

def get_all_repos(token):
    repos, page = [], 1
    while page <= 5:
        batch = gh(f"/users/{USERNAME}/repos?per_page=100&page={page}&sort=updated&type=owner", token)
        if not batch:
            break
        repos.extend([r for r in batch if r["name"] not in SKIP_REPOS])
        page += 1
    return repos

def get_pinned(token):
    query = """
    { user(login: "%s") {
        pinnedItems(first: 6, types: REPOSITORY) {
          nodes { ... on Repository { name description url stargazerCount forkCount } }
        }
      }
    }
    """ % USERNAME
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        nodes = r.json().get("data", {}).get("user", {}).get("pinnedItems", {}).get("nodes", [])
        return {n["name"] for n in nodes}
    except Exception as e:
        print(f"⚠️  GraphQL: {str(e)[:50]}")
        return set()

# ── Repo classification ───────────────────────────────────────────────────────
ML_KW = [
    "cancer", "disease", "health", "predict", "classif", "regress", "neural",
    "iris", "titanic", "stock", "segment", "knn", "lstm", "nlp", "sentiment",
    "model", "train", "diabetes", "fraud", "spam", "mnist", "cnn", "rnn",
    "xgboost", "forest", "logistic", "svm", "naive", "cluster", "preprocess"
]

AIAPP_KW = [
    "vebhav", "meetiq", "shipespace", "farmconnect", "kareerpilot",
    "agent", "assistant", "lms", "flyhii", "gpt", "rag", "chatbot",
    "copilot", "recommend", "search", "embed", "llm", "openai"
]

FS_KW = [
    "portfolio", "website", "frontend", "dashboard", "ui", "app",
    "fullstack", "client", "landing", "blog", "service", "server"
]

def classify(repo):
    name = repo["name"].lower()
    desc = (repo.get("description") or "").lower()
    lang = (repo.get("language") or "").lower()
    topics = " ".join(repo.get("topics", [])).lower()
    src = f"{name} {desc} {topics}"

    if any(k in src for k in AIAPP_KW):
        return "ai"
    if any(k in src for k in ML_KW):
        return "ml"
    if any(k in src for k in FS_KW) or lang in ("typescript", "javascript"):
        return "fs"
    if lang == "python":
        return "ml"
    return "other"

# ── Algorithm & domain mapping ────────────────────────────────────────────────
ALGO_MAP = {
    "logistic": "Logistic Regression", "cancer": "Logistic Regression",
    "heart": "Random Forest / SVM", "health": "XGBoost + NLP",
    "mental": "XGBoost + NLP", "iris": "K-Nearest Neighbors",
    "knn": "K-NN", "titanic": "Data Preprocessing", "house": "Linear Regression",
    "stock": "LSTM", "segment": "KMeans", "ckd": "Random Forest",
    "diabetes": "RF", "fraud": "Isolation Forest", "sentiment": "NLP"
}

DOMAIN_MAP = {
    "cancer": "Healthcare", "heart": "Healthcare", "health": "Healthcare",
    "mental": "Healthcare", "iris": "Benchmark", "titanic": "Benchmark",
    "house": "Real Estate", "stock": "Finance", "fraud": "Finance",
    "sentiment": "NLP", "segment": "Business", "farm": "Agriculture"
}

def get_algo(name):
    n = name.lower()
    return next((v for k,v in ALGO_MAP.items() if k in n), "ML")

def get_domain(name):
    n = name.lower()
    return next((v for k,v in DOMAIN_MAP.items() if k in n), "AI/ML")

# ── Markdown builders ─────────────────────────────────────────────────────────
STATS_BASE = "https://github-readme-stats.vercel.app/api"
THEME = "theme=github_dark&hide_border=true&title_color=a78bfa&icon_color=a78bfa&text_color=e2e8f0&bg_color=0d1117"

def pin_card(name):
    url = f"{STATS_BASE}/pin/?username={USERNAME}&repo={name}&{THEME}&cache_seconds=3600"
    return f"[![{name}]({url})](https://github.com/{USERNAME}/{name})"

def repo_grid(repos, cols=2, max_show=6):
    """Generate n-column grid of repo cards."""
    cards = [pin_card(r["name"]) for r in repos[:max_show]]
    rows = []
    for i in range(0, len(cards), cols):
        rows.append(" ".join(cards[i:i+cols]))
    return "\n\n".join(rows)

def ml_table(repos):
    """Professional ML portfolio table."""
    if not repos:
        return "No ML repositories found."
    rows = ["| Repository | Description | Algorithm | Domain | Language |"]
    rows.append("|---|---|---|---|---|")
    for r in repos:
        name = r["name"]
        desc = (r.get("description") or "").split("\n")[0][:50] or name.replace("-", " ").title()
        lang = r.get("language") or "Python"
        stars = r.get("stargazers_count", 0)
        star_badge = f" ⭐{stars}" if stars else ""
        link = f"[{name}](https://github.com/{USERNAME}/{name})"
        rows.append(f"| {link} | {desc} | {get_algo(name)} | {get_domain(name)} | `{lang}`{star_badge} |")
    return "\n".join(rows)

def org_contrib_section():
    """Professional org contributions."""
    rows = ["| Organization | Repository | Language | Commits | Impact |"]
    rows.append("|---|---|---|---|---|")
    for c in ORG_CONTRIBS:
        link = f"[{c['org']}/{c['repo']}](https://github.com/{c['org']}/{c['repo']})"
        rows.append(f"| {c['org']} | {link} | `{c['lang']}` | {c['commits']} | {c['desc']} |")
    return "\n".join(rows)

# ── Main README builder ───────────────────────────────────────────────────────
def build_readme(token):
    print("📊 Fetching GitHub profile…")
    user = get_user(token)

    name = user.get("name") or USERNAME
    bio = user.get("bio") or "Full-Stack Developer & AI/ML Engineer"
    location = user.get("location") or "India"
    public_repos = user.get("public_repos", 0)
    followers = user.get("followers", 0)
    following = user.get("following", 0)
    blog = (user.get("blog") or PORTFOLIO).strip()
    if blog and not blog.startswith("http"):
        blog = "https://" + blog
    blog = blog or PORTFOLIO
    created_at = user.get("created_at", "")[:10]
    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    print("📦 Fetching all repositories…")
    all_repos = get_all_repos(token)
    repos = [r for r in all_repos if not r.get("fork")]

    print(f"📌 Found {len(repos)} repos · fetching pinned…")
    pinned_names = get_pinned(token)

    # Sort repos: pinned first, then by stars
    pinned_repos = [r for r in repos if r["name"] in pinned_names]
    other_repos = sorted(
        [r for r in repos if r["name"] not in pinned_names],
        key=lambda r: r.get("stargazers_count", 0), reverse=True
    )
    sorted_repos = pinned_repos + other_repos

    # Classify
    ai_repos, ml_repos, fs_repos, other = [], [], [], []
    for r in sorted_repos:
        cat = classify(r)
        if cat == "ai":
            ai_repos.append(r)
        elif cat == "ml":
            ml_repos.append(r)
        elif cat == "fs":
            fs_repos.append(r)
        else:
            other.append(r)

    # Statistics
    total_stars = sum(r.get("stargazers_count", 0) for r in sorted_repos)
    total_forks = sum(r.get("forks_count", 0) for r in sorted_repos)

    # Top languages
    lang_count = {}
    for r in sorted_repos:
        l = r.get("language")
        if l:
            lang_count[l] = lang_count.get(l, 0) + 1
    top_langs = sorted(lang_count.items(), key=lambda x: -x[1])[:6]

    print(f"✅ Classified: {len(ai_repos)} AI, {len(ml_repos)} ML, {len(fs_repos)} FS")

    # Build markdown
    readme = f"""\
<div align="center">

<!-- Header Banner -->
<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=220&section=header&text={quote(name)}&fontSize=56&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Full-Stack%20Developer%20%E2%80%A2%20AI%20Builder%20%E2%80%A2%20ML%20Engineer&descSize=18&descAlignY=60&descColor=a78bfa"/>

<!-- Animated intro -->
<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=500&size=20&duration=3500&pause=1200&color=A78BFA&center=true&vCenter=true&width=800&height=50&lines=Building+AI+that+solves+real+problems.;{public_repos}+public+repos.;1%2C488+contributions+in+2026.;Shipping+production+code+daily." alt="Typing SVG"/>

<br/>

<!-- Dynamic badges -->
[![Profile Views](https://komarev.com/ghpvc/?username={USERNAME}&color=7c3aed&style=flat-square&label=profile+views)](https://github.com/{USERNAME})
&nbsp;
[![Followers](https://img.shields.io/github/followers/{USERNAME}?label=followers&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=followers)
&nbsp;
[![Stars](https://img.shields.io/github/stars/{USERNAME}?label=stars&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=repositories)
&nbsp;
[![Email](https://img.shields.io/badge/Email-say%20hello-D14836?style=flat-square&logo=gmail&logoColor=white)](mailto:{EMAIL})

</div>

---

## 👨‍💻 About Me

I'm a full-stack developer and AI/ML engineer based in **{location}** with a passion for building production-grade applications that solve real-world problems. My expertise spans from machine learning model development to cloud-native full-stack systems.

**Currently:** Building AI-powered applications · Contributing to production systems · Mentoring developers

**Philosophy:** *"Learn by shipping. Theory without production is just research."*

---

## 📊 GitHub Profile at a Glance

```yaml
name              : {name}
location          : {location}
portfolio         : {blog}
email             : {EMAIL}

stats:
  public_repos    : {public_repos}
  total_stars     : {total_stars}
  total_forks     : {total_forks}
  followers       : {followers}
  following       : {following}
  member_since    : {created_at}

contributions:
  last_year       : 1,488
  april_2026      : 507 commits across 10 repositories
  new_projects    : 2 (VeBhavAI, MeetIQ)

top_languages   : {', '.join(f'{l} ×{c}' for l,c in top_langs)}
```

---

## 🎯 Current Projects

**Active Development:**
- 🤖 **VeBhav AI** — AI-powered developer assistant (TypeScript)
- 💬 **MeetIQ** — Intelligent meeting platform with AI (Python)
- 📚 **NextGen LMS** — Production learning management system (TypeScript)

---

## 📈 Live GitHub Analytics

<div align="center">

<!-- Stats card: refreshes on page load -->
<img height="180em" src="{STATS_BASE}?username={USERNAME}&show_icons=true&{THEME}&rank_icon=github&cache_seconds=3600"/>

<!-- Language breakdown -->
<img height="180em" src="{STATS_BASE}/top-langs/?username={USERNAME}&layout=compact&langs_count=8&{THEME}&hide=html,css&cache_seconds=3600"/>

</div>

<!-- Contribution streak and activity -->
<div align="center">

<img src="https://streak-stats.demolab.com?user={USERNAME}&theme=dark&hide_border=true&background=0d1117&ring=a78bfa&fire=a78bfa&currStreakLabel=e2e8f0&sideNums=a78bfa&sideLabels=94a3b8" alt="GitHub streak"/>

</div>

<div align="center">

<img src="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&bg_color=0d1117&color=a78bfa&line=7c3aed&point=e2e8f0&area=true&hide_border=true&area_color=7c3aed&radius=6" alt="Contribution graph"/>

</div>

---

## 🚀 Featured Projects

### AI / Full-Stack Applications ({len(ai_repos)})

<div align="center">

{repo_grid(ai_repos + fs_repos, cols=2, max_show=6)}

</div>

---

### Machine Learning & Data Science ({len(ml_repos)})

<div align="center">

{repo_grid(ml_repos, cols=2, max_show=6)}

</div>

{ml_table(ml_repos)}

---

## 🤝 Open Source Contributions

Contributing to production systems across multiple organizations:

{org_contrib_section()}

**Total Org Commits:** {sum(c['commits'] for c in ORG_CONTRIBS)} commits across {len(ORG_CONTRIBS)} repositories

---

## 🛠️ Tech Stack

### Languages & Frameworks
![Python](https://img.shields.io/badge/Python-111827?style=flat-square&logo=python&logoColor=3776AB)
![TypeScript](https://img.shields.io/badge/TypeScript-111827?style=flat-square&logo=typescript&logoColor=3178C6)
![JavaScript](https://img.shields.io/badge/JavaScript-111827?style=flat-square&logo=javascript&logoColor=F7DF1E)
![React](https://img.shields.io/badge/React-111827?style=flat-square&logo=react&logoColor=61DAFB)
![Next.js](https://img.shields.io/badge/Next.js-111827?style=flat-square&logo=next.js&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-111827?style=flat-square&logo=node.js&logoColor=339933)

### AI / ML
![TensorFlow](https://img.shields.io/badge/TensorFlow-111827?style=flat-square&logo=tensorflow&logoColor=FF6F00)
![PyTorch](https://img.shields.io/badge/PyTorch-111827?style=flat-square&logo=pytorch&logoColor=EE4C2C)
![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-111827?style=flat-square&logo=scikit-learn&logoColor=F7931E)
![Pandas](https://img.shields.io/badge/Pandas-111827?style=flat-square&logo=pandas&logoColor=150458)
![NumPy](https://img.shields.io/badge/NumPy-111827?style=flat-square&logo=numpy&logoColor=013243)

### Data & Databases
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-111827?style=flat-square&logo=postgresql&logoColor=316192)
![MongoDB](https://img.shields.io/badge/MongoDB-111827?style=flat-square&logo=mongodb&logoColor=47A248)
![Redis](https://img.shields.io/badge/Redis-111827?style=flat-square&logo=redis&logoColor=DC382D)

### Cloud & DevOps
![AWS](https://img.shields.io/badge/AWS-111827?style=flat-square&logo=amazon-aws&logoColor=FF9900)
![Docker](https://img.shields.io/badge/Docker-111827?style=flat-square&logo=docker&logoColor=2496ED)
![Kubernetes](https://img.shields.io/badge/Kubernetes-111827?style=flat-square&logo=kubernetes&logoColor=326CE5)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-111827?style=flat-square&logo=github-actions&logoColor=2088FF)
![Vercel](https://img.shields.io/badge/Vercel-111827?style=flat-square&logo=vercel&logoColor=white)

---

## 📜 Certifications & Recognition

| Certification | Issuer | Focus |
|---|---|---|
| 🎓 **ML Internship Certificate** | Industry | 6 production ML projects |
| 🏅 **Machine Learning Professional** | IBM | Supervised, Unsupervised, Deep Learning |
| ☁️ **Azure Developer Associate (AZ-204)** | Microsoft | Cloud-native application development |

---

## 🎯 2025 Goals

```
✅ Launch VeBhav AI — public beta
✅ Ship MeetIQ v1 to production  
⚙️  Contribute to 5+ major open-source projects
⚙️  Master Vision Transformers & RLHF
⚙️  AWS Solutions Architect certification
```

---

## 💬 Let's Connect & Collaborate

I'm always interested in discussing AI, ML, full-stack development, and open-source opportunities.

<div align="center">

[![LinkedIn](https://img.shields.io/badge/LinkedIn-{quote(LINKEDIN)}-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/{LINKEDIN})
&nbsp;
[![GitHub](https://img.shields.io/badge/GitHub-{USERNAME}-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/{USERNAME})
&nbsp;
[![Portfolio](https://img.shields.io/badge/Portfolio-Website-7c3aed?style=for-the-badge&logo=vercel&logoColor=white)]({blog})
&nbsp;
[![Email](https://img.shields.io/badge/Email-venuthota009-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:{EMAIL})

</div>

---

## 📝 Stats

- **Total Public Repositories:** {public_repos}
- **Total Stars:** {total_stars}
- **Total Forks:** {total_forks}
- **GitHub Member Since:** {created_at}
- **2026 Contributions:** 1,488
- **Current Streak:** Active developer

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=100&section=footer"/>

*Last updated: {generated_at}*

**[{name}](https://github.com/{USERNAME})** • [Portfolio]({blog}) • [Email](mailto:{EMAIL})

</div>
"""
    return readme


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN required")
        exit(1)

    readme = build_readme(token)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    print("✅ Professional README.md generated successfully!")
