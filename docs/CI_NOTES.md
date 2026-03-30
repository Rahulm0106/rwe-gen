# CI Pipeline Notes

**Owner:** Rahul  
**Platform:** GitHub Actions

---

## Pipeline Overview

Triggers on every Pull Request to `main`.

| Step | Tool | What it checks |
|------|------|----------------|
| Python lint | `flake8` or `ruff` | Backend code style |
| Backend smoke test | `pytest` + `httpx` | All 3 endpoints return 200 |
| Node lint | `eslint` | Frontend code style |

---

## Known Issues

_None yet — to be updated as issues are discovered._

---

## Change Log

| Date | Change |
|------|--------|
| Mar 29, 2026 | File created |
