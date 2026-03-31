# DB — OMOP PostgreSQL Setup

**Owner:** Laya Fakher  
**Role:** DB / OMOP Engineer  
**Stack:** PostgreSQL · Synthea · pgAdmin · Java (OpenJDK)

---

## Overview

This document describes the setup of the local database environment for the RWE-Gen project.  
The goal for Day 1 is to generate synthetic data, set up PostgreSQL, create the project database, and verify connectivity.

---

## 1. Synthea Setup and Data Generation

### Clone Synthea

```bash
git clone https://github.com/synthetichealth/synthea.git
cd synthea
````

### Generate Synthetic Patient Data (T2D)

```bash
.\run_synthea.bat -p 1000 --exporter.fhir.export=false --exporter.csv.export=true -m diabetes
```

### Result

* Successfully generated **1000 synthetic patients**
* Output files located in:

```
tools/synthea/output/csv
```

---

## 2. PostgreSQL Setup

### Installation

* PostgreSQL installed locally (Windows)
* pgAdmin 4 used for database management

### Database Creation

Using pgAdmin:

* Created database:

```
omop_rwe
```

### Connection Verification

Executed the following query in pgAdmin:

```sql
SELECT current_database();
```

### Result

* Database connection: SUCCESS
* Query execution: SUCCESS

---

## 3. Test Query (Verification)

To verify database functionality:

```sql
CREATE TABLE test_connection (
    id SERIAL PRIMARY KEY,
    name TEXT
);

INSERT INTO test_connection (name) VALUES ('Laya');

SELECT * FROM test_connection;
```

### Result

* Table created successfully
* Insert successful
* Query returned expected result

---

## 4. OMOP Schema Status

* OMOP CDM schema loading: **NOT started yet**
* Required tables (`person`, `concept`) not yet created
* This will be completed in the next step (Day 2)

---

## 5. T2D Verification Query (Planned)

```sql
SELECT COUNT(*)
FROM condition_occurrence
WHERE condition_concept_id = 201826;
```

Expected result after OMOP loading:

```
> 0 rows
```

---

## 6. Environment Details

| Item            | Value                                       |
| --------------- | ------------------------------------------- |
| OS              | Windows 11                                  |
| Java version    | OpenJDK 17.0.18                             |
| Synthea version | Latest (cloned from GitHub on Mar 31, 2026) |
| PostgreSQL ver. | 18.3                                        |
| Patient count   | 1000                                        |
| T2D row count   | Not yet available                           |

---

## 7. Issues Encountered and Fixes

### Java not recognized

* Issue: `java` command not found
* Fix: Installed OpenJDK (Temurin 17)

### Synthea build failure (Gradle error)

* Issue: `Unsupported class file major version`
* Fix: Corrected Java environment and reran Synthea

### PostgreSQL connection issues (CLI)

* Issue: `connection refused` on localhost:5432
* Fix: Used pgAdmin to connect and manage database successfully

---

## 8. Current Status (End of Day 1)

* Branch created: `feat/laya/db-setup`
* Synthea data generation: COMPLETE
* PostgreSQL setup: COMPLETE
* Database `omop_rwe`: CREATED
* Query execution: VERIFIED
* OMOP schema: NOT YET LOADED

---

## 9. Next Steps (Day 2)

* Load OMOP CDM schema into PostgreSQL
* Create core tables:

  * person
  * concept
  * condition_occurrence
* Begin data integration / mapping
* Run T2D verification query



