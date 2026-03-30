# RWE-Gen — AI-Powered Real-World Evidence Generator

> CS595 · Spring 2026 · Trauma Team

RWE-Gen is an AI-assisted research pipeline that transforms plain-English clinical questions
into structured observational analyses using OMOP clinical data.

---

## Team

| Name     | Role                  | Area                        |
|----------|-----------------------|-----------------------------|
| Rahul    | QA / Integration Lead | CI, testing, contracts      |
| Simon    | LLM / AI Engineer     | Protocol generation, prompts|
| Laya     | DB / OMOP Engineer    | PostgreSQL, Synthea, SQL    |
| Prasanna | Backend Engineer      | FastAPI, API endpoints      |
| Muktha   | Frontend Engineer     | React UI, screens           |

---

## Project Structure

```
rwe-gen/
├── backend/      # FastAPI application (Prasanna)
├── frontend/     # React application (Muktha)
├── llm/          # LLM scripts and prompt engineering (Simon)
├── db/           # SQL templates, OMOP setup scripts (Laya)
│   └── sql/
├── docs/         # Integration contract, schema, meeting notes (Rahul)
└── README.md
```

---

## Local Setup

> Full setup instructions will be added by each team member in their respective folders.
> See `/backend/README_backend.md`, `/db/README_db.md`, etc.

### Prerequisites (to be confirmed per role)

- Python 3.10+
- Node.js 18+
- PostgreSQL 13+
- Java 11+ (for Synthea)

---

## Branch Naming Convention

```
feat/<your-name>/<short-description>
```

**Examples:**
- `feat/rahul/ci-setup`
- `feat/simon/protocol-schema`
- `feat/laya/db-setup`
- `feat/prasanna/fastapi-scaffold`
- `feat/muktha/react-scaffold`

---

## PR Process

1. Create your branch from `main` using the naming convention above
2. Push your changes and open a Pull Request to `main`
3. Tag at least **one** teammate as a reviewer
4. Address any review comments before merging
5. **No direct pushes to `main`** — all changes go through PRs

---

## Sprint Timeline

| Sprint | Dates           | Goal                            |
|--------|-----------------|---------------------------------|
| 1      | Mar 29 – Apr 4  | Foundation & Contracts          |
| 2      | Apr 5  – Apr 11 | Core Services Live              |
| 3      | Apr 12 – Apr 18 | End-to-End Pipeline             |
| 4      | Apr 19 – Apr 25 | Polish, Stabilise & Demo        |

---

## Key Documents

- [`/docs/integration_contract.md`](docs/integration_contract.md) — API request/response shapes (source of truth)
- [`/docs/protocol_schema.json`](docs/protocol_schema.json) — Fixed JSON study protocol schema
- [`/docs/CI_NOTES.md`](docs/CI_NOTES.md) — CI pipeline notes and known issues
