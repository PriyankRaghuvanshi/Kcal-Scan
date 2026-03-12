# CalorieClick.ai – Resume development here

This repo (**kcal-photo-app** / GitHub: **Kcal-Scan**) is the canonical codebase for **CalorieClick.ai**. Use this workspace for all further development instead of the web or any other copy.

## Current setup

- **Git remote:** `origin` → `git@github.com:PriyankRaghuvanshi/Kcal-Scan.git`
- **App branding:** CalorieClick AI (scheme: `calorieclickai`, bundle: `com.priyank.calorieclick`)
- **API:** `https://kcal-scan-production.up.railway.app`
- **Branch:** `main` (tracking `origin/main`)

## Bringing in CalorieClick.ai code from another source

If you have code changes in another repo (e.g. a separate calorieclick.ai repo or a fork), add it as a remote and merge:

```bash
# Add the other repo as a remote (replace URL with your actual repo)
git remote add calorieclick https://github.com/YOUR_ORG/calorieclick-ai.git

# Fetch its branches
git fetch calorieclick

# List branches to see what to merge, e.g. main or production
git branch -r

# Merge into current branch (example: their main into our main)
git merge calorieclick/main --no-edit
# Or merge a specific branch:
# git merge calorieclick/production --no-edit
```

If the source is a **zip or folder** (not git), copy the files into this repo and then:

```bash
git status
git add .
git commit -m "Merge CalorieClick.ai changes from [source]"
```

## Main app entrypoints

- **Mobile (Expo):** `mobile/App.js` + `mobile/app.json`
- **Backend API:** `backend/` (FastAPI at `backend/app/main.py`)

---

*Resume all CalorieClick.ai work from this repo.*
