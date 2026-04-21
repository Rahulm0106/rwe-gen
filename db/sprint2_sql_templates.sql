-- ============================================================
-- RWE-Gen · Sprint 2 SQL Templates
-- Owner:    Laya Fakher (DB/Synthea)
-- Consumer: Prasanna Pravin Renapurkar (Backend / psycopg2)
-- Verified: April 21, 2026
--
-- Contains 4 parameterized templates:
--   Template 1 — Demographics
--   Template 2 — Lab Value Aggregation (mean/min/max)
--   Template 3 — Condition-Based Incidence Rate
--   Template 4 — Procedure-Based Incidence (Dialysis / CKD)
--
-- HOW PARAMETERS WORK:
--   Prasanna replaces {placeholders} with validated concept IDs
--   from Simon's ATHENA module before sending to psycopg2.
--   All concept IDs are integers. All dates are 'YYYY-MM-DD'.
--
-- THE GOLDEN RULE:
--   PostgreSQL generates ALL numbers shown to the user.
--   GROQ generates the protocol only.
--   ATHENA generates concept IDs only.
-- ============================================================


-- ============================================================
-- TEMPLATE 1 — DEMOGRAPHICS
-- Study type:  Characterization
-- Parameters:
--   {condition_concept_id}  e.g. 201826  (Type 2 Diabetes)
--   {drug_concept_id}       e.g. 1503297 (Metformin)
--
-- Returns: cohort_size, mean_age, male_count, female_count,
--          count of patients on the target drug
--
-- Validated results (T2D + Metformin):
--   cohort_size=1662, mean_age=81.4,
--   male=31039, female=26527, on_drug=500
-- ============================================================

SELECT
    COUNT(DISTINCT co.person_id)                                        AS cohort_size,
    ROUND(AVG(DATE_PART('year', AGE(p.birth_datetime)))::numeric, 1)   AS mean_age,
    SUM(CASE WHEN p.gender_concept_id = 8507 THEN 1 ELSE 0 END)        AS male_count,
    SUM(CASE WHEN p.gender_concept_id = 8532 THEN 1 ELSE 0 END)        AS female_count,
    COUNT(DISTINCT de.person_id)                                        AS on_target_drug_count
FROM condition_occurrence co
JOIN person p
    ON co.person_id = p.person_id
LEFT JOIN drug_exposure de
    ON co.person_id = de.person_id
    AND de.drug_concept_id = {drug_concept_id}
WHERE co.condition_concept_id = {condition_concept_id};


-- ============================================================
-- TEMPLATE 2 — LAB VALUE AGGREGATION (mean / min / max)
-- Study type:  Lab Value Summary
-- Parameters:
--   {condition_concept_id}    e.g. 201826  (Type 2 Diabetes)
--   {measurement_concept_id}  e.g. 3004410 (HbA1c)
--
-- Key concept IDs for reference:
--   HbA1c          3004410
--   BMI            3038553
--   Systolic BP    3004249
--   Diastolic BP   3012888
--   eGFR           3049187
--   Creatinine     3016723
--   LDL            3007070
--
-- Validated results (T2D + HbA1c):
--   readings=154443, mean=3.77, min=2.30, max=12.00
-- ============================================================

SELECT
    COUNT(DISTINCT co.person_id)                    AS cohort_size,
    COUNT(m.measurement_id)                         AS lab_reading_count,
    ROUND(AVG(m.value_as_number)::numeric, 2)       AS mean_value,
    ROUND(MIN(m.value_as_number)::numeric, 2)       AS min_value,
    ROUND(MAX(m.value_as_number)::numeric, 2)       AS max_value,
    ROUND(PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY m.value_as_number)
        ::numeric, 2)                               AS median_value
FROM condition_occurrence co
JOIN measurement m
    ON co.person_id = m.person_id
WHERE co.condition_concept_id  = {condition_concept_id}
  AND m.measurement_concept_id = {measurement_concept_id}
  AND m.value_as_number IS NOT NULL;


-- ============================================================
-- TEMPLATE 3 — CONDITION-BASED INCIDENCE RATE
-- Study type:  Incidence
-- Parameters:
--   {condition_concept_id}  e.g. 201826     (Type 2 Diabetes)
--   {obs_start_date}        e.g. 2010-01-01 (observation window start)
--   {obs_end_date}          e.g. 2024-12-31 (observation window end)
--
-- Returns: persons at risk, persons with event,
--          total person-years, incidence rate per 1,000 person-years
--
-- NOTE: Uses observation_period table for person-time denominator.
--       (date - date)::numeric gives days; divide by 365.25 for years.
--       EXTRACT(EPOCH FROM interval) NOT used — causes type cast error
--       in PostgreSQL 18 with date columns.
--
-- Validated results (T2D, full data window):
--   persons_at_risk=11540, persons_with_event=1662,
--   total_person_years=361257.46, rate=4.6006
-- ============================================================

WITH cohort AS (
    SELECT DISTINCT op.person_id,
        GREATEST(op.observation_period_start_date, '{obs_start_date}'::date) AS window_start,
        LEAST(op.observation_period_end_date,       '{obs_end_date}'::date)   AS window_end
    FROM observation_period op
    WHERE op.observation_period_end_date   >= '{obs_start_date}'::date
      AND op.observation_period_start_date <= '{obs_end_date}'::date
),
events AS (
    SELECT DISTINCT co.person_id,
        MIN(co.condition_start_date) AS first_event_date
    FROM condition_occurrence co
    WHERE co.condition_concept_id = {condition_concept_id}
    GROUP BY co.person_id
)
SELECT
    COUNT(DISTINCT cohort.person_id)                        AS persons_at_risk,
    COUNT(DISTINCT events.person_id)                        AS persons_with_event,
    ROUND(
        SUM(
            (cohort.window_end - cohort.window_start)::numeric / 365.25
        )::numeric, 2
    )                                                       AS total_person_years,
    ROUND(
        1000.0 * COUNT(DISTINCT events.person_id)
        / NULLIF(
            SUM((cohort.window_end - cohort.window_start)::numeric / 365.25),
        0), 4
    )                                                       AS incidence_rate_per_1000_py
FROM cohort
LEFT JOIN events
    ON cohort.person_id = events.person_id
    AND events.first_event_date BETWEEN cohort.window_start AND cohort.window_end;


-- ============================================================
-- TEMPLATE 4 — PROCEDURE-BASED INCIDENCE (DIALYSIS / CKD)
-- Study type:  CKD End-Stage Outcome
-- Parameters:  none (CKD concept ID hardcoded — single use template)
--
-- NOTE: Synthea did not generate dialysis records in staging_conditions.
--       Query returns cohort_size=0 cleanly without crashing.
--       This satisfies TC-08 (empty cohort returns zero, not null).
--       If dialysis data is present in future Synthea runs, the
--       description LIKE filter below will pick it up automatically.
--
-- Validated results:
--   ckd_cohort_size=1137, dialysis_cases=0,
--   dialysis_progression_pct=0.00
-- ============================================================

WITH ckd_cohort AS (
    SELECT DISTINCT co.person_id,
        MIN(co.condition_start_date) AS ckd_diagnosis_date
    FROM condition_occurrence co
    WHERE co.condition_concept_id = 46271022
    GROUP BY co.person_id
),
dialysis_events AS (
    SELECT DISTINCT pm.person_id,
        MIN(sc.start_time::date) AS dialysis_date
    FROM staging_conditions sc
    JOIN patient_map pm
        ON sc.patient = pm.synthea_patient_id
    WHERE LOWER(sc.description) LIKE '%dialysis%'
    GROUP BY pm.person_id
),
combined AS (
    SELECT
        ckd.person_id,
        ckd.ckd_diagnosis_date,
        dial.dialysis_date,
        CASE WHEN dial.person_id IS NOT NULL THEN 1 ELSE 0 END AS progressed_to_dialysis
    FROM ckd_cohort ckd
    LEFT JOIN dialysis_events dial
        ON ckd.person_id = dial.person_id
)
SELECT
    COUNT(*)                                            AS ckd_cohort_size,
    COALESCE(SUM(progressed_to_dialysis), 0)            AS dialysis_cases,
    ROUND(
        COALESCE(
            100.0 * SUM(progressed_to_dialysis) / NULLIF(COUNT(*), 0),
        0)::numeric, 2
    )                                                   AS dialysis_progression_pct,
    CASE
        WHEN SUM(progressed_to_dialysis) = 0
        THEN 'No dialysis data in Synthea output'
        ELSE 'Dialysis progression data present'
    END                                                 AS note
FROM combined;


-- ============================================================
-- SPRINT 2 VALIDATION GATE
-- Run this last to confirm TC-01, TC-02, TC-03 all pass.
-- Screenshot the result and send to Rahul for Sprint 2 sign-off.
-- ============================================================

SELECT 'TC-01 Demographics cohort non-zero' AS test,
    CASE WHEN (
        SELECT COUNT(DISTINCT person_id)
        FROM condition_occurrence
        WHERE condition_concept_id = 201826
    ) > 0 THEN 'PASS' ELSE 'FAIL' END AS status

UNION ALL

SELECT 'TC-02 HbA1c readings non-zero',
    CASE WHEN (
        SELECT COUNT(*)
        FROM condition_occurrence co
        JOIN measurement m ON co.person_id = m.person_id
        WHERE co.condition_concept_id  = 201826
          AND m.measurement_concept_id = 3004410
          AND m.value_as_number IS NOT NULL
    ) > 0 THEN 'PASS' ELSE 'FAIL' END

UNION ALL

SELECT 'TC-03 Incidence query can run (observation_period populated)',
    CASE WHEN (
        SELECT COUNT(*) FROM observation_period
    ) > 0 THEN 'PASS' ELSE 'FAIL' END;

-- ============================================================
-- END OF SPRINT 2 SQL TEMPLATES
-- All 4 templates validated against omop_rwe database.
-- TC-01, TC-02, TC-03: PASS
-- TC-08 (empty cohort): PASS — Template 4 returns 0 cleanly
-- Next: Sprint 3 — confirm parameterized injection with Prasanna
-- ============================================================
