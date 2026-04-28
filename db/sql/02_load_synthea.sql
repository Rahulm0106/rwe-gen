-- ============================================================
-- 02_load_synthea.sql
-- Loads Synthea CSVs into staging tables, then builds the
-- person + visit_occurrence + map tables that 03_etl_setup.sql
-- expects to already exist.
--
-- Runs automatically on first DB boot via /docker-entrypoint-initdb.d
-- when ./db/synthea is mounted to /synthea inside the container.
--
-- Idempotent: drops/recreates staging + map tables, truncates
-- person + visit_occurrence cascade. Safe to re-run manually:
--   docker exec -it rwe_gen_db psql -U rwe_user -d omop_rwe \
--       -f /docker-entrypoint-initdb.d/02_load_synthea.sql
-- ============================================================


-- ============================================================
-- STEP 1 — STAGING TABLES (column order matches CSV headers exactly)
-- ============================================================

DROP TABLE IF EXISTS staging_patients     CASCADE;
DROP TABLE IF EXISTS staging_encounters   CASCADE;
DROP TABLE IF EXISTS staging_conditions   CASCADE;
DROP TABLE IF EXISTS staging_medications  CASCADE;
DROP TABLE IF EXISTS staging_observations CASCADE;

-- patients.csv: Id,BIRTHDATE,DEATHDATE,SSN,DRIVERS,PASSPORT,PREFIX,FIRST,MIDDLE,
--   LAST,SUFFIX,MAIDEN,MARITAL,RACE,ETHNICITY,GENDER,BIRTHPLACE,ADDRESS,CITY,
--   STATE,COUNTY,FIPS,ZIP,LAT,LON,HEALTHCARE_EXPENSES,HEALTHCARE_COVERAGE,INCOME
CREATE TABLE staging_patients (
    id                  TEXT,
    birthdate           TEXT,
    deathdate           TEXT,
    ssn                 TEXT,
    drivers             TEXT,
    passport            TEXT,
    prefix              TEXT,
    first               TEXT,
    middle              TEXT,
    last                TEXT,
    suffix              TEXT,
    maiden              TEXT,
    marital             TEXT,
    race                TEXT,
    ethnicity           TEXT,
    gender              TEXT,
    birthplace          TEXT,
    address             TEXT,
    city                TEXT,
    state               TEXT,
    county              TEXT,
    fips                TEXT,
    zip                 TEXT,
    lat                 TEXT,
    lon                 TEXT,
    healthcare_expenses TEXT,
    healthcare_coverage TEXT,
    income              TEXT
);

-- encounters.csv: Id,START,STOP,PATIENT,ORGANIZATION,PROVIDER,PAYER,
--   ENCOUNTERCLASS,CODE,DESCRIPTION,BASE_ENCOUNTER_COST,TOTAL_CLAIM_COST,
--   PAYER_COVERAGE,REASONCODE,REASONDESCRIPTION
CREATE TABLE staging_encounters (
    id                  TEXT,
    start_time          TEXT,
    stop_time           TEXT,
    patient             TEXT,
    organization        TEXT,
    provider            TEXT,
    payer               TEXT,
    encounterclass      TEXT,
    code                TEXT,
    description         TEXT,
    base_encounter_cost TEXT,
    total_claim_cost    TEXT,
    payer_coverage      TEXT,
    reasoncode          TEXT,
    reasondescription   TEXT
);

-- conditions.csv: START,STOP,PATIENT,ENCOUNTER,SYSTEM,CODE,DESCRIPTION
CREATE TABLE staging_conditions (
    start_time  TEXT,
    stop_time   TEXT,
    patient     TEXT,
    encounter   TEXT,
    system      TEXT,
    code        TEXT,
    description TEXT
);

-- medications.csv: START,STOP,PATIENT,PAYER,ENCOUNTER,CODE,DESCRIPTION,
--   BASE_COST,PAYER_COVERAGE,DISPENSES,TOTALCOST,REASONCODE,REASONDESCRIPTION
CREATE TABLE staging_medications (
    start_time         TEXT,
    stop_time          TEXT,
    patient            TEXT,
    payer              TEXT,
    encounter          TEXT,
    code               TEXT,
    description        TEXT,
    base_cost          TEXT,
    payer_coverage     TEXT,
    dispenses          TEXT,
    totalcost          TEXT,
    reasoncode         TEXT,
    reasondescription  TEXT
);

-- observations.csv: DATE,PATIENT,ENCOUNTER,CATEGORY,CODE,DESCRIPTION,
--   VALUE,UNITS,TYPE
CREATE TABLE staging_observations (
    date        TEXT,
    patient     TEXT,
    encounter   TEXT,
    category    TEXT,
    code        TEXT,
    description TEXT,
    value       TEXT,
    units       TEXT,
    type        TEXT
);


-- ============================================================
-- STEP 2 — COPY CSVs INTO STAGING
-- /synthea/ is the read-only volume mount of ./db/synthea
-- ============================================================

\echo 'Loading patients.csv...'
COPY staging_patients     FROM '/synthea/patients.csv'     WITH (FORMAT csv, HEADER true);

\echo 'Loading encounters.csv...'
COPY staging_encounters   FROM '/synthea/encounters.csv'   WITH (FORMAT csv, HEADER true);

\echo 'Loading conditions.csv...'
COPY staging_conditions   FROM '/synthea/conditions.csv'   WITH (FORMAT csv, HEADER true);

\echo 'Loading medications.csv...'
COPY staging_medications  FROM '/synthea/medications.csv'  WITH (FORMAT csv, HEADER true);

\echo 'Loading observations.csv (this is the big one — ~1.6 GB)...'
COPY staging_observations FROM '/synthea/observations.csv' WITH (FORMAT csv, HEADER true);

SELECT
    (SELECT COUNT(*) FROM staging_patients)     AS patients,
    (SELECT COUNT(*) FROM staging_encounters)   AS encounters,
    (SELECT COUNT(*) FROM staging_conditions)   AS conditions,
    (SELECT COUNT(*) FROM staging_medications)  AS medications,
    (SELECT COUNT(*) FROM staging_observations) AS observations;


-- ============================================================
-- STEP 3 — MAP TABLES (synthea string IDs → OMOP integer IDs)
-- 03_etl_setup.sql joins on these.
-- ============================================================

DROP TABLE IF EXISTS encounter_map CASCADE;
DROP TABLE IF EXISTS patient_map   CASCADE;

CREATE TABLE patient_map (
    synthea_patient_id TEXT   PRIMARY KEY,
    person_id          BIGINT NOT NULL UNIQUE
);

INSERT INTO patient_map (synthea_patient_id, person_id)
SELECT id, ROW_NUMBER() OVER (ORDER BY id)
FROM staging_patients;

CREATE TABLE encounter_map (
    synthea_encounter_id TEXT   PRIMARY KEY,
    visit_occurrence_id  BIGINT NOT NULL UNIQUE
);

INSERT INTO encounter_map (synthea_encounter_id, visit_occurrence_id)
SELECT id, ROW_NUMBER() OVER (ORDER BY id)
FROM staging_encounters;


-- ============================================================
-- STEP 4 — POPULATE person
-- gender_concept_id: M → 8507 (Male), F → 8532 (Female)
-- race/ethnicity left as 0 for MVP (Synthea values are free text;
-- proper OMOP mapping is out of scope for Sprint 1).
-- ============================================================

TRUNCATE TABLE person CASCADE;

INSERT INTO person (
    person_id,
    gender_concept_id,
    year_of_birth,
    month_of_birth,
    day_of_birth,
    birth_datetime,
    race_concept_id,
    ethnicity_concept_id
)
SELECT
    pm.person_id,
    CASE
        WHEN UPPER(sp.gender) = 'M' THEN 8507
        WHEN UPPER(sp.gender) = 'F' THEN 8532
        ELSE 0
    END,
    EXTRACT(YEAR  FROM sp.birthdate::date)::int,
    EXTRACT(MONTH FROM sp.birthdate::date)::int,
    EXTRACT(DAY   FROM sp.birthdate::date)::int,
    sp.birthdate::timestamp,
    0,
    0
FROM staging_patients sp
JOIN patient_map pm ON sp.id = pm.synthea_patient_id;


-- ============================================================
-- STEP 5 — POPULATE visit_occurrence
-- visit_concept_id derived from Synthea ENCOUNTERCLASS:
--   ambulatory/outpatient/wellness → 9202 (Outpatient Visit)
--   urgentcare/emergency           → 9203 (Emergency Room Visit)
--   inpatient                      → 9201 (Inpatient Visit)
--   else                           → 0
-- ============================================================

TRUNCATE TABLE visit_occurrence CASCADE;

INSERT INTO visit_occurrence (
    visit_occurrence_id,
    person_id,
    visit_concept_id,
    visit_start_date,
    visit_end_date
)
SELECT
    em.visit_occurrence_id,
    pm.person_id,
    CASE
        WHEN LOWER(se.encounterclass) IN ('ambulatory', 'outpatient', 'wellness') THEN 9202
        WHEN LOWER(se.encounterclass) IN ('urgentcare', 'emergency')              THEN 9203
        WHEN LOWER(se.encounterclass) = 'inpatient'                               THEN 9201
        ELSE 0
    END,
    se.start_time::date,
    CASE
        WHEN se.stop_time IS NULL OR se.stop_time = '' THEN NULL
        ELSE se.stop_time::date
    END
FROM staging_encounters se
JOIN encounter_map em ON se.id      = em.synthea_encounter_id
JOIN patient_map   pm ON se.patient = pm.synthea_patient_id;


-- ============================================================
-- STEP 6 — QUICK CONFIRMATION
-- ============================================================

SELECT 'persons loaded'           AS check_name, COUNT(*) AS count FROM person
UNION ALL
SELECT 'visit_occurrence loaded', COUNT(*)                         FROM visit_occurrence
UNION ALL
SELECT 'patient_map rows',        COUNT(*)                         FROM patient_map
UNION ALL
SELECT 'encounter_map rows',      COUNT(*)                         FROM encounter_map;

\echo '02_load_synthea.sql complete. 03_etl_setup.sql will run next.'
