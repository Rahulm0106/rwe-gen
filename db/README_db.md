# DB — OMOP PostgreSQL Setup

**Owner:** Laya  
**Stack:** PostgreSQL 13+ · Synthea · Python

---

## Setup (to be completed by Laya — Sprint 1)

### 1. Generate Synthea data

```bash
# From the Synthea directory
./run_synthea -p 1000 --exporter.fhir.export false --exporter.csv.export true -m diabetes
```

### 2. Load OMOP CDM into PostgreSQL

```bash
# Database name: omop_rwe
psql -U postgres -c "CREATE DATABASE omop_rwe;"
psql -U postgres -d omop_rwe -f db/sql/create_omop_tables.sql
```

### 3. Verify

```bash
psql -U postgres -d omop_rwe -f db/sql/verify_omop.sql
```

---

## Key Files (to be created by Laya)

| File                        | Purpose                                      |
|-----------------------------|----------------------------------------------|
| `sql/create_omop_tables.sql`| OMOP CDM table definitions                   |
| `sql/verify_omop.sql`       | Row counts + T2D concept sanity check        |
| `sql/cohort_characterization.sql` | Parameterised cohort query template   |
| `sql/incidence_analysis.sql`| Parameterised incidence query template       |
| `README_db.md`              | Full setup steps, verified row counts        |

---

## T2D Verification Query

```sql
SELECT COUNT(*)
FROM condition_occurrence
WHERE condition_concept_id = 201826;
-- Expected: > 0 rows
```

---

## Environment

| Item             | Value (to be filled by Laya) |
|------------------|------------------------------|
| OS               | —                            |
| Java version     | —                            |
| Synthea version  | —                            |
| PostgreSQL ver.  | —                            |
| Patient count    | —                            |
| T2D row count    | —                            |
