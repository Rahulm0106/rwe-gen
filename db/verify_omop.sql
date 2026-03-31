
-- verify_omop.sql
-- Sprint 1 database sanity checks for RWE-Gen

SELECT current_database();

-- Core table row counts
SELECT COUNT(*) AS person_count FROM person;
SELECT COUNT(*) AS concept_count FROM concept;
SELECT COUNT(*) AS visit_occurrence_count FROM visit_occurrence;
SELECT COUNT(*) AS condition_occurrence_count FROM condition_occurrence;
SELECT COUNT(*) AS drug_exposure_count FROM drug_exposure;
SELECT COUNT(*) AS observation_count FROM observation;
SELECT COUNT(*) AS measurement_count FROM measurement;

-- Mapping support tables
SELECT COUNT(*) AS patient_map_count FROM patient_map;
SELECT COUNT(*) AS encounter_map_count FROM encounter_map;

-- T2D verification
SELECT COUNT(*) AS t2d_count
FROM condition_occurrence
WHERE condition_concept_id = 201826;

-- Condition concept breakdown
SELECT condition_concept_id, COUNT(*) AS row_count
FROM condition_occurrence
GROUP BY condition_concept_id
ORDER BY condition_concept_id;

-- Sample check
SELECT *
FROM condition_occurrence
WHERE condition_concept_id = 201826
LIMIT 10;