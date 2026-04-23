# Integration Contract

**Owner:** Rahul (QA / Integration Lead)

**Status:** 🚧 Placeholder — JSON shapes to be filled on Day 2 once Prasanna's Pydantic models are reviewed

**Last updated:** March 29, 2026

---

## What this document is

This is the **single source of truth** for how every component in RWE-Gen talks to every other component.

It defines exactly:
- What JSON the **frontend sends** to each endpoint
- What JSON the **backend returns** on success
- What JSON the **backend returns** on failure

### The golden rule
> If Muktha's frontend code and Prasanna's backend code disagree on a field name, type, or structure — **this document is the referee, not either person's code.**
> Any change to an endpoint shape must be a PR to this document first. The affected member must be notified and approve before the code changes.

---

## Change Log

| Date | Changed by | What changed |
|------|------------|--------------|
| Mar 29, 2026 | Rahul | Initial placeholder created — structure and rules defined |
| _Day 2_ | Rahul + Prasanna | JSON shapes filled in from Pydantic models |

---

## Endpoint 1 — `POST /generate-protocol`

**Who calls it:** Muktha (Frontend)
**Who implements it:** Prasanna (Backend) → calls Simon (LLM Service)
**Purpose:** Takes a plain-English clinical question, returns a structured study protocol

### Request body

```json
{
  "question": "string"
}
```

**Field notes:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `question` | string | ✅ | The researcher's clinical question in plain English |

### Success response — HTTP 200

> ⏳ To be filled on Day 2 once Prasanna's Pydantic `StudyProtocol` model is reviewed.
> Shape will be derived directly from `/docs/protocol_schema.json`.

```json
{
  "_placeholder": "Prasanna to confirm field names and types by end of Day 2"
}
```

**Expected top-level fields (from protocol_schema.json — pending confirmation):**
- `study_type`
- `cohort_definition` (nested object)
- `comparator`
- `outcome`
- `analysis_parameters` (nested object)

### Error response — HTTP 422 / 500

> ⏳ To be filled on Day 2.

```json
{
  "_placeholder": "error shape to be confirmed"
}
```

---

## Endpoint 2 — `POST /validate-concepts`

**Who calls it:** Prasanna (Backend — called internally after /generate-protocol)
**Who implements it:** Prasanna (Backend) → calls ATHENA API or local fallback
**Purpose:** Takes concept names from the protocol, returns OMOP concept IDs

### Request body

```json
{
  "concepts": ["string", "string"]
}
```

**Field notes:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `concepts` | array of strings | ✅ | Concept names extracted from the protocol (e.g. "Type 2 Diabetes") |

### Success response — HTTP 200

> ⏳ To be filled on Day 2 once Prasanna's Pydantic `ConceptValidationResponse` model is reviewed.

```json
{
  "_placeholder": "Prasanna to confirm field names and types by end of Day 2"
}
```

**Expected fields (pending confirmation):**
- `validated` — array of matched concepts with their OMOP concept IDs
- `unmatched` — array of concept names that could not be resolved

### Error response — HTTP 500

> ⏳ To be filled on Day 2.

```json
{
  "_placeholder": "error shape to be confirmed"
}
```

---

## Endpoint 3 — `POST /execute-query`

**Who calls it:** Muktha (Frontend — after researcher approves the protocol)
**Who implements it:** Prasanna (Backend) → calls Laya (Query Engine)
**Purpose:** Runs the validated protocol as a cohort query against OMOP PostgreSQL, returns structured results

### Request body

> ⏳ To be filled on Day 2. Will contain the approved protocol and validated concept IDs.

```json
{
  "_placeholder": "shape depends on /generate-protocol and /validate-concepts responses — to be confirmed Day 2"
}
```

**Expected fields (pending confirmation):**
- `protocol` — the approved StudyProtocol object
- `validated_concepts` — the output of /validate-concepts

### Success response — HTTP 200

> ⏳ To be filled on Day 2 once Prasanna's `QueryResultsResponse` model is reviewed.

```json
{
  "_placeholder": "Prasanna to confirm field names and types by end of Day 2"
}
```

**Expected fields (pending confirmation):**
- `cohort_size` — integer
- `demographics` — nested object (age groups, sex breakdown)
- `incidence_rate` — float or null
- `incidence_rate_unit` — string or null
- `query_time_ms` — integer

### Error response — HTTP 500

> ⏳ To be filled on Day 2.

```json
{
  "_placeholder": "error shape to be confirmed"
}
```

---

## Shared rules (agreed now — not placeholders)

These rules apply to all endpoints and are already locked in:

| Rule | Value |
|------|-------|
| Date format | Always `YYYY-MM-DD` — no exceptions |
| Null fields | Always JSON `null` — never empty string `""` |
| Concept IDs | Always integers — never strings |
| Error codes | Always `SCREAMING_SNAKE_CASE` (e.g. `PROTOCOL_GENERATION_FAILED`) |
| `recoverable` flag | `true` = user can retry the same action; `false` = pipeline must restart from question input |
| Content-Type | Always `application/json` on both request and response |
| Base URL (local dev) | `http://localhost:8000` |

---

## Review sign-off (Day 2)

All five members must leave an explicit approval on the PR that fills in the placeholder sections.

| Name | Role | Approved? |
|------|------|-----------|
| Rahul | QA / Integration Lead | — |
| Simon | LLM / AI Engineer | — |
| Laya | DB / OMOP Engineer | — |
| Prasanna | Backend Engineer | — |
| Muktha | Frontend Engineer | — |
