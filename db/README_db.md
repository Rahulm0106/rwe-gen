**Owner:** Laya Fakher (DB/Synthea)  
**Consumer:** Prasanna Pravin Renapurkar (Backend)  
**Verified by:** Rahul Sanjay Mandviya (QA)

---

## What this folder contains

| File | Purpose | Sprint |
|------|---------|--------|
| `rwegen_etl_setup.sql` | Full ETL — creates all OMOP tables and loads Synthea data. Run once. | Sprint 1 |
| `sprint1_verification.sql` | QA verification script — Rahul runs this to sign off Sprint 1. | Sprint 1 |
| `sprint2_sql_templates.sql` | 4 parameterized SQL templates for Prasanna's `/execute-query` endpoint. | Sprint 2 |
| `synthea/` | Drop your Synthea CSV output here before running the ETL. Not committed to git. | — |

---

## Sprint 2 SQL Templates

File: `sprint2_sql_templates.sql`

These 4 templates are consumed by Prasanna's `/execute-query` FastAPI endpoint.
Prasanna replaces `{placeholders}` with validated concept IDs from Simon's ATHENA module.

| Template | Study Type | Parameters | Validated Result |
|----------|-----------|------------|-----------------|
| Template 1 — Demographics | Characterization | `{condition_concept_id}`, `{drug_concept_id}` | cohort_size=1662, mean_age=81.4 |
| Template 2 — Lab Aggregation | Lab Value Summary | `{condition_concept_id}`, `{measurement_concept_id}` | HbA1c: 154k readings, mean=3.77 |
| Template 3 — Incidence Rate | Incidence | `{condition_concept_id}`, `{obs_start_date}`, `{obs_end_date}` | 4.6006 per 1,000 person-years |
| Template 4 — Dialysis / CKD | Procedure Outcome | none (hardcoded CKD concept) | ckd_cohort=1137, dialysis=0 (TC-08 ✓) |

### Key concept IDs for Prasanna (parameter reference)

#### Conditions (`condition_concept_id`)
| Disease | concept_id |
|---------|-----------|
| Type 2 Diabetes | 201826 |
| Obesity | 433736 |
| Hypertension | 316866 |
| Chronic Kidney Disease | 46271022 |

#### Labs (`measurement_concept_id`)
| Lab | concept_id |
|-----|-----------|
| HbA1c | 3004410 |
| BMI | 3038553 |
| Systolic BP | 3004249 |
| Diastolic BP | 3012888 |
| eGFR | 3049187 |
| Serum Creatinine | 3016723 |
| LDL Cholesterol | 3007070 |

#### Drugs (`drug_concept_id`)
| Drug | concept_id |
|------|-----------|
| Metformin | 1503297 |
| Lisinopril | 1308216 |
| Amlodipine | 1332418 |
| Atorvastatin | 1545958 |
| Insulin | 1516766 |

### PostgreSQL compatibility notes (important for Prasanna)

Two fixes were required for PostgreSQL 18 — do not revert these:

1. `AVG(DATE_PART(...))` requires `::numeric` cast before `ROUND()`:
   ```sql
   ROUND(AVG(DATE_PART('year', AGE(p.birth_datetime)))::numeric, 1)
   ```

2. Date subtraction for person-years uses `(date - date)::numeric / 365.25`
   instead of `EXTRACT(EPOCH FROM interval)` which fails in PostgreSQL 18:
   ```sql
   SUM((cohort.window_end - cohort.window_start)::numeric / 365.25)
   ```

### Sprint 2 test case results

| Test Case | Description | Status |
|-----------|-------------|--------|
| TC-01 | Demographics cohort non-zero | ✅ PASS |
| TC-02 | HbA1c readings non-zero | ✅ PASS |
| TC-03 | Incidence query can run | ✅ PASS |
| TC-08 | Empty cohort returns 0 cleanly, not null | ✅ PASS |
| TC-04 | GROQ retry logic — Simon's responsibility | — |

---

## Prerequisites

- Docker + docker-compose running (Prasanna sets this up)
- PostgreSQL container up and database `rwegen` created
- Synthea CSVs generated and placed in `db/synthea/`

If you haven't generated Synthea data yet, see **Generating Synthea Data** below.

---

## Step 1 — Generate Synthea data (Laya)

Run Synthea with all 4 required disease modules:

```bash
java -jar synthea-with-dependencies.jar \
  -p 10000 \
  --exporter.csv.export true \
  -m diabetes,metabolic_syndrome_disease,hypertension,chronic_kidney_disease \
  Massachusetts
```

Copy the output CSVs into `db/synthea/`:

```
db/synthea/
├── patients.csv
├── encounters.csv
├── conditions.csv
├── medications.csv
└── observations.csv
```

These files are not committed to git (too large). They stay local.

---

## Step 2 — Start the database (Prasanna)

```bash
docker-compose up -d db
```

Wait for the container to be healthy, then create the database:

```bash
docker exec -it rwegen_db psql -U postgres -c "CREATE DATABASE rwegen;"
```

---

## Step 3 — Copy CSVs into the container (Laya or Prasanna)

```bash
docker cp db/synthea/. rwegen_db:/tmp/synthea/
```

Verify files are there:

```bash
docker exec -it rwegen_db ls /tmp/synthea/
# Should show: patients.csv encounters.csv conditions.csv medications.csv observations.csv
```

---

## Step 4 — Run the ETL (Laya)

```bash
docker exec -it rwegen_db psql -U postgres -d rwegen -f /tmp/rwegen_etl_setup.sql
```

Or copy the script in first if it's not already mounted:

```bash
docker cp db/rwegen_etl_setup.sql rwegen_db:/tmp/rwegen_etl_setup.sql
docker exec -it rwegen_db psql -U postgres -d rwegen -f /tmp/rwegen_etl_setup.sql
```

The script prints row counts at the end of each section. Expected final output:

```
person                ~10,000 rows
visit_occurrence      ~500,000+ rows
condition_occurrence  ~420,000+ rows
drug_exposure         ~600,000+ rows
measurement           ~5,700,000+ rows
observation           ~several million rows
observation_period    ~10,000 rows
```

---

## Step 5 — Verify (Rahul)

```bash
docker cp db/sprint1_verification.sql rwegen_db:/tmp/sprint1_verification.sql
docker exec -it rwegen_db psql -U postgres -d rwegen -f /tmp/sprint1_verification.sql
```

All 11 gates in Section 11 must show **PASS** before Sprint 2 begins.  
Screenshot Section 11 output and post to the team channel.

---

## Connection details for Prasanna (FastAPI / psycopg2)

```
host:     localhost  (or 'db' inside docker network)
port:     5432
database: rwegen
user:     postgres
password: set in docker-compose.yml / .env
```

psycopg2 connection string:
```
postgresql://postgres:<password>@db:5432/rwegen
```

---

## OMOP Tables loaded

| Table | Status | Used for |
|-------|--------|----------|
| `person` | Core | Demographics on every result screen |
| `visit_occurrence` | Core | Hospitalization filters |
| `condition_occurrence` | Core | All cohort definitions |
| `drug_exposure` | Core | Drug filters (metformin, ACE inhibitors) |
| `observation_period` | Core | Observation window for incidence queries |
| `measurement` | Full | HbA1c, BMI, BP, eGFR, Creatinine, LDL |
| `observation` | Limited | Smoking status only |
| `concept` | Placeholder | Loaded separately by Simon (ATHENA) |

`death` table is **out of scope** for MVP.

---

## Re-running the ETL

The ETL script is fully idempotent — it drops and recreates everything.  
Safe to re-run at any time:

```bash
docker exec -it rwegen_db psql -U postgres -d rwegen -f /tmp/rwegen_etl_setup.sql
```

---