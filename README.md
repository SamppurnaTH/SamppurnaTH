import requests
import json
from datetime import datetime

USERNAME = "SamppurnaTH"
GITHUB_API = "https://api.github.com"

def get_user(token=None):
    headers = {"Authorization": f"token {token}"} if token else {}
    r = requests.get(f"{GITHUB_API}/users/{USERNAME}", headers=headers)
    return r.json()

def get_repos(token=None):
    headers = {"Authorization": f"token {token}"} if token else {}
    repos = []
    page = 1
    while True:
        r = requests.get(
            f"{GITHUB_API}/users/{USERNAME}/repos?per_page=100&page={page}&sort=updated",
            headers=headers
        )
        data = r.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def classify_repo(repo):
    name = repo.get("name", "").lower()
    desc = (repo.get("description") or "").lower()
    lang = (repo.get("language") or "").lower()
    topics = repo.get("topics", [])

    ml_keywords = ["cancer", "disease", "health", "prediction", "classification",
                   "regression", "neural", "ml", "ai", "iris", "titanic",
                   "stock", "price", "segmentation", "knn", "lstm", "nlp",
                   "farm", "detect", "sentiment", "model", "train"]
    ai_app_keywords = ["vebhav", "meetiq", "shipespace", "farmconnect",
                       "kareerpilot", "agent", "bot", "assistant", "lms",
                       "nextgen", "flyhii", "chat", "gpt", "rag"]
    fullstack_keywords = ["portfolio", "website", "app", "frontend",
                          "backend", "dashboard", "api", "server"]

    combined = name + " " + desc + " " + " ".join(topics)

    for kw in ai_app_keywords:
        if kw in combined:
            return "ai_apps"
    for kw in ml_keywords:
        if kw in combined:
            return "ml"
    if lang in ["typescript", "javascript"] or any(kw in combined for kw in fullstack_keywords):
        return "fullstack"
    if lang == "python":
        return "ml"
    return "other"

def build_readme(user, repos):
    name = user.get("name") or USERNAME
    bio = user.get("bio") or "Full-Stack Developer & AI/ML Engineer"
    location = user.get("location") or "India"
    public_repos = user.get("public_repos", 0)
    followers = user.get("followers", 0)
    following = user.get("following", 0)
    blog = user.get("blog") or "https://venu-profile.vercel.app"
    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Sort and classify repos
    ai_app_repos, ml_repos, fullstack_repos, other_repos = [], [], [], []
    for r in repos:
        if r.get("fork") or r.get("name") == USERNAME:
            continue
        cat = classify_repo(r)
        if cat == "ai_apps":
            ai_app_repos.append(r)
        elif cat == "ml":
            ml_repos.append(r)
        elif cat == "fullstack":
            fullstack_repos.append(r)
        else:
            other_repos.append(r)

    def pin_card(repo_name, owner=USERNAME):
        return (
            f'[![{repo_name}](https://github-readme-stats.vercel.app/api/pin/'
            f'?username={owner}&repo={repo_name}'
            f'&theme=github_dark&hide_border=true'
            f'&title_color=a78bfa&icon_color=a78bfa'
            f'&text_color=e2e8f0&bg_color=0d1117)]'
            f'(https://github.com/{owner}/{repo_name})'
        )

    def repo_row(repos_list, max_show=6):
        cards = [pin_card(r["name"]) for r in repos_list[:max_show]]
        rows = []
        for i in range(0, len(cards), 2):
            pair = cards[i:i+2]
            rows.append("\n".join(pair))
        return "\n\n".join(rows)

    def ml_table(repos_list):
        rows = []
        algo_map = {
            "cancer": "Logistic Regression / SVM",
            "heart": "Random Forest / SVM / LR",
            "health": "XGBoost + NLP",
            "iris": "K-Nearest Neighbors",
            "titanic": "Data Preprocessing Pipeline",
            "house": "Linear / Polynomial Regression",
            "stock": "LSTM Neural Network",
            "segmentation": "KMeans Clustering",
            "ckd": "Random Forest",
        }
        domain_map = {
            "cancer": "Healthcare", "heart": "Healthcare",
            "health": "Healthcare", "iris": "Benchmark",
            "titanic": "Benchmark", "house": "Real Estate",
            "stock": "Finance", "segmentation": "Business", "ckd": "Healthcare",
        }
        for r in repos_list:
            n = r["name"].lower()
            algo = next((v for k, v in algo_map.items() if k in n), r.get("language") or "Python")
            domain = next((v for k, v in domain_map.items() if k in n), "AI/ML")
            desc = r.get("description") or r["name"].replace("-", " ").title()
            link = f'[{r["name"]}](https://github.com/{USERNAME}/{r["name"]})'
            rows.append(f'| {link} | {desc[:60]} | {algo} | {domain} |')
        return "\n".join(rows)

    readme = f"""<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=220&section=header&text={name.replace(' ', '%20')}&fontSize=56&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Full-Stack%20Developer%20%E2%80%A2%20AI%20Builder%20%E2%80%A2%20ML%20Engineer&descSize=18&descAlignY=60&descColor=a78bfa"/>

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=500&size=20&duration=3500&pause=1200&color=A78BFA&center=true&vCenter=true&width=700&height=50&lines=Building+AI+that+solves+real+problems.;{public_repos}+public+repos+%26+counting.;Learning+by+shipping+in+production." alt="Typing SVG"/>

<br/>

[![Profile Views](https://komarev.com/ghpvc/?username={USERNAME}&color=7c3aed&style=flat-square&label=profile+views)](https://github.com/{USERNAME})
&nbsp;
[![Followers](https://img.shields.io/github/followers/{USERNAME}?label=followers&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=followers)
&nbsp;
[![Stars](https://img.shields.io/github/stars/{USERNAME}?label=total+stars&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=repositories)
&nbsp;
[![LinkedIn](https://img.shields.io/badge/LinkedIn-connect-7c3aed?style=flat-square&logo=linkedin)](https://linkedin.com/in/thotavenkatavenu)
&nbsp;
[![Portfolio](https://img.shields.io/badge/Portfolio-live-7c3aed?style=flat-square&logo=vercel)]({blog if blog.startswith("http") else "https://venu-profile.vercel.app"})

</div>

---

## `$ whoami`

```yaml
name        : {name}
bio         : {bio}
location    : {location}
public_repos: {public_repos}
followers   : {followers}
following   : {following}
portfolio   : {blog if blog else "https://venu-profile.vercel.app"}
readme_auto : "This README is auto-generated by GitHub Actions on every push"
```

---

## 📊 Live GitHub Analytics

<div align="center">

<img height="180em" src="https://github-readme-stats.vercel.app/api?username={USERNAME}&show_icons=true&theme=github_dark&count_private=true&hide_border=true&title_color=a78bfa&icon_color=a78bfa&text_color=e2e8f0&bg_color=0d1117&rank_icon=github&cache_seconds=1800"/>

<img height="180em" src="https://github-readme-stats.vercel.app/api/top-langs/?username={USERNAME}&layout=compact&langs_count=8&theme=github_dark&hide_border=true&title_color=a78bfa&text_color=e2e8f0&bg_color=0d1117&hide=html,css&cache_seconds=1800"/>

</div>

<div align="center">

<img src="https://streak-stats.demolab.com?user={USERNAME}&theme=dark&hide_border=true&background=0d1117&ring=a78bfa&fire=a78bfa&currStreakLabel=e2e8f0&sideNums=a78bfa&sideLabels=94a3b8&currStreakNum=a78bfa&dates=94a3b8&stroke=0d1117&cache_seconds=1800"/>

</div>

<div align="center">

<img src="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&bg_color=0d1117&color=a78bfa&line=7c3aed&point=e2e8f0&area=true&hide_border=true&area_color=7c3aed&radius=6"/>

</div>

<div align="center">

![Public Repos](https://img.shields.io/badge/dynamic/json?url=https://api.github.com/users/{USERNAME}&query=$.public_repos&label=public+repos&style=flat-square&color=7c3aed&logo=github)
&nbsp;
![Last Updated](https://img.shields.io/github/last-commit/{USERNAME}/{USERNAME}?label=readme+updated&style=flat-square&color=7c3aed)

</div>

---

## 🏗️ AI / Full-Stack Apps

<div align="center">

{repo_row(ai_app_repos + fullstack_repos)}

</div>

---

## 🧪 ML / Data Science

<div align="center">

{repo_row(ml_repos)}

</div>

### ML Portfolio

| Repo | Description | Algorithm | Domain |
|---|---|---|---|
{ml_table(ml_repos)}

---

## ⚙️ Tech Arsenal

### AI / Machine Learning
![Python](https://img.shields.io/badge/Python-111827?style=flat-square&logo=python&logoColor=a78bfa)
![TensorFlow](https://img.shields.io/badge/TensorFlow-111827?style=flat-square&logo=tensorflow&logoColor=a78bfa)
![PyTorch](https://img.shields.io/badge/PyTorch-111827?style=flat-square&logo=pytorch&logoColor=a78bfa)
![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-111827?style=flat-square&logo=scikit-learn&logoColor=a78bfa)
![Pandas](https://img.shields.io/badge/Pandas-111827?style=flat-square&logo=pandas&logoColor=a78bfa)
![NumPy](https://img.shields.io/badge/NumPy-111827?style=flat-square&logo=numpy&logoColor=a78bfa)
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

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake.svg">
  <img alt="GitHub contribution grid snake animation" src="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
</picture>
</div>

---

## 🏅 Certifications

| | Certification | Issuer |
|---|---|---|
| 🎓 | ML Internship — 6 production projects | Industry |
| 🏅 | Machine Learning Professional Certificate | IBM |
| ☁️ | Azure Developer Associate (AZ-204) | Microsoft |

---

## 🤝 Let's Build Together

<div align="center">

[![LinkedIn](https://img.shields.io/badge/LinkedIn-thotavenkatavenu-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/thotavenkatavenu)
&nbsp;
[![Portfolio](https://img.shields.io/badge/Portfolio-live-7c3aed?style=for-the-badge&logo=vercel&logoColor=white)]({blog if blog.startswith("http") else "https://venu-profile.vercel.app"})
&nbsp;
[![GitHub](https://img.shields.io/badge/GitHub-{USERNAME}-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/{USERNAME})

</div>

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=120&section=footer"/>

*Auto-generated by GitHub Actions · Last run: {updated}*

**[Venu Thota](https://github.com/{USERNAME})**

</div>
"""
    return readme

if __name__ == "__main__":
    import os
    token = os.environ.get("GITHUB_TOKEN")
    user = get_user(token)
    repos = get_repos(token)
    readme = build_readme(user, repos)
    with open("README.md", "w") as f:
        f.write(readme)
    print(f"README.md generated with {len(repos)} repos.")
