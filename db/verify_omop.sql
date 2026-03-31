-- verify_omop.sql
-- Sprint 1 database sanity checks for RWE-Gen

SELECT current_database() AS database_name;

-- Core table row counts
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

-- Mapping support tables
SELECT COUNT(*) AS patient_map_count FROM patient_map;
SELECT COUNT(*) AS encounter_map_count FROM encounter_map;

-- Staging support tables
SELECT COUNT(*) AS staging_patients_count FROM staging_patients;
SELECT COUNT(*) AS staging_encounters_count FROM staging_encounters;
SELECT COUNT(*) AS staging_conditions_count FROM staging_conditions;
SELECT COUNT(*) AS staging_medications_count FROM staging_medications;
SELECT COUNT(*) AS staging_observations_count FROM staging_observations;

-- T2D verification
SELECT COUNT(*) AS t2d_count
FROM condition_occurrence
WHERE condition_concept_id = 201826;

-- Condition concept breakdown
SELECT condition_concept_id, COUNT(*) AS row_count
FROM condition_occurrence
GROUP BY condition_concept_id
ORDER BY row_count DESC, condition_concept_id;

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