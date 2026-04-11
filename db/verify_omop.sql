-- verify_omop.sql
-- RWE-Gen Sprint 1 final database verification
-- Owner: Laya Fakher
-- Purpose:
--   1) confirm PostgreSQL connection
--   2) confirm staging imports worked
--   3) confirm mapping tables were built
--   4) confirm final OMOP-like tables were loaded
--   5) verify TC-11 (T2D present with concept_id = 201826)
--   6) inspect disease coverage for obesity, hypertension, CKD
--   7) inspect BMI and HbA1c location in staging_observations
--   8) inspect HbA1c timing relative to T2D diagnosis

SELECT current_database() AS database_name;

------------------------------------------------------------
-- 1. Final core table row counts
------------------------------------------------------------
SELECT 'person' AS table_name, COUNT(*) AS row_count FROM person
UNION ALL
SELECT 'concept', COUNT(*) FROM concept
UNION ALL
SELECT 'visit_occurrence', COUNT(*) FROM visit_occurrence
UNION ALL
SELECT 'condition_occurrence', COUNT(*) FROM condition_occurrence
UNION ALL
SELECT 'drug_exposure', COUNT(*) FROM drug_exposure
UNION ALL
SELECT 'observation', COUNT(*) FROM observation
UNION ALL
SELECT 'measurement', COUNT(*) FROM measurement
ORDER BY table_name;

------------------------------------------------------------
-- 2. Mapping table counts
------------------------------------------------------------
SELECT COUNT(*) AS patient_map_count
FROM patient_map;

SELECT COUNT(*) AS encounter_map_count
FROM encounter_map;

------------------------------------------------------------
-- 3. Staging table counts
------------------------------------------------------------
SELECT COUNT(*) AS staging_patients_count
FROM staging_patients;

SELECT COUNT(*) AS staging_encounters_count
FROM staging_encounters;

SELECT COUNT(*) AS staging_conditions_count
FROM staging_conditions;

SELECT COUNT(*) AS staging_medications_count
FROM staging_medications;

SELECT COUNT(*) AS staging_observations_count
FROM staging_observations;

------------------------------------------------------------
-- 4. TC-11 verification: T2D must be present
------------------------------------------------------------
SELECT COUNT(*) AS t2d_count
FROM condition_occurrence
WHERE condition_concept_id = 201826;

------------------------------------------------------------
-- 5. T2D patient-level count
------------------------------------------------------------
SELECT COUNT(DISTINCT person_id) AS t2d_patient_count
FROM condition_occurrence
WHERE condition_concept_id = 201826;

------------------------------------------------------------
-- 6. Condition concept breakdown in final table
------------------------------------------------------------
SELECT
    condition_concept_id,
    COUNT(*) AS row_count
FROM condition_occurrence
GROUP BY condition_concept_id
ORDER BY row_count DESC, condition_concept_id;

------------------------------------------------------------
-- 7. Disease coverage checks in staging_conditions
--    These confirm required disease families are present
------------------------------------------------------------

-- Type 2 Diabetes
SELECT
    description,
    COUNT(*) AS row_count
FROM staging_conditions
WHERE LOWER(description) LIKE '%type 2 diabetes%'
GROUP BY description
ORDER BY row_count DESC;

-- Obesity
SELECT
    description,
    COUNT(*) AS row_count
FROM staging_conditions
WHERE LOWER(description) LIKE '%obesity%'
GROUP BY description
ORDER BY row_count DESC;

-- Hypertension
SELECT
    description,
    COUNT(*) AS row_count
FROM staging_conditions
WHERE LOWER(description) LIKE '%hypertension%'
GROUP BY description
ORDER BY row_count DESC;

-- Chronic kidney disease / renal disease
SELECT
    description,
    COUNT(*) AS row_count
FROM staging_conditions
WHERE LOWER(description) LIKE '%chronic kidney%'
   OR LOWER(description) LIKE '%kidney disease%'
   OR LOWER(description) LIKE '%renal%'
   OR LOWER(description) LIKE '%ckd%'
GROUP BY description
ORDER BY row_count DESC;

------------------------------------------------------------
-- 8. BMI inspection in staging_observations
--    Used to determine whether BMI lands in measurement
------------------------------------------------------------
SELECT
    description,
    COUNT(*) AS row_count
FROM staging_observations
WHERE LOWER(description) LIKE '%body mass index%'
   OR LOWER(description) LIKE '%bmi%'
GROUP BY description
ORDER BY row_count DESC;

SELECT
    date,
    patient,
    description,
    value,
    units,
    type
FROM staging_observations
WHERE LOWER(description) LIKE '%body mass index%'
   OR LOWER(description) LIKE '%bmi%'
LIMIT 20;

------------------------------------------------------------
-- 9. HbA1c inspection in staging_observations
--    Used to determine whether HbA1c lands in measurement
------------------------------------------------------------
SELECT
    description,
    COUNT(*) AS row_count
FROM staging_observations
WHERE LOWER(description) LIKE '%a1c%'
   OR LOWER(description) LIKE '%hba1c%'
   OR LOWER(description) LIKE '%hemoglobin a1c%'
GROUP BY description
ORDER BY row_count DESC;

SELECT
    date,
    patient,
    description,
    value,
    units,
    type
FROM staging_observations
WHERE LOWER(description) LIKE '%a1c%'
   OR LOWER(description) LIKE '%hba1c%'
   OR LOWER(description) LIKE '%hemoglobin a1c%'
LIMIT 20;

------------------------------------------------------------
-- 10. HbA1c date vs T2D condition date inspection
------------------------------------------------------------
SELECT
    pm.person_id,
    so.date::date AS hba1c_date,
    sc.start_time::date AS t2d_condition_start_date,
    so.description AS hba1c_description,
    sc.description AS t2d_description
FROM staging_observations so
JOIN patient_map pm
    ON so.patient = pm.synthea_patient_id
JOIN staging_conditions sc
    ON so.patient = sc.patient
WHERE (
        LOWER(so.description) LIKE '%a1c%'
     OR LOWER(so.description) LIKE '%hba1c%'
     OR LOWER(so.description) LIKE '%hemoglobin a1c%'
      )
  AND (
        LOWER(sc.description) LIKE '%diabetes mellitus type 2%'
     OR LOWER(sc.description) LIKE '%due to type 2 diabetes%'
      )
LIMIT 50;

------------------------------------------------------------
-- 11. Sample final-table rows for manual sanity checking
------------------------------------------------------------

-- Sample T2D rows
SELECT *
FROM condition_occurrence
WHERE condition_concept_id = 201826
LIMIT 10;

-- Sample measurement rows
SELECT *
FROM measurement
LIMIT 10;

-- Sample observation rows
SELECT *
FROM observation
LIMIT 10;