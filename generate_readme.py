import requests
import os
from datetime import datetime

USERNAME = "SamppurnaTH"
API = "https://api.github.com"

TOKEN = os.environ.get("GITHUB_TOKEN")

HEADERS = {
    "Accept": "application/vnd.github+json",
}

# Enable topics API
HEADERS["Accept"] = "application/vnd.github.mercy-preview+json"

if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


# ---------------------------
# USER DATA
# ---------------------------
def get_user():
    r = requests.get(f"{API}/users/{USERNAME}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


# ---------------------------
# PINNED REPOS (GraphQL)
# ---------------------------
def get_pinned_repos():
    if not TOKEN:
        return []

    query = """
    {
      user(login: "%s") {
        pinnedItems(first: 6, types: REPOSITORY) {
          nodes {
            ... on Repository {
              name
              description
              stargazerCount
              forkCount
              updatedAt
              primaryLanguage { name }
            }
          }
        }
      }
    }
    """ % USERNAME

    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": query},
        headers=HEADERS
    )

    data = r.json()
    return data["data"]["user"]["pinnedItems"]["nodes"]


# ---------------------------
# REPOSITORIES
# ---------------------------
def get_repos():
    repos = []
    page = 1

    while True:
        r = requests.get(
            f"{API}/users/{USERNAME}/repos",
            params={
                "per_page": 100,
                "page": page,
                "sort": "updated"
            },
            headers=HEADERS
        )

        r.raise_for_status()
        data = r.json()

        if not data:
            break

        repos.extend(data)
        page += 1

    return repos


# ---------------------------
# LANGUAGES
# ---------------------------
def get_languages(repo):
    r = requests.get(repo["languages_url"], headers=HEADERS)
    if r.status_code == 200:
        return list(r.json().keys())
    return []


# ---------------------------
# CLASSIFY REPOS
# ---------------------------
def classify_repo(repo):

    topics = repo.get("topics", [])
    name = repo["name"].lower()
    desc = (repo.get("description") or "").lower()

    combined = " ".join(topics) + name + desc

    ml_keywords = [
        "ml", "ai", "model", "prediction", "regression",
        "classification", "lstm", "nlp", "neural"
    ]

    ai_keywords = [
        "chatbot", "assistant", "rag", "agent",
        "gpt", "bot"
    ]

    if any(k in combined for k in ai_keywords):
        return "ai_apps"

    if any(k in combined for k in ml_keywords):
        return "ml"

    if repo["language"] in ["JavaScript", "TypeScript"]:
        return "fullstack"

    return "other"


# ---------------------------
# BUILD README
# ---------------------------
def build_readme(user, repos, pinned):

    name = user.get("name") or USERNAME
    bio = user.get("bio") or ""
    location = user.get("location") or ""
    blog = user.get("blog") or ""
    followers = user.get("followers")
    following = user.get("following")
    public_repos = user.get("public_repos")

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    ai_apps = []
    ml = []
    fullstack = []
    other = []

    for r in repos:

        if r["fork"]:
            continue

        category = classify_repo(r)

        if category == "ai_apps":
            ai_apps.append(r)

        elif category == "ml":
            ml.append(r)

        elif category == "fullstack":
            fullstack.append(r)

        else:
            other.append(r)

    def repo_card(repo):

        name = repo["name"]

        return f"""
[![{name}](https://github-readme-stats.vercel.app/api/pin/?username={USERNAME}&repo={name}&theme=github_dark&hide_border=true)](https://github.com/{USERNAME}/{name})
"""

    pinned_cards = "\n".join(repo_card({"name": r["name"]}) for r in pinned)

    ai_cards = "\n".join(repo_card(r) for r in ai_apps[:6])
    ml_cards = "\n".join(repo_card(r) for r in ml[:6])
    fs_cards = "\n".join(repo_card(r) for r in fullstack[:6])

    readme = f"""
# {name}

{bio}

📍 {location}

🌐 {blog}

---

## 📊 GitHub Stats

![stats](https://github-readme-stats.vercel.app/api?username={USERNAME}&show_icons=true&theme=github_dark)

![langs](https://github-readme-stats.vercel.app/api/top-langs/?username={USERNAME}&layout=compact&theme=github_dark)

---

## 📌 Pinned Projects

{pinned_cards}

---

## 🤖 AI Applications

{ai_cards}

---

## 🧠 Machine Learning

{ml_cards}

---

## 🌐 Full Stack

{fs_cards}

---

## 📈 Profile

- Public Repos: {public_repos}
- Followers: {followers}
- Following: {following}

---

_Last updated: {updated}_
"""

    return readme


# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":

    user = get_user()
    repos = get_repos()
    pinned = get_pinned_repos()

    readme = build_readme(user, repos, pinned)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"README generated from {len(repos)} repositories")
