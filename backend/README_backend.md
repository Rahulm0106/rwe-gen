# Backend — FastAPI Application

**Owner:** Prasanna  
**Stack:** Python · FastAPI · Uvicorn · Pydantic

---

## Setup (to be completed by Prasanna — Sprint 1)

```bash
cd backend/
pip install -r requirements.txt
uvicorn main:app --reload
```

API docs available at: `http://localhost:8000/docs`

---

## Endpoints

| Method | Path                  | Description                        |
|--------|-----------------------|------------------------------------|
| POST   | `/generate-protocol`  | Generate structured study protocol |
| POST   | `/validate-concepts`  | Validate OMOP concept IDs          |
| POST   | `/execute-query`      | Execute cohort query on OMOP DB    |

> Full request/response shapes: see `/docs/integration_contract.md`
