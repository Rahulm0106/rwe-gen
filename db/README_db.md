# DB — OMOP PostgreSQL Setup

**Owner:** Laya Fakher  
**Role:** DB / OMOP Engineer  
**Stack:** PostgreSQL · pgAdmin 4 · Synthea · Java (OpenJDK)

---

## Overview

This document describes the database setup and initial data-loading workflow completed for Sprint 1 of the RWE-Gen project.

The purpose of this setup is to:

- generate synthetic healthcare data using Synthea,
- configure a local PostgreSQL database,
- create OMOP-like core tables needed for the project MVP,
- load selected Synthea CSV data into these tables,
- and verify that Type 2 Diabetes records are present and queryable.

---

## 1. Git Branch

The database setup work was completed on the following branch:

```text
feat/laya/db-setup
````

---

## 2. Synthea Setup and Data Generation

### Clone Synthea

```bash
git clone https://github.com/synthetichealth/synthea.git
cd synthea
```

### Java Verification

Java was required before running Synthea.

```bash
java -version
```

Installed version used:

```text
OpenJDK 17.0.18
```

### Initial Attempt

The first Synthea run used:

```bash
.\run_synthea.bat -p 1000 --exporter.fhir.export=false --exporter.csv.export=true -m diabetes
```

This completed successfully, but the resulting CSV export did not include all required files such as `conditions.csv` and `medications.csv`.

### Final Successful Data Generation

The corrected run used:

```bash
.\run_synthea.bat -p 1000 --exporter.csv.export=true
```

### Result

* Successfully generated **1000 synthetic patients**
* Output files stored in:

```text
D:\IIT\Health Informatics\Project\tools\synthea\output\csv
```

### Key CSV Files Used

* `patients.csv`
* `encounters.csv`
* `conditions.csv`
* `medications.csv`
* `observations.csv`

---

## 3. PostgreSQL Setup

### Installation

* PostgreSQL installed locally on Windows
* pgAdmin 4 used for database creation and query execution

### PostgreSQL Version

```text
PostgreSQL 18.3
```

### Database Creation

Created database:

```text
omop_rwe
```

### Connection Verification

Executed in pgAdmin:

```sql
SELECT current_database();
```

### Result

* Database connection: SUCCESS
* Query execution: SUCCESS

---

## 4. Initial Test Query

To confirm the database was working correctly, the following temporary test table was created:

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

This table remains in the database as a basic connection test artifact.

---

## 5. OMOP-Like Schema Creation

A minimal OMOP-like schema was created for Sprint 1 to support core project functionality.

### Tables Created

* `person`
* `concept`
* `visit_occurrence`
* `condition_occurrence`
* `drug_exposure`
* `observation`
* `measurement`

### Notes

This is not yet a full official OMOP CDM implementation.
Instead, it is a simplified schema sufficient for Sprint 1 goals:

* local database setup,
* structured healthcare data loading,
* verification queries for T2D cohort support.

The `concept` table was created successfully but has not yet been fully populated with official OMOP vocabulary content. Full vocabulary loading is deferred to later work beyond Sprint 1.

---

## 6. Staging Tables and Data Loading

To load Synthea CSV files safely, staging tables were created first:

* `staging_patients`
* `staging_encounters`
* `staging_conditions`
* `staging_medications`
* `staging_observations`

CSV files were imported into these staging tables through pgAdmin.

### Data Mapping Workflow

The following mapping process was used:

* `patients.csv` → `staging_patients` → `person`
* `encounters.csv` → `staging_encounters` → `visit_occurrence`
* `conditions.csv` → `staging_conditions` → `condition_occurrence`
* `medications.csv` → `staging_medications` → `drug_exposure`
* `observations.csv` → `staging_observations` → `measurement` / `observation`

### Mapping Support Tables

Additional mapping tables used:

* `patient_map`
* `encounter_map`

These mapping tables were needed because:

* Synthea IDs are UUID-style string identifiers,
* while the local OMOP-like schema uses numeric IDs for keys.

### Observation and Measurement Mapping Logic

Since `observations.csv` contains mixed-value data, the following simplified mapping was used:

* rows with numeric `value` fields were inserted into `measurement`
* rows with non-numeric `value` fields were inserted into `observation`

This approach is sufficient for Sprint 1 verification and keeps the data usable for later cohort analysis work.

---

## 7. T2D Verification and Mapping Logic

### Initial Problem

The first T2D verification query returned `0` rows because the initial mapping logic assumed ICD-10 codes such as `E11`.

However, the Synthea `conditions.csv` file used **SNOMED-coded diagnoses**, for example:

* `44054006` → `Diabetes mellitus type 2 (disorder)`

### Fix Applied

The `condition_occurrence` loading logic was updated to map Type 2 Diabetes using the `description` field instead of relying on ICD-10-style codes.

Conditions matching descriptions such as:

* `diabetes mellitus type 2`
* `due to type 2 diabetes`

were mapped to:

```text
condition_concept_id = 201826
```

### Final T2D Verification Query

```sql
SELECT COUNT(*)
FROM condition_occurrence
WHERE condition_concept_id = 201826;
```

### Final Result

```text
268
```

This confirms that Type 2 Diabetes rows are present and queryable in the loaded data.

---

## 8. Current Verification Summary

### Final Core Table Counts

| Table                | Row Count |
| -------------------- | --------: |
| person               |      1152 |
| concept              |         0 |
| visit_occurrence     |     67553 |
| condition_occurrence |     42130 |
| drug_exposure        |     56342 |
| observation          |    327835 |
| measurement          |    550931 |

### Condition Concept Breakdown

```sql
SELECT condition_concept_id, COUNT(*)
FROM condition_occurrence
GROUP BY condition_concept_id;
```

### Current Result

* `201826` → `268`
* `0` → `41862`

This is acceptable for Sprint 1 because the required T2D mapping works and returns a non-zero result.

---

## 9. Environment Details

| Item                    | Value                                    |
| ----------------------- | ---------------------------------------- |
| OS                      | Windows 11                               |
| Java version            | OpenJDK 17.0.18                          |
| Synthea version         | Latest clone from GitHub on Mar 31, 2026 |
| PostgreSQL version      | 18.3                                     |
| Database name           | omop_rwe                                 |
| Patient count generated | 1000                                     |
| Final T2D row count     | 268                                      |

---

## 10. Issues Encountered and Fixes

### 1. Java not recognized

* **Issue:** `java` command was not found
* **Fix:** Installed Temurin OpenJDK 17

### 2. Synthea Gradle error

* **Issue:** `Unsupported class file major version`
* **Fix:** Corrected Java environment and reran after clearing Gradle state

### 3. PostgreSQL CLI connection issues

* **Issue:** `psql` connection failed on localhost
* **Fix:** Switched to pgAdmin for successful database management

### 4. Missing `conditions.csv` in first Synthea run

* **Issue:** Initial diabetes-module-only run did not produce all needed CSV files
* **Fix:** Reran Synthea without `-m diabetes` using full CSV export

### 5. T2D mapping returned zero initially

* **Issue:** Initial mapping assumed ICD-10-like `E11` codes
* **Fix:** Updated mapping logic to use SNOMED-based descriptions from `conditions.csv`

### 6. Observation and measurement tables were initially empty

* **Issue:** `observation` and `measurement` had zero rows because `observations.csv` had not yet been imported into a staging table
* **Fix:** Created `staging_observations`, imported `observations.csv`, then mapped numeric values into `measurement` and non-numeric values into `observation`

### 7. Mapping column name mismatch during observation loading

* **Issue:** Initial insert query used a non-existent column name `patient_uuid`
* **Fix:** Corrected the join to use the actual mapping column `synthea_patient_id`

---

## 11. Current Sprint 1 Status

Completed:

* branch creation
* Synthea setup
* Java setup
* PostgreSQL setup
* database creation
* OMOP-like schema creation
* staging imports
* mapping table creation
* core table loading
* observation and measurement loading
* Type 2 Diabetes verification query
* verification SQL script preparation

Current status:

* PostgreSQL running
* schema created
* data loaded
* verification queries working
* T2D query working
* Sprint 1 database deliverable complete

---

## 12. Next Steps

Next database tasks include:

* clean and organize SQL scripts for repository submission,
* refine SQL templates for cohort characterization,
* prepare parameterized SQL query templates for Sprint 2,
* improve concept vocabulary handling if needed later,
* support backend integration with reusable query outputs.

```

