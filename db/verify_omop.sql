-- ============================================================
-- RWE-Gen · Sprint 1 Verification Script
-- Run by: Rahul (QA)
-- Purpose: Confirm Laya ETL is complete and correct
--          before Sprint 2 begins (gate: April 15)
-- How to use: Run top to bottom. Every CHECK block prints
--             PASS or FAIL with a reason. All must be PASS.
-- ============================================================


-- ============================================================
-- SECTION 1 — TABLE EXISTENCE
-- Every table the project needs must exist before any
-- Sprint 2 SQL template work can begin.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 1 — TABLE EXISTENCE'               AS "";
SELECT '============================================' AS "";

SELECT
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'person')
         THEN 'PASS — person table exists'
         ELSE 'FAIL — person table MISSING'
    END AS check_person;

SELECT
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'condition_occurrence')
         THEN 'PASS — condition_occurrence table exists'
         ELSE 'FAIL — condition_occurrence table MISSING'
    END AS check_condition_occurrence;

SELECT
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'drug_exposure')
         THEN 'PASS — drug_exposure table exists'
         ELSE 'FAIL — drug_exposure table MISSING'
    END AS check_drug_exposure;

SELECT
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'measurement')
         THEN 'PASS — measurement table exists'
         ELSE 'FAIL — measurement table MISSING'
    END AS check_measurement;

SELECT
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'observation')
         THEN 'PASS — observation table exists'
         ELSE 'FAIL — observation table MISSING'
    END AS check_observation;

SELECT
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'visit_occurrence')
         THEN 'PASS — visit_occurrence table exists'
         ELSE 'FAIL — visit_occurrence table MISSING'
    END AS check_visit_occurrence;

-- CRITICAL: This table was missing from Laya original ETL script
SELECT
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'observation_period')
         THEN 'PASS — observation_period table exists'
         ELSE 'FAIL — observation_period table MISSING (needed for ALL incidence queries — re-run ETL with fix)'
    END AS check_observation_period;


-- ============================================================
-- SECTION 2 — ROW COUNTS
-- Confirms data actually loaded into each table.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 2 — ROW COUNTS'                    AS "";
SELECT '============================================' AS "";

SELECT
    'person'               AS table_name,
    COUNT(*)               AS row_count,
    CASE WHEN COUNT(*) >= 9000 THEN 'PASS — close to expected 10,000'
         WHEN COUNT(*) > 0     THEN 'WARN — loaded but fewer than expected 10,000'
         ELSE                       'FAIL — table is empty'
    END AS status
FROM person

UNION ALL

SELECT
    'condition_occurrence',
    COUNT(*),
    CASE WHEN COUNT(*) > 10000 THEN 'PASS'
         WHEN COUNT(*) > 0     THEN 'WARN — low row count, check Synthea modules loaded'
         ELSE                       'FAIL — table is empty'
    END
FROM condition_occurrence

UNION ALL

SELECT
    'drug_exposure',
    COUNT(*),
    CASE WHEN COUNT(*) > 10000 THEN 'PASS'
         WHEN COUNT(*) > 0     THEN 'WARN — low row count, check medications CSV'
         ELSE                       'FAIL — table is empty, drug filter queries will return zero cohort'
    END
FROM drug_exposure

UNION ALL

SELECT
    'measurement',
    COUNT(*),
    CASE WHEN COUNT(*) > 50000  THEN 'PASS'
         WHEN COUNT(*) > 0      THEN 'WARN — low row count, HbA1c/BMI/eGFR coverage may be thin'
         ELSE                        'FAIL — table is empty, ALL lab value queries will fail'
    END
FROM measurement

UNION ALL

SELECT
    'observation',
    COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS'
         ELSE                   'WARN — empty, smoking status queries affected'
    END
FROM observation

UNION ALL

SELECT
    'visit_occurrence',
    COUNT(*),
    CASE WHEN COUNT(*) > 10000 THEN 'PASS'
         WHEN COUNT(*) > 0     THEN 'WARN — low row count'
         ELSE                       'FAIL — table is empty'
    END
FROM visit_occurrence

UNION ALL

SELECT
    'observation_period',
    COUNT(*),
    CASE WHEN COUNT(*) >= 9000 THEN 'PASS'
         WHEN COUNT(*) > 0     THEN 'WARN — fewer rows than expected'
         ELSE                       'FAIL — table is empty, all incidence window queries will fail'
    END
FROM observation_period;


-- ============================================================
-- SECTION 3 — TC-11 OFFICIAL GATE CHECK
-- This is the formal Sprint 1 gate from the reference doc.
-- Must return non-zero.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 3 — TC-11 OFFICIAL GATE'           AS "";
SELECT '============================================' AS "";

SELECT
    COUNT(*) AS t2d_record_count,
    CASE WHEN COUNT(*) > 0
         THEN 'PASS — TC-11 GATE MET: T2D records present in condition_occurrence'
         ELSE 'FAIL — TC-11 GATE FAILED: No T2D records found'
    END AS tc11_status
FROM condition_occurrence
WHERE condition_concept_id = 201826;


-- ============================================================
-- SECTION 4 — ALL 4 DISEASE MODULE CONCEPT IDs
-- Bug found: original ETL only mapped T2D. Obesity, HTN,
-- CKD all got concept_id = 0.
-- All 4 must have non-zero counts here.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 4 — DISEASE MODULE CONCEPT IDs'    AS "";
SELECT '============================================' AS "";

SELECT
    concept_id,
    disease,
    record_count,
    CASE WHEN record_count > 0 THEN 'PASS'
         ELSE 'FAIL — concept ID not mapped in ETL, re-run with fix'
    END AS status
FROM (
    SELECT 201826   AS concept_id, 'Type 2 Diabetes'        AS disease, COUNT(*) AS record_count FROM condition_occurrence WHERE condition_concept_id = 201826
    UNION ALL
    SELECT 433736,               'Obesity',                              COUNT(*) FROM condition_occurrence WHERE condition_concept_id = 433736
    UNION ALL
    SELECT 316866,               'Hypertension',                         COUNT(*) FROM condition_occurrence WHERE condition_concept_id = 316866
    UNION ALL
    SELECT 46271022,             'Chronic Kidney Disease',               COUNT(*) FROM condition_occurrence WHERE condition_concept_id = 46271022
) disease_check
ORDER BY concept_id;

-- Also show what concept IDs actually exist in the table
-- If you see a lot of 0s, Bug 1 from Laya script was not fixed
SELECT '--- Actual concept_id distribution in condition_occurrence ---' AS "";
SELECT
    condition_concept_id,
    COUNT(*) AS row_count,
    CASE
        WHEN condition_concept_id = 201826   THEN 'Type 2 Diabetes'
        WHEN condition_concept_id = 433736   THEN 'Obesity'
        WHEN condition_concept_id = 316866   THEN 'Hypertension'
        WHEN condition_concept_id = 46271022 THEN 'Chronic Kidney Disease'
        WHEN condition_concept_id = 0        THEN 'UNMAPPED (concept_id = 0) — ETL bug'
        ELSE                                      'Other condition'
    END AS label
FROM condition_occurrence
GROUP BY condition_concept_id
ORDER BY row_count DESC
LIMIT 20;


-- ============================================================
-- SECTION 5 — MEASUREMENT CONCEPT IDs
-- Bug found: original ETL hardcoded measurement_concept_id = 0
-- for everything. HbA1c, BMI, eGFR, BP must have real IDs.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 5 — MEASUREMENT CONCEPT IDs'       AS "";
SELECT '============================================' AS "";

SELECT
    concept_id,
    lab_name,
    record_count,
    CASE WHEN record_count > 0 THEN 'PASS'
         ELSE 'FAIL — lab value not mapped, re-run ETL with measurement concept ID fix'
    END AS status
FROM (
    SELECT 3004410 AS concept_id, 'HbA1c (T2D monitoring)'     AS lab_name, COUNT(*) AS record_count FROM measurement WHERE measurement_concept_id = 3004410
    UNION ALL
    SELECT 3038553,               'BMI (Obesity definition)',                COUNT(*) FROM measurement WHERE measurement_concept_id = 3038553
    UNION ALL
    SELECT 3004249,               'Systolic BP (Hypertension)',              COUNT(*) FROM measurement WHERE measurement_concept_id = 3004249
    UNION ALL
    SELECT 3012888,               'Diastolic BP (Hypertension)',             COUNT(*) FROM measurement WHERE measurement_concept_id = 3012888
    UNION ALL
    SELECT 3049187,               'eGFR (CKD staging)',                      COUNT(*) FROM measurement WHERE measurement_concept_id = 3049187
    UNION ALL
    SELECT 3016723,               'Serum Creatinine (CKD)',                  COUNT(*) FROM measurement WHERE measurement_concept_id = 3016723
    UNION ALL
    SELECT 3007070,               'LDL Cholesterol (CVD risk)',              COUNT(*) FROM measurement WHERE measurement_concept_id = 3007070
) lab_check
ORDER BY concept_id;

-- Show what measurement concept IDs actually exist
-- A large count of 0 means Bug 2 was not fixed
SELECT '--- Actual measurement_concept_id distribution (top 15) ---' AS "";
SELECT
    measurement_concept_id,
    COUNT(*) AS row_count,
    CASE
        WHEN measurement_concept_id = 3004410 THEN 'HbA1c'
        WHEN measurement_concept_id = 3038553 THEN 'BMI'
        WHEN measurement_concept_id = 3004249 THEN 'Systolic BP'
        WHEN measurement_concept_id = 3012888 THEN 'Diastolic BP'
        WHEN measurement_concept_id = 3049187 THEN 'eGFR'
        WHEN measurement_concept_id = 3016723 THEN 'Creatinine'
        WHEN measurement_concept_id = 3007070 THEN 'LDL'
        WHEN measurement_concept_id = 0       THEN 'UNMAPPED (concept_id = 0) — ETL bug'
        ELSE                                       'Other'
    END AS label
FROM measurement
GROUP BY measurement_concept_id
ORDER BY row_count DESC
LIMIT 15;


-- ============================================================
-- SECTION 6 — DRUG CONCEPT IDs
-- Bug found: original ETL hardcoded drug_concept_id = 0.
-- Metformin and other key drugs must have real concept IDs.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 6 — DRUG CONCEPT IDs'              AS "";
SELECT '============================================' AS "";

SELECT
    concept_id,
    drug_name,
    record_count,
    CASE WHEN record_count > 0 THEN 'PASS'
         ELSE 'FAIL — drug not mapped, all drug-filtered cohort queries will return zero'
    END AS status
FROM (
    SELECT 1503297 AS concept_id, 'Metformin (primary T2D drug)'     AS drug_name, COUNT(*) AS record_count FROM drug_exposure WHERE drug_concept_id = 1503297
    UNION ALL
    SELECT 1308216,               'Lisinopril (ACE inhibitor / HTN)',             COUNT(*) FROM drug_exposure WHERE drug_concept_id = 1308216
    UNION ALL
    SELECT 1332418,               'Amlodipine (CCB / HTN)',                       COUNT(*) FROM drug_exposure WHERE drug_concept_id = 1332418
    UNION ALL
    SELECT 1545958,               'Atorvastatin (statin / CVD risk)',              COUNT(*) FROM drug_exposure WHERE drug_concept_id = 1545958
    UNION ALL
    SELECT 1516766,               'Insulin (T2D advanced)',                        COUNT(*) FROM drug_exposure WHERE drug_concept_id = 1516766
    UNION ALL
    SELECT 1594973,               'Glipizide (sulfonylurea / T2D)',               COUNT(*) FROM drug_exposure WHERE drug_concept_id = 1594973
) drug_check
ORDER BY concept_id;

-- Show actual drug_concept_id distribution
-- A large count of 0 means Bug 3 was not fixed
SELECT '--- Actual drug_concept_id distribution (top 15) ---' AS "";
SELECT
    drug_concept_id,
    COUNT(*) AS row_count,
    CASE
        WHEN drug_concept_id = 1503297 THEN 'Metformin'
        WHEN drug_concept_id = 1308216 THEN 'Lisinopril'
        WHEN drug_concept_id = 1332418 THEN 'Amlodipine'
        WHEN drug_concept_id = 1545958 THEN 'Atorvastatin'
        WHEN drug_concept_id = 1516766 THEN 'Insulin'
        WHEN drug_concept_id = 1594973 THEN 'Glipizide'
        WHEN drug_concept_id = 0       THEN 'UNMAPPED (concept_id = 0) — ETL bug'
        ELSE                                'Other drug'
    END AS label
FROM drug_exposure
GROUP BY drug_concept_id
ORDER BY row_count DESC
LIMIT 15;


-- ============================================================
-- SECTION 7 — OBSERVATION PERIOD COVERAGE
-- Missing from Laya original script entirely.
-- Needed for ALL incidence analysis queries.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 7 — OBSERVATION PERIOD COVERAGE'   AS "";
SELECT '============================================' AS "";

SELECT
    COUNT(*)                            AS observation_period_rows,
    COUNT(DISTINCT person_id)           AS persons_covered,
    MIN(observation_period_start_date)  AS earliest_start,
    MAX(observation_period_end_date)    AS latest_end,
    CASE
        WHEN COUNT(DISTINCT person_id) >= 9000 THEN 'PASS — observation_period covers expected population'
        WHEN COUNT(DISTINCT person_id) > 0     THEN 'WARN — fewer persons than expected'
        ELSE                                        'FAIL — observation_period is empty, all incidence queries will fail'
    END AS status
FROM observation_period;


-- ============================================================
-- SECTION 8 — CROSS-TABLE INTEGRITY
-- Checks that person_ids are consistent across tables.
-- Orphan rows (person_id not in person table) will cause
-- SQL joins to silently drop patients from cohorts.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 8 — CROSS-TABLE INTEGRITY'         AS "";
SELECT '============================================' AS "";

SELECT
    'condition_occurrence orphans' AS check_name,
    COUNT(*) AS orphan_count,
    CASE WHEN COUNT(*) = 0 THEN 'PASS — all person_ids exist in person table'
         ELSE 'FAIL — orphan person_ids found, cohort queries will drop these patients'
    END AS status
FROM condition_occurrence co
WHERE NOT EXISTS (SELECT 1 FROM person p WHERE p.person_id = co.person_id)

UNION ALL

SELECT
    'drug_exposure orphans',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'PASS'
         ELSE 'FAIL — orphan person_ids in drug_exposure'
    END
FROM drug_exposure de
WHERE NOT EXISTS (SELECT 1 FROM person p WHERE p.person_id = de.person_id)

UNION ALL

SELECT
    'measurement orphans',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'PASS'
         ELSE 'FAIL — orphan person_ids in measurement'
    END
FROM measurement m
WHERE NOT EXISTS (SELECT 1 FROM person p WHERE p.person_id = m.person_id)

UNION ALL

SELECT
    'observation_period orphans',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'PASS'
         ELSE 'FAIL — orphan person_ids in observation_period'
    END
FROM observation_period op
WHERE NOT EXISTS (SELECT 1 FROM person p WHERE p.person_id = op.person_id);


-- ============================================================
-- SECTION 9 — END-TO-END QUERY SIMULATION
-- These are simplified versions of the actual SQL templates
-- Laya will write in Sprint 2. If they return non-zero here,
-- the data is shaped correctly for the pipeline to work.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 9 — END-TO-END QUERY SIMULATION'   AS "";
SELECT '============================================' AS "";

-- Simulate: "T2D patients on metformin" cohort
-- This is the base cohort for TC-01, TC-02, TC-03
SELECT
    'T2D patients on metformin cohort' AS simulation,
    COUNT(DISTINCT co.person_id)       AS cohort_size,
    CASE WHEN COUNT(DISTINCT co.person_id) > 0
         THEN 'PASS — cohort is non-zero, TC-01/02/03 can run'
         ELSE 'FAIL — cohort is zero. Check condition concept ID 201826 AND drug concept ID 1503297 are both mapped'
    END AS status
FROM condition_occurrence co
JOIN drug_exposure de
    ON co.person_id = de.person_id
WHERE co.condition_concept_id = 201826   -- T2D
  AND de.drug_concept_id      = 1503297; -- Metformin

-- Simulate: HbA1c readings for T2D patients
-- This powers lab value summary (Pattern 3 / TC-03)
SELECT
    'HbA1c readings for T2D patients' AS simulation,
    COUNT(*)                           AS lab_row_count,
    ROUND(AVG(m.value_as_number), 2)   AS mean_hba1c,
    CASE WHEN COUNT(*) > 0
         THEN 'PASS — HbA1c data present, lab value summary queries can run'
         ELSE 'FAIL — no HbA1c data found. Check measurement_concept_id = 3004410 is mapped'
    END AS status
FROM condition_occurrence co
JOIN measurement m
    ON co.person_id = m.person_id
WHERE co.condition_concept_id  = 201826  -- T2D
  AND m.measurement_concept_id = 3004410 -- HbA1c
  AND m.value_as_number IS NOT NULL;

-- Simulate: Observation window available for T2D patients
-- This powers incidence rate calculation (Pattern 2 / TC-01)
SELECT
    'Observation period for T2D patients' AS simulation,
    COUNT(DISTINCT co.person_id)          AS patients_with_obs_window,
    CASE WHEN COUNT(DISTINCT co.person_id) > 0
         THEN 'PASS — observation windows exist for T2D cohort, incidence rate can be calculated'
         ELSE 'FAIL — no observation windows for T2D patients. observation_period table empty or missing'
    END AS status
FROM condition_occurrence co
JOIN observation_period op
    ON co.person_id = op.person_id
WHERE co.condition_concept_id = 201826;

-- Simulate: BMI for obese patients
-- Confirms Obesity module and BMI measurement mapping both worked
SELECT
    'BMI readings for obese patients'  AS simulation,
    COUNT(*)                            AS lab_row_count,
    ROUND(AVG(m.value_as_number), 2)   AS mean_bmi,
    CASE WHEN COUNT(*) > 0
         THEN 'PASS — BMI data present for obese cohort'
         ELSE 'FAIL — no BMI data. Check condition_concept_id = 433736 AND measurement_concept_id = 3038553'
    END AS status
FROM condition_occurrence co
JOIN measurement m
    ON co.person_id = m.person_id
WHERE co.condition_concept_id  = 433736  -- Obesity
  AND m.measurement_concept_id = 3038553 -- BMI
  AND m.value_as_number IS NOT NULL;


-- ============================================================
-- SECTION 10 — STAGING TABLE SANITY
-- Checks the raw Synthea CSVs loaded into staging correctly.
-- If staging counts are low, the Synthea generation step
-- may not have run with all 4 disease modules.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 10 — STAGING TABLE COUNTS'         AS "";
SELECT '============================================' AS "";

SELECT
    'staging_patients'   AS table_name, COUNT(*) AS row_count FROM staging_patients
UNION ALL SELECT 'staging_encounters',  COUNT(*) FROM staging_encounters
UNION ALL SELECT 'staging_conditions',  COUNT(*) FROM staging_conditions
UNION ALL SELECT 'staging_medications', COUNT(*) FROM staging_medications
UNION ALL SELECT 'staging_observations',COUNT(*) FROM staging_observations;

-- Check all 4 disease descriptions are present in raw staging data
-- If any of these return 0, the Synthea module didn't generate data
-- and no ETL fix will help — Synthea must be re-run
SELECT '--- Disease description coverage in staging_conditions ---' AS "";
SELECT
    disease,
    record_count,
    CASE WHEN record_count > 0
         THEN 'PASS — raw Synthea data present for this disease'
         ELSE 'FAIL — no raw data for this disease. Synthea must be re-run with this module enabled'
    END AS status
FROM (
    SELECT 'Type 2 Diabetes' AS disease,
           COUNT(*) AS record_count
    FROM staging_conditions
    WHERE LOWER(description) LIKE '%type 2 diabetes%'
       OR LOWER(description) LIKE '%due to type 2 diabetes%'

    UNION ALL
    SELECT 'Obesity', COUNT(*)
    FROM staging_conditions
    WHERE LOWER(description) LIKE '%obesity%'

    UNION ALL
    SELECT 'Hypertension', COUNT(*)
    FROM staging_conditions
    WHERE LOWER(description) LIKE '%hypertension%'

    UNION ALL
    SELECT 'Chronic Kidney Disease', COUNT(*)
    FROM staging_conditions
    WHERE LOWER(description) LIKE '%chronic kidney%'
       OR LOWER(description) LIKE '%kidney disease%'
       OR LOWER(description) LIKE '%renal%'
) disease_staging_check;

-- Check key lab descriptions are in raw staging observations
SELECT '--- Key lab coverage in staging_observations ---' AS "";
SELECT
    lab_name,
    record_count,
    CASE WHEN record_count > 0
         THEN 'PASS — raw lab data present'
         ELSE 'FAIL — no raw data for this lab. ETL concept ID mapping cannot fix missing source data'
    END AS status
FROM (
    SELECT 'HbA1c' AS lab_name,
           COUNT(*) AS record_count
    FROM staging_observations
    WHERE LOWER(description) LIKE '%a1c%'
       OR LOWER(description) LIKE '%hemoglobin a1c%'

    UNION ALL
    SELECT 'BMI', COUNT(*)
    FROM staging_observations
    WHERE LOWER(description) LIKE '%body mass index%'
       OR LOWER(description) LIKE '%bmi%'

    UNION ALL
    SELECT 'eGFR / Creatinine', COUNT(*)
    FROM staging_observations
    WHERE LOWER(description) LIKE '%egfr%'
       OR LOWER(description) LIKE '%glomerular%'
       OR LOWER(description) LIKE '%creatinine%'

    UNION ALL
    SELECT 'Blood Pressure', COUNT(*)
    FROM staging_observations
    WHERE LOWER(description) LIKE '%systolic%'
       OR LOWER(description) LIKE '%diastolic%'

    UNION ALL
    SELECT 'Metformin (medications)', COUNT(*)
    FROM staging_medications
    WHERE LOWER(description) LIKE '%metformin%'
) lab_staging_check;


-- ============================================================
-- SECTION 11 — FINAL SPRINT 1 SIGN-OFF SUMMARY
-- One row per gate item. All must show PASS for Sprint 1
-- to be signed off and Sprint 2 to begin.
-- ============================================================

SELECT '============================================' AS "";
SELECT 'SECTION 11 — SPRINT 1 SIGN-OFF SUMMARY'   AS "";
SELECT '============================================' AS "";

SELECT gate, status FROM (

    SELECT 1 AS sort_order, 'TC-11: T2D records in condition_occurrence' AS gate,
        CASE WHEN (SELECT COUNT(*) FROM condition_occurrence WHERE condition_concept_id = 201826) > 0
             THEN 'PASS' ELSE 'FAIL' END AS status

    UNION ALL SELECT 2, 'person table populated (~10,000)',
        CASE WHEN (SELECT COUNT(*) FROM person) >= 9000
             THEN 'PASS' ELSE 'FAIL' END

    UNION ALL SELECT 3, 'All 4 disease modules mapped (not concept_id = 0)',
        CASE WHEN (SELECT COUNT(*) FROM condition_occurrence WHERE condition_concept_id IN (201826,433736,316866,46271022)) =
                  (SELECT COUNT(*) FROM condition_occurrence WHERE condition_concept_id != 0)
                  AND (SELECT COUNT(*) FROM condition_occurrence WHERE condition_concept_id IN (433736,316866,46271022)) > 0
             THEN 'PASS' ELSE 'FAIL — Obesity/HTN/CKD concept IDs not mapped' END

    UNION ALL SELECT 4, 'measurement table has real concept IDs (not all 0)',
        CASE WHEN (SELECT COUNT(*) FROM measurement WHERE measurement_concept_id != 0) > 0
             THEN 'PASS' ELSE 'FAIL — all measurement_concept_id = 0, ETL bug not fixed' END

    UNION ALL SELECT 5, 'HbA1c mapped in measurement (concept 3004410)',
        CASE WHEN (SELECT COUNT(*) FROM measurement WHERE measurement_concept_id = 3004410) > 0
             THEN 'PASS' ELSE 'FAIL' END

    UNION ALL SELECT 6, 'BMI mapped in measurement (concept 3038553)',
        CASE WHEN (SELECT COUNT(*) FROM measurement WHERE measurement_concept_id = 3038553) > 0
             THEN 'PASS' ELSE 'FAIL' END

    UNION ALL SELECT 7, 'drug_exposure has real concept IDs (not all 0)',
        CASE WHEN (SELECT COUNT(*) FROM drug_exposure WHERE drug_concept_id != 0) > 0
             THEN 'PASS' ELSE 'FAIL — all drug_concept_id = 0, ETL bug not fixed' END

    UNION ALL SELECT 8, 'Metformin mapped in drug_exposure (concept 1503297)',
        CASE WHEN (SELECT COUNT(*) FROM drug_exposure WHERE drug_concept_id = 1503297) > 0
             THEN 'PASS' ELSE 'FAIL' END

    UNION ALL SELECT 9, 'observation_period table exists and is populated',
        CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'observation_period')
              AND (SELECT COUNT(*) FROM observation_period) >= 9000
             THEN 'PASS' ELSE 'FAIL — missing or empty, incidence queries cannot run' END

    UNION ALL SELECT 10, 'T2D + Metformin cohort is non-zero (TC-01/02/03 base)',
        CASE WHEN (
            SELECT COUNT(DISTINCT co.person_id)
            FROM condition_occurrence co
            JOIN drug_exposure de ON co.person_id = de.person_id
            WHERE co.condition_concept_id = 201826
              AND de.drug_concept_id = 1503297
        ) > 0 THEN 'PASS' ELSE 'FAIL — base cohort for all 3 happy-path TCs is empty' END

    UNION ALL SELECT 11, 'HbA1c data joinable to T2D cohort (lab value query)',
        CASE WHEN (
            SELECT COUNT(*)
            FROM condition_occurrence co
            JOIN measurement m ON co.person_id = m.person_id
            WHERE co.condition_concept_id = 201826
              AND m.measurement_concept_id = 3004410
        ) > 0 THEN 'PASS' ELSE 'FAIL — HbA1c cannot be queried for T2D patients' END

    UNION ALL SELECT 12, 'docker-compose startup (manual check — cannot verify via SQL)',
        'MANUAL — confirm with Prasanna before April 15' AS status

    UNION ALL SELECT 13, 'React app loads in browser (manual check)',
        'MANUAL — confirm with Muktha before April 15' AS status

) summary
ORDER BY sort_order;

-- ============================================================
-- END OF SCRIPT
-- If all rows in Section 11 show PASS (or MANUAL):
--   Sprint 1 is done. Sprint 2 can begin April 16.
-- If any row shows FAIL:
--   Share the specific FAIL message with Laya immediately.
--   She needs to fix the ETL and re-run before April 15.
-- ============================================================
