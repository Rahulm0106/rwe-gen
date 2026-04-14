-- ============================================================
-- RWE-Gen · ETL Fix Script for Laya
-- Fixes all 4 bugs found by Rahul verification run
-- Staging tables are UNTOUCHED — Synthea does NOT need
-- to be re-run. This script only fixes the INSERT mappings.
--
-- Run top to bottom in one shot.
-- After running, give Rahul the go-ahead to re-run
-- sprint1_verification.sql to confirm all gates pass.
-- ============================================================


-- ============================================================
-- STEP 1 — CLEAR THE BROKEN DATA
-- Wipe the 4 tables that have bad/missing data.
-- Staging tables are NOT touched.
-- ============================================================

TRUNCATE TABLE measurement          CASCADE;
TRUNCATE TABLE observation          CASCADE;
TRUNCATE TABLE drug_exposure        CASCADE;
TRUNCATE TABLE condition_occurrence CASCADE;

-- observation_period may not exist yet — drop safely
DROP TABLE IF EXISTS observation_period;


-- ============================================================
-- STEP 2 — RE-INSERT condition_occurrence
-- FIX: All 4 disease modules now get real concept IDs.
-- Previously only T2D was mapped; Obesity/HTN/CKD got 0.
-- ============================================================

INSERT INTO condition_occurrence (
    condition_occurrence_id,
    person_id,
    condition_concept_id,
    condition_start_date,
    condition_end_date,
    visit_occurrence_id
)
SELECT
    ROW_NUMBER() OVER (ORDER BY sc.patient, sc.start_time, sc.code),
    pm.person_id,
    CASE
        -- Type 2 Diabetes
        WHEN LOWER(sc.description) LIKE '%diabetes mellitus type 2%'   THEN 201826
        WHEN LOWER(sc.description) LIKE '%due to type 2 diabetes%'     THEN 201826
        WHEN LOWER(sc.description) LIKE '%type 2 diabetes%'            THEN 201826
        -- Obesity
        WHEN LOWER(sc.description) LIKE '%obesity%'                    THEN 433736
        WHEN LOWER(sc.description) LIKE '%overweight%'                 THEN 433736
        WHEN LOWER(sc.description) LIKE '%body mass index 30%'         THEN 433736
        -- Hypertension
        WHEN LOWER(sc.description) LIKE '%hypertension%'               THEN 316866
        WHEN LOWER(sc.description) LIKE '%high blood pressure%'        THEN 316866
        -- Chronic Kidney Disease
        WHEN LOWER(sc.description) LIKE '%chronic kidney disease%'     THEN 46271022
        WHEN LOWER(sc.description) LIKE '%kidney disease%'             THEN 46271022
        WHEN LOWER(sc.description) LIKE '%renal insufficiency%'        THEN 46271022
        WHEN LOWER(sc.description) LIKE '%renal failure%'              THEN 46271022
        WHEN LOWER(sc.description) LIKE '%ckd%'                        THEN 46271022
        -- Everything else stays 0
        ELSE 0
    END,
    sc.start_time::date,
    CASE
        WHEN sc.stop_time IS NULL OR sc.stop_time = '' THEN NULL
        ELSE sc.stop_time::date
    END,
    em.visit_occurrence_id
FROM staging_conditions sc
JOIN patient_map pm
    ON sc.patient = pm.synthea_patient_id
LEFT JOIN encounter_map em
    ON sc.encounter = em.synthea_encounter_id;

-- Quick check
SELECT
    condition_concept_id,
    COUNT(*) AS row_count,
    CASE
        WHEN condition_concept_id = 201826   THEN 'Type 2 Diabetes'
        WHEN condition_concept_id = 433736   THEN 'Obesity'
        WHEN condition_concept_id = 316866   THEN 'Hypertension'
        WHEN condition_concept_id = 46271022 THEN 'Chronic Kidney Disease'
        WHEN condition_concept_id = 0        THEN 'Other / unmapped'
        ELSE 'Unknown'
    END AS label
FROM condition_occurrence
GROUP BY condition_concept_id
ORDER BY row_count DESC;


-- ============================================================
-- STEP 3 — RE-INSERT drug_exposure
-- FIX: Key drugs now get real RxNorm concept IDs.
-- Previously every drug got drug_concept_id = 0.
-- ============================================================

INSERT INTO drug_exposure (
    drug_exposure_id,
    person_id,
    drug_concept_id,
    drug_exposure_start_date,
    drug_exposure_end_date,
    visit_occurrence_id
)
SELECT
    ROW_NUMBER() OVER (ORDER BY sm.patient, sm.start_time, sm.code),
    pm.person_id,
    CASE
        -- T2D medications
        WHEN LOWER(sm.description) LIKE '%metformin%'                  THEN 1503297
        WHEN LOWER(sm.description) LIKE '%glipizide%'                  THEN 1594973
        WHEN LOWER(sm.description) LIKE '%glyburide%'                  THEN 1516766
        WHEN LOWER(sm.description) LIKE '%glimepiride%'                THEN 1597756
        WHEN LOWER(sm.description) LIKE '%sitagliptin%'                THEN 1580747
        WHEN LOWER(sm.description) LIKE '%insulin%'                    THEN 1516766
        WHEN LOWER(sm.description) LIKE '%liraglutide%'                THEN 40170911
        WHEN LOWER(sm.description) LIKE '%dulaglutide%'                THEN 40239216
        WHEN LOWER(sm.description) LIKE '%empagliflozin%'              THEN 45774751
        WHEN LOWER(sm.description) LIKE '%canagliflozin%'              THEN 43526465
        WHEN LOWER(sm.description) LIKE '%pioglitazone%'               THEN 1525215
        -- Hypertension medications
        WHEN LOWER(sm.description) LIKE '%lisinopril%'                 THEN 1308216
        WHEN LOWER(sm.description) LIKE '%enalapril%'                  THEN 1341927
        WHEN LOWER(sm.description) LIKE '%ramipril%'                   THEN 1335471
        WHEN LOWER(sm.description) LIKE '%losartan%'                   THEN 1367500
        WHEN LOWER(sm.description) LIKE '%valsartan%'                  THEN 1308842
        WHEN LOWER(sm.description) LIKE '%amlodipine%'                 THEN 1332418
        WHEN LOWER(sm.description) LIKE '%hydrochlorothiazide%'        THEN 974166
        WHEN LOWER(sm.description) LIKE '%furosemide%'                 THEN 956874
        WHEN LOWER(sm.description) LIKE '%carvedilol%'                 THEN 1346823
        WHEN LOWER(sm.description) LIKE '%metoprolol%'                 THEN 1307046
        WHEN LOWER(sm.description) LIKE '%atenolol%'                   THEN 1314002
        -- Statins (CVD risk in T2D + HTN)
        WHEN LOWER(sm.description) LIKE '%atorvastatin%'               THEN 1545958
        WHEN LOWER(sm.description) LIKE '%simvastatin%'                THEN 1539403
        WHEN LOWER(sm.description) LIKE '%rosuvastatin%'               THEN 1510813
        WHEN LOWER(sm.description) LIKE '%pravastatin%'                THEN 1551803
        -- Everything else
        ELSE 0
    END,
    CAST(sm.start_time AS timestamp)::date,
    CASE
        WHEN sm.stop_time IS NULL OR sm.stop_time = '' THEN NULL
        ELSE CAST(sm.stop_time AS timestamp)::date
    END,
    em.visit_occurrence_id
FROM staging_medications sm
JOIN patient_map pm
    ON sm.patient = pm.synthea_patient_id
LEFT JOIN encounter_map em
    ON sm.encounter = em.synthea_encounter_id;

-- Quick check
SELECT
    drug_concept_id,
    COUNT(*) AS row_count,
    CASE
        WHEN drug_concept_id = 1503297  THEN 'Metformin'
        WHEN drug_concept_id = 1308216  THEN 'Lisinopril'
        WHEN drug_concept_id = 1332418  THEN 'Amlodipine'
        WHEN drug_concept_id = 1545958  THEN 'Atorvastatin'
        WHEN drug_concept_id = 1516766  THEN 'Insulin / Glyburide'
        WHEN drug_concept_id = 1594973  THEN 'Glipizide'
        WHEN drug_concept_id = 0        THEN 'Other / unmapped'
        ELSE 'Other named drug'
    END AS label
FROM drug_exposure
GROUP BY drug_concept_id
ORDER BY row_count DESC
LIMIT 20;


-- ============================================================
-- STEP 4 — RE-INSERT measurement
-- FIX: Lab values now get real LOINC concept IDs.
-- Previously every measurement got measurement_concept_id = 0.
-- ============================================================

INSERT INTO measurement (
    measurement_id,
    person_id,
    measurement_concept_id,
    measurement_date,
    value_as_number
)
SELECT
    ROW_NUMBER() OVER (ORDER BY so.patient, so.date, so.description),
    pm.person_id,
    CASE
        -- T2D monitoring
        WHEN LOWER(so.description) LIKE '%hemoglobin a1c%'             THEN 3004410
        WHEN LOWER(so.description) LIKE '%hba1c%'                      THEN 3004410
        WHEN LOWER(so.description) LIKE '%a1c%'                        THEN 3004410
        WHEN LOWER(so.description) LIKE '%glycated hemoglobin%'        THEN 3004410
        -- Obesity
        WHEN LOWER(so.description) LIKE '%body mass index%'            THEN 3038553
        WHEN LOWER(so.description) LIKE '%bmi%'                        THEN 3038553
        -- Blood pressure (Hypertension)
        WHEN LOWER(so.description) LIKE '%systolic blood pressure%'    THEN 3004249
        WHEN LOWER(so.description) LIKE '%systolic%'                   THEN 3004249
        WHEN LOWER(so.description) LIKE '%diastolic blood pressure%'   THEN 3012888
        WHEN LOWER(so.description) LIKE '%diastolic%'                  THEN 3012888
        -- CKD staging
        WHEN LOWER(so.description) LIKE '%glomerular filtration%'      THEN 3049187
        WHEN LOWER(so.description) LIKE '%egfr%'                       THEN 3049187
        WHEN LOWER(so.description) LIKE '%creatinine%'                 THEN 3016723
        -- CVD risk in T2D + HTN
        WHEN LOWER(so.description) LIKE '%ldl%'                        THEN 3007070
        WHEN LOWER(so.description) LIKE '%low density lipoprotein%'    THEN 3007070
        WHEN LOWER(so.description) LIKE '%hdl%'                        THEN 3011884
        WHEN LOWER(so.description) LIKE '%high density lipoprotein%'   THEN 3011884
        WHEN LOWER(so.description) LIKE '%total cholesterol%'          THEN 3027114
        WHEN LOWER(so.description) LIKE '%cholesterol%'                THEN 3027114
        WHEN LOWER(so.description) LIKE '%triglyceride%'               THEN 3022335
        -- General glucose
        WHEN LOWER(so.description) LIKE '%glucose%'                    THEN 3004501
        -- Body weight and height
        WHEN LOWER(so.description) LIKE '%body weight%'                THEN 3025315
        WHEN LOWER(so.description) LIKE '%weight%'                     THEN 3025315
        WHEN LOWER(so.description) LIKE '%body height%'                THEN 3036277
        WHEN LOWER(so.description) LIKE '%height%'                     THEN 3036277
        -- Heart rate
        WHEN LOWER(so.description) LIKE '%heart rate%'                 THEN 3027018
        -- Potassium (CKD monitoring)
        WHEN LOWER(so.description) LIKE '%potassium%'                  THEN 3023103
        -- Sodium
        WHEN LOWER(so.description) LIKE '%sodium%'                     THEN 3019550
        -- Everything else numeric
        ELSE 0
    END,
    so.date::date,
    so.value::numeric
FROM staging_observations so
JOIN patient_map pm
    ON so.patient = pm.synthea_patient_id
WHERE so.value IS NOT NULL
  AND so.value <> ''
  AND so.value ~ '^[0-9]+(\.[0-9]+)?$';

-- Quick check — should see real concept IDs now, not mostly 0
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
        WHEN measurement_concept_id = 3027114 THEN 'Total Cholesterol'
        WHEN measurement_concept_id = 3004501 THEN 'Glucose'
        WHEN measurement_concept_id = 3025315 THEN 'Body Weight'
        WHEN measurement_concept_id = 0       THEN 'Other / unmapped'
        ELSE 'Other named lab'
    END AS label
FROM measurement
GROUP BY measurement_concept_id
ORDER BY row_count DESC
LIMIT 20;


-- ============================================================
-- STEP 5 — RE-INSERT observation (non-numeric values)
-- No concept ID fix needed here for MVP — smoking status
-- only. Kept as-is from original script.
-- ============================================================

INSERT INTO observation (
    observation_id,
    person_id,
    observation_concept_id,
    observation_date,
    value_as_string
)
SELECT
    ROW_NUMBER() OVER (ORDER BY so.patient, so.date, so.description),
    pm.person_id,
    CASE
        WHEN LOWER(so.description) LIKE '%tobacco%'      THEN 4005823
        WHEN LOWER(so.description) LIKE '%smoking%'      THEN 4005823
        WHEN LOWER(so.description) LIKE '%smoker%'       THEN 4005823
        ELSE 0
    END,
    so.date::date,
    so.value
FROM staging_observations so
JOIN patient_map pm
    ON so.patient = pm.synthea_patient_id
WHERE so.value IS NOT NULL
  AND so.value <> ''
  AND NOT (so.value ~ '^[0-9]+(\.[0-9]+)?$');

SELECT COUNT(*) AS observation_rows_loaded FROM observation;


-- ============================================================
-- STEP 6 — CREATE AND POPULATE observation_period
-- This table was MISSING from the original ETL entirely.
-- Required for ALL incidence analysis queries (Pattern 2).
-- One row per person: spans their first to last encounter.
-- ============================================================

CREATE TABLE observation_period (
    observation_period_id          BIGINT PRIMARY KEY,
    person_id                      BIGINT NOT NULL REFERENCES person(person_id),
    observation_period_start_date  DATE,
    observation_period_end_date    DATE,
    period_type_concept_id         INTEGER
);

INSERT INTO observation_period (
    observation_period_id,
    person_id,
    observation_period_start_date,
    observation_period_end_date,
    period_type_concept_id
)
SELECT
    ROW_NUMBER() OVER (ORDER BY pm.person_id),
    pm.person_id,
    MIN(vo.visit_start_date),
    MAX(vo.visit_end_date),
    44814724  -- OMOP standard: EHR encounter record
FROM visit_occurrence vo
JOIN patient_map pm
    ON vo.person_id = pm.person_id
GROUP BY pm.person_id;

-- Quick check
SELECT
    COUNT(*)                            AS observation_period_rows,
    COUNT(DISTINCT person_id)           AS persons_covered,
    MIN(observation_period_start_date)  AS earliest_start,
    MAX(observation_period_end_date)    AS latest_end
FROM observation_period;


-- ============================================================
-- STEP 7 — FINAL CONFIRMATION
-- Run these 4 checks. All must show non-zero.
-- If they do, tell Rahul to re-run the full verification
-- script to get the official sign-off summary.
-- ============================================================

SELECT '=== FINAL CONFIRMATION ===' AS "";

SELECT 'T2D records' AS check_name, COUNT(*) AS count,
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM condition_occurrence WHERE condition_concept_id = 201826
UNION ALL
SELECT 'Obesity records', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM condition_occurrence WHERE condition_concept_id = 433736
UNION ALL
SELECT 'Hypertension records', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM condition_occurrence WHERE condition_concept_id = 316866
UNION ALL
SELECT 'CKD records', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM condition_occurrence WHERE condition_concept_id = 46271022
UNION ALL
SELECT 'Metformin records', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM drug_exposure WHERE drug_concept_id = 1503297
UNION ALL
SELECT 'HbA1c records', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM measurement WHERE measurement_concept_id = 3004410
UNION ALL
SELECT 'BMI records', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM measurement WHERE measurement_concept_id = 3038553
UNION ALL
SELECT 'eGFR records', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM measurement WHERE measurement_concept_id = 3049187
UNION ALL
SELECT 'observation_period rows', COUNT(*),
    CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
FROM observation_period
UNION ALL
SELECT 'T2D + Metformin cohort (TC-01/02/03 base)', COUNT(DISTINCT co.person_id),
    CASE WHEN COUNT(DISTINCT co.person_id) > 0
         THEN 'PASS — Sprint 2 can begin'
         ELSE 'FAIL — base cohort still empty, check mappings above'
    END
FROM condition_occurrence co
JOIN drug_exposure de ON co.person_id = de.person_id
WHERE co.condition_concept_id = 201826
  AND de.drug_concept_id = 1503297;

-- ============================================================
-- DONE. If all rows above show PASS:
-- Message Rahul: "ETL fix complete, re-run verification script"
-- ============================================================
