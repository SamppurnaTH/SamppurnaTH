#!/usr/bin/env python3
"""
Auto-generates README.md for SamppurnaTH from live GitHub API data.
Run by GitHub Actions on every push + every 6 hours.
"""

import os
import requests
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
USERNAME    = "SamppurnaTH"
LINKEDIN    = "thotavenkatavenu"
PORTFOLIO   = "https://venu-profile.vercel.app"
EMAIL       = "venuthota009@gmail.com"          # update if needed
GITHUB_API  = "https://api.github.com"

# Repos to always skip (forks auto-skipped separately)
SKIP_REPOS  = {USERNAME}                        # skip the profile repo itself

# Known org contributions — kept here because GitHub API only returns
# repos where you are the owner; org contribs won't show otherwise.
ORG_CONTRIBS = [
    {"org": "teamFedWorks",  "repo": "NextGen-Backend",         "commits": 274, "lang": "TypeScript"},
    {"org": "raj3176",       "repo": "nextgen-backend-aws-2026", "commits": 155, "lang": "Python"},
    {"org": "deftia-com",    "repo": "nextgen-lms",             "commits": 22,  "lang": "TypeScript"},
    {"org": "fly-hii",       "repo": "Flyhii-AIAgent",          "commits": 5,   "lang": "Python"},
]

# ── GitHub helpers ─────────────────────────────────────────────────────────────
def gh(path, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.get(f"{GITHUB_API}{path}", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def get_user(token):
    return gh(f"/users/{USERNAME}", token)

def get_all_repos(token):
    repos, page = [], 1
    while True:
        batch = gh(f"/users/{USERNAME}/repos?per_page=100&page={page}&sort=updated&type=owner", token)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos

def get_pinned_names(token):
    """GraphQL call to get pinned repo names."""
    query = """
    { user(login: "%s") {
        pinnedItems(first: 6, types: REPOSITORY) {
          nodes { ... on Repository { name } }
        }
      }
    }
    """ % USERNAME
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    try:
        nodes = r.json()["data"]["user"]["pinnedItems"]["nodes"]
        return {n["name"] for n in nodes}
    except Exception:
        return set()

def get_repo_languages(repo_full_name, token):
    """Returns dict of {lang: bytes} for a repo."""
    try:
        return gh(f"/repos/{repo_full_name}/languages", token)
    except Exception:
        return {}

# ── Repo classification ────────────────────────────────────────────────────────
ML_KW   = ["cancer","disease","health","predict","classif","regress","neural",
            "iris","titanic","stock","segment","knn","lstm","nlp","sentiment",
            "model","train","diabetes","fraud","spam","mnist","cnn","rnn",
            "xgboost","random.forest","logistic","svm","naive","cluster",
            "pre.process","preprocessing","eda","feature","notebook"]

AIAPP_KW= ["vebhav","meetiq","shipespace","farmconnect","kareerpilot",
            "agent","assistant","lms","flyhii","gpt","rag","chatbot","copilot",
            "recommend","search","embed","llm","openai","langchain","vector"]

FS_KW   = ["portfolio","website","frontend","dashboard","ui","app",
            "fullstack","full.stack","client","landing","blog"]

def classify(repo):
    name    = repo["name"].lower()
    desc    = (repo.get("description") or "").lower()
    lang    = (repo.get("language") or "").lower()
    topics  = " ".join(repo.get("topics") or []).lower()
    src     = f"{name} {desc} {topics}"

    if any(k in src for k in AIAPP_KW):  return "ai_app"
    if any(k in src for k in ML_KW):     return "ml"
    if any(k in src for k in FS_KW):     return "fullstack"
    if lang in ("typescript","javascript","dart","kotlin","swift"): return "fullstack"
    if lang in ("python","r","julia","matlab"):                     return "ml"
    return "other"

# ── Algo / domain lookup for ML table ─────────────────────────────────────────
ALGO_MAP = {
    "logistic":    "Logistic Regression",
    "cancer":      "Logistic Regression / SVM",
    "heart":       "Random Forest / SVM / LR",
    "health":      "XGBoost + NLP",
    "mental":      "XGBoost + NLP",
    "iris":        "K-Nearest Neighbors",
    "knn":         "K-Nearest Neighbors",
    "titanic":     "Data Preprocessing Pipeline",
    "pre.process": "Data Preprocessing Pipeline",
    "house":       "Linear / Polynomial Regression",
    "price":       "Regression Models",
    "stock":       "LSTM Neural Network",
    "lstm":        "LSTM Neural Network",
    "segment":     "KMeans Clustering",
    "cluster":     "KMeans Clustering",
    "ckd":         "Random Forest",
    "diabetes":    "Random Forest / SVM",
    "fraud":       "Isolation Forest / XGBoost",
    "spam":        "Naive Bayes / SVM",
    "sentiment":   "NLP / VADER / TextBlob",
}

DOMAIN_MAP = {
    "cancer":"Healthcare","heart":"Healthcare","health":"Healthcare",
    "mental":"Healthcare","ckd":"Healthcare","diabetes":"Healthcare",
    "iris":"Benchmark","titanic":"Benchmark","mnist":"Benchmark",
    "house":"Real Estate","price":"Real Estate",
    "stock":"Finance","fraud":"Finance",
    "spam":"Cybersecurity",
    "sentiment":"NLP","nlp":"NLP",
    "segment":"Business","cluster":"Business",
    "farm":"Agriculture",
}

def algo_for(name):
    n = name.lower()
    return next((v for k,v in ALGO_MAP.items() if k in n), "Python / ML")

def domain_for(name):
    n = name.lower()
    return next((v for k,v in DOMAIN_MAP.items() if k in n), "AI/ML")

# ── Markdown helpers ───────────────────────────────────────────────────────────
STATS_BASE = "https://github-readme-stats.vercel.app/api"
THEME      = "theme=github_dark&hide_border=true&title_color=a78bfa&icon_color=a78bfa&text_color=e2e8f0&bg_color=0d1117"

def pin_card(repo_name, owner=USERNAME):
    url  = f"{STATS_BASE}/pin/?username={owner}&repo={repo_name}&{THEME}&cache_seconds=1800"
    link = f"https://github.com/{owner}/{repo_name}"
    return f"[![{repo_name}]({url})]({link})"

def cards_grid(repos, max_show=6):
    """Two cards per row."""
    items = [pin_card(r["name"]) for r in repos[:max_show]]
    rows  = []
    for i in range(0, len(items), 2):
        rows.append("&nbsp;\n".join(items[i:i+2]))
    return "\n\n".join(rows)

def lang_badge(lang):
    colors = {
        "python":"3776AB","typescript":"3178C6","javascript":"F7DF1E",
        "jupyter notebook":"F37626","r":"276DC3","java":"ED8B00",
        "c++":"00599C","go":"00ADD8","rust":"000000","dart":"0175C2",
    }
    color = colors.get(lang.lower(), "555555")
    slug  = lang.replace(" ", "%20").replace("+", "%2B")
    return f"![{lang}](https://img.shields.io/badge/{slug}-111827?style=flat-square&logo={slug.lower()}&logoColor={color})"

def repo_language_summary(repos, token):
    """Aggregate all languages across repos from API."""
    totals = {}
    for r in repos[:30]:   # cap to avoid rate limit
        langs = get_repo_languages(r["full_name"], token)
        for lang, nbytes in langs.items():
            totals[lang] = totals.get(lang, 0) + nbytes
    total_bytes = sum(totals.values()) or 1
    return {k: round(v/total_bytes*100, 1) for k,v in
            sorted(totals.items(), key=lambda x: -x[1])[:10]}

# ── Main builder ──────────────────────────────────────────────────────────────
def build_readme(token):
    print("Fetching user profile…")
    user = get_user(token)

    name         = user.get("name") or USERNAME
    bio          = user.get("bio") or "Full-Stack Developer & AI/ML Engineer"
    location     = user.get("location") or "India"
    public_repos = user.get("public_repos", 0)
    followers    = user.get("followers", 0)
    following    = user.get("following", 0)
    blog         = (user.get("blog") or PORTFOLIO).strip()
    if blog and not blog.startswith("http"):
        blog = "https://" + blog
    blog = blog or PORTFOLIO
    avatar       = user.get("avatar_url", "")
    created      = user.get("created_at", "")[:10]
    updated_at   = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    print("Fetching repos…")
    all_repos = get_all_repos(token)
    repos     = [r for r in all_repos if not r.get("fork") and r["name"] not in SKIP_REPOS]

    print("Fetching pinned repos…")
    pinned_names = get_pinned_names(token)

    # Sort: pinned first, then by stars desc
    pinned = [r for r in repos if r["name"] in pinned_names]
    rest   = sorted([r for r in repos if r["name"] not in pinned_names],
                    key=lambda r: r.get("stargazers_count", 0), reverse=True)
    repos  = pinned + rest

    # Classify
    ai_repos, ml_repos, fs_repos, other_repos = [], [], [], []
    for r in repos:
        c = classify(r)
        if c == "ai_app":    ai_repos.append(r)
        elif c == "ml":      ml_repos.append(r)
        elif c == "fullstack": fs_repos.append(r)
        else:                other_repos.append(r)

    # Total stars across all repos
    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
    total_forks = sum(r.get("forks_count", 0) for r in repos)

    # Top languages from repo metadata (fast, no extra API calls)
    lang_counter = {}
    for r in repos:
        l = r.get("language")
        if l:
            lang_counter[l] = lang_counter.get(l, 0) + 1
    top_langs = sorted(lang_counter.items(), key=lambda x: -x[1])[:8]
    lang_line = " · ".join(f"`{l}` ×{c}" for l,c in top_langs)

    # Build ML table rows
    def ml_table_rows(rlist):
        rows = []
        for r in rlist:
            desc  = (r.get("description") or r["name"].replace("-"," ").title())[:70]
            stars = r.get("stargazers_count", 0)
            lang  = r.get("language") or "Python"
            link  = f'[{r["name"]}](https://github.com/{USERNAME}/{r["name"]})'
            star_badge = f"⭐ {stars}" if stars else ""
            rows.append(f"| {link} | {desc} | {algo_for(r['name'])} | {domain_for(r['name'])} | `{lang}` {star_badge} |")
        return "\n".join(rows) if rows else "| — | No ML repos found | — | — | — |"

    # Build org contribs table
    def org_table():
        rows = []
        for c in ORG_CONTRIBS:
            link = f'[{c["org"]}/{c["repo"]}](https://github.com/{c["org"]}/{c["repo"]})'
            rows.append(f'| {link} | `{c["lang"]}` | {c["commits"]} commits |')
        return "\n".join(rows)

    # Typing lines — real repo count baked in
    typing_lines = (
        f"Building+AI+that+solves+real+problems.;"
        f"{public_repos}+public+repos+%26+counting.;"
        f"1%2C468%2B+contributions+in+the+last+year.;"
        f"From+RAG+pipelines+to+production+LMS."
    )

    readme = f"""\
<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=220&section=header&text={name.replace(' ','%20')}&fontSize=56&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Full-Stack%20Developer%20%E2%80%A2%20AI%20Builder%20%E2%80%A2%20ML%20Engineer&descSize=18&descAlignY=60&descColor=a78bfa"/>

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=500&size=20&duration=3500&pause=1200&color=A78BFA&center=true&vCenter=true&width=760&height=50&lines={typing_lines}" alt="Typing SVG"/>

<br/>

[![Profile Views](https://komarev.com/ghpvc/?username={USERNAME}&color=7c3aed&style=flat-square&label=profile+views)](https://github.com/{USERNAME})
&nbsp;
[![Followers](https://img.shields.io/github/followers/{USERNAME}?label=followers&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=followers)
&nbsp;
[![Stars](https://img.shields.io/github/stars/{USERNAME}?label=total+stars&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=repositories)
&nbsp;
[![LinkedIn](https://img.shields.io/badge/LinkedIn-connect-7c3aed?style=flat-square&logo=linkedin)](https://linkedin.com/in/{LINKEDIN})
&nbsp;
[![Portfolio](https://img.shields.io/badge/Portfolio-live-7c3aed?style=flat-square&logo=vercel)]({blog})

</div>

---

## `$ whoami`

```yaml
name         : {name}
bio          : {bio}
location     : {location}
github       : https://github.com/{USERNAME}
portfolio    : {blog}
public_repos : {public_repos}
total_stars  : {total_stars}
total_forks  : {total_forks}
followers    : {followers}
following    : {following}
member_since : {created}
top_languages: [{", ".join(l for l,_ in top_langs)}]
readme_sync  : auto-generated by GitHub Actions · {updated_at}
```

---

## 📊 Live GitHub Analytics

<div align="center">

<img height="180em" src="{STATS_BASE}?username={USERNAME}&show_icons=true&{THEME}&rank_icon=github&cache_seconds=1800"/>

<img height="180em" src="{STATS_BASE}/top-langs/?username={USERNAME}&layout=compact&langs_count=8&{THEME}&hide=html,css&cache_seconds=1800"/>

</div>

<div align="center">

<img src="https://streak-stats.demolab.com?user={USERNAME}&theme=dark&hide_border=true&background=0d1117&ring=a78bfa&fire=a78bfa&currStreakLabel=e2e8f0&sideNums=a78bfa&sideLabels=94a3b8&currStreakNum=a78bfa&dates=94a3b8&stroke=0d1117&cache_seconds=1800"/>

</div>

<div align="center">

<img src="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&bg_color=0d1117&color=a78bfa&line=7c3aed&point=e2e8f0&area=true&hide_border=true&area_color=7c3aed&radius=6"/>

</div>

<div align="center">

![Repos](https://img.shields.io/badge/dynamic/json?url=https://api.github.com/users/{USERNAME}&query=$.public_repos&label=public+repos&style=flat-square&color=7c3aed&logo=github)
&nbsp;
![Followers](https://img.shields.io/badge/dynamic/json?url=https://api.github.com/users/{USERNAME}&query=$.followers&label=followers&style=flat-square&color=7c3aed&logo=github)
&nbsp;
![Last Push](https://img.shields.io/github/last-commit/{USERNAME}/{USERNAME}?label=readme+synced&style=flat-square&color=7c3aed)

</div>

---

## 🏗️ AI Apps & Full-Stack Projects

> {len(ai_repos + fs_repos)} projects · auto-detected from repo names, descriptions & topics

<div align="center">

{cards_grid(ai_repos + fs_repos, max_show=6)}

</div>

---

## 🧪 Machine Learning & Data Science

> {len(ml_repos)} ML repos · all classified automatically from repo metadata

<div align="center">

{cards_grid(ml_repos, max_show=6)}

</div>

| Repo | Description | Algorithm | Domain | Lang |
|---|---|---|---|---|
{ml_table_rows(ml_repos)}

---

## 🤝 Open Source Contributions

> Active across multiple production orgs — org commits are tracked separately as GitHub API only exposes owned repos.

| Repository | Language | Commits (Apr 2026) |
|---|---|---|
{org_table()}

---

## ⚙️ Tech Arsenal

**Detected across your repos:** {lang_line}

### AI / Machine Learning
![Python](https://img.shields.io/badge/Python-111827?style=flat-square&logo=python&logoColor=a78bfa)
![TensorFlow](https://img.shields.io/badge/TensorFlow-111827?style=flat-square&logo=tensorflow&logoColor=a78bfa)
![PyTorch](https://img.shields.io/badge/PyTorch-111827?style=flat-square&logo=pytorch&logoColor=a78bfa)
![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-111827?style=flat-square&logo=scikit-learn&logoColor=a78bfa)
![Pandas](https://img.shields.io/badge/Pandas-111827?style=flat-square&logo=pandas&logoColor=a78bfa)
![NumPy](https://img.shields.io/badge/NumPy-111827?style=flat-square&logo=numpy&logoColor=a78bfa)
![XGBoost](https://img.shields.io/badge/XGBoost-111827?style=flat-square&logo=python&logoColor=a78bfa)
![OpenAI](https://img.shields.io/badge/OpenAI-111827?style=flat-square&logo=openai&logoColor=a78bfa)
![HuggingFace](https://img.shields.io/badge/HuggingFace-111827?style=flat-square&logo=huggingface&logoColor=a78bfa)
![LangChain](https://img.shields.io/badge/LangChain-111827?style=flat-square&logo=chainlink&logoColor=a78bfa)

### Full-Stack Development
![TypeScript](https://img.shields.io/badge/TypeScript-111827?style=flat-square&logo=typescript&logoColor=a78bfa)
![JavaScript](https://img.shields.io/badge/JavaScript-111827?style=flat-square&logo=javascript&logoColor=a78bfa)
![React](https://img.shields.io/badge/React-111827?style=flat-square&logo=react&logoColor=a78bfa)
![Next.js](https://img.shields.io/badge/Next.js-111827?style=flat-square&logo=next.js&logoColor=a78bfa)
![Node.js](https://img.shields.io/badge/Node.js-111827?style=flat-square&logo=node.js&logoColor=a78bfa)
![Express](https://img.shields.io/badge/Express-111827?style=flat-square&logo=express&logoColor=a78bfa)
![Tailwind](https://img.shields.io/badge/Tailwind-111827?style=flat-square&logo=tailwind-css&logoColor=a78bfa)
![MongoDB](https://img.shields.io/badge/MongoDB-111827?style=flat-square&logo=mongodb&logoColor=a78bfa)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-111827?style=flat-square&logo=postgresql&logoColor=a78bfa)
![Flask](https://img.shields.io/badge/Flask-111827?style=flat-square&logo=flask&logoColor=a78bfa)
![Socket.io](https://img.shields.io/badge/Socket.io-111827?style=flat-square&logo=socket.io&logoColor=a78bfa)
![Redis](https://img.shields.io/badge/Redis-111827?style=flat-square&logo=redis&logoColor=a78bfa)

### DevOps / Cloud
![Docker](https://img.shields.io/badge/Docker-111827?style=flat-square&logo=docker&logoColor=a78bfa)
![Kubernetes](https://img.shields.io/badge/Kubernetes-111827?style=flat-square&logo=kubernetes&logoColor=a78bfa)
![AWS](https://img.shields.io/badge/AWS-111827?style=flat-square&logo=amazon-aws&logoColor=a78bfa)
![GCP](https://img.shields.io/badge/GCP-111827?style=flat-square&logo=google-cloud&logoColor=a78bfa)
![Azure](https://img.shields.io/badge/Azure-111827?style=flat-square&logo=microsoft-azure&logoColor=a78bfa)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-111827?style=flat-square&logo=github-actions&logoColor=a78bfa)
![Vercel](https://img.shields.io/badge/Vercel-111827?style=flat-square&logo=vercel&logoColor=a78bfa)
![Git](https://img.shields.io/badge/Git-111827?style=flat-square&logo=git&logoColor=a78bfa)

---

## 🐍 Live Contribution Snake

> Redrawn every 12 hours from your real contribution grid.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake.svg">
  <img alt="contribution snake" src="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
</picture>
</div>

---

## 🏅 Certifications

| | Certification | Issuer |
|---|---|---|
| 🎓 | ML Internship — 6 production ML projects | Industry |
| 🏅 | Machine Learning Professional Certificate | IBM |
| ☁️ | Azure Developer Associate (AZ-204) | Microsoft |

---

## 🎯 2025 Roadmap

```
[ ] Launch VeBhav AI — public beta
[ ] Ship MeetIQ v1 to production
[ ] Contribute to 3+ major open-source AI/ML repos
[ ] Master Transformers, GANs & advanced fine-tuning
[ ] AWS Solutions Architect certification
```

---

## 🤝 Let's Build Together

<div align="center">

[![LinkedIn](https://img.shields.io/badge/LinkedIn-{LINKEDIN}-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/{LINKEDIN})
&nbsp;
[![Portfolio](https://img.shields.io/badge/Portfolio-live-7c3aed?style=for-the-badge&logo=vercel&logoColor=white)]({blog})
&nbsp;
[![GitHub](https://img.shields.io/badge/GitHub-{USERNAME}-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/{USERNAME})
&nbsp;
[![Email](https://img.shields.io/badge/Email-say+hello-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:{EMAIL})

</div>

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=120&section=footer"/>

*🤖 This README is fully auto-generated by GitHub Actions · synced {updated_at}*

**[{name}](https://github.com/{USERNAME})**

</div>
"""
    return readme


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("❌  GITHUB_TOKEN env var is required.")

    readme = build_readme(token)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    print("✅  README.md written successfully.")
