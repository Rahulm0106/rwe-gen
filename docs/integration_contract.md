# Integration Contract

**Owner:** Rahul  
**Status:** 🚧 Draft — to be completed Day 2, Sprint 1  
**Last updated:** March 29, 2026

> This document is the **source of truth** for all inter-component JSON shapes.
> Any change to a request or response format must be reflected here first,
> and the affected downstream member notified before the code change is merged.

---

## Endpoint 1 — `POST /generate-protocol`

**Called by:** Frontend (Muktha)  
**Implemented by:** Backend (Prasanna) → LLM Service (Simon)

### Request

```json
{
  "question": "string — the clinical question in natural language"
}
```

### Success Response `200`

```json
{
  "study_type": "cohort_characterization | incidence_analysis",
  "cohort_definition": {
    "condition": "string",
    "drug": "string | null",
    "observation_window": {
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD"
    }
  },
  "comparator": "string | null",
  "outcome": "string",
  "analysis_parameters": {
    "min_prior_obs_days": "integer",
    "washout_period_days": "integer"
  }
}
```

### Error Response `422 / 500`

```json
{
  "error_code": "PROTOCOL_GENERATION_FAILED",
  "message": "string — human-readable description",
  "recoverable": true
}
```

---

## Endpoint 2 — `POST /validate-concepts`

**Called by:** Backend (Prasanna) internally after `/generate-protocol`  
**Implemented by:** Backend (Prasanna) → ATHENA API / local fallback

### Request

```json
{
  "concepts": ["string", "string"]
}
```

### Success Response `200`

```json
{
  "validated": [
    {
      "name": "string",
      "concept_id": "integer",
      "domain": "string",
      "vocabulary": "string",
      "matched": true
    }
  ],
  "unmatched": ["string"]
}
```

### Error Response `500`

```json
{
  "error_code": "CONCEPT_VALIDATION_FAILED",
  "message": "string",
  "recoverable": true
}
```

---

## Endpoint 3 — `POST /execute-query`

**Called by:** Frontend (Muktha) after researcher approves protocol  
**Implemented by:** Backend (Prasanna) → Query Engine (Laya)

### Request

```json
{
  "protocol": { },
  "validated_concepts": [ ]
}
```

> `protocol` shape: same as `/generate-protocol` response  
> `validated_concepts` shape: same as `/validate-concepts` response

### Success Response `200`

```json
{
  "cohort_size": "integer",
  "demographics": {
    "age_groups": {
      "18-30": "integer",
      "31-45": "integer",
      "46-60": "integer",
      "61+":   "integer"
    },
    "sex": {
      "male":   "integer",
      "female": "integer",
      "other":  "integer"
    }
  },
  "incidence_rate": "float | null",
  "incidence_rate_unit": "per 1000 person-years | null",
  "query_time_ms": "integer"
}
```

### Error Response `500`

```json
{
  "error_code": "QUERY_EXECUTION_FAILED",
  "message": "string",
  "recoverable": false
}
```

---

## Constraints & Rules

| Rule | Detail |
|------|--------|
| Date format | Always `YYYY-MM-DD` — no exceptions |
| Null fields | Use JSON `null`, never empty string `""` |
| Concept IDs | Always integers, never strings |
| Error codes | Always `SCREAMING_SNAKE_CASE` |
| `recoverable` | `true` = user can retry; `false` = pipeline must restart |

---

## Change Log

| Date | Changed by | Change |
|------|------------|--------|
| Mar 29, 2026 | Rahul | Initial placeholder created |
