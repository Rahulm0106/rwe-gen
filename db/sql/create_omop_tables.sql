-- create_omop_tables.sql
-- Minimal OMOP-like schema for Sprint 1 of RWE-Gen
-- Owner: Laya Fakher
-- Purpose:
--   Create the core tables needed for local PostgreSQL setup,
--   Synthea CSV loading, and T2D verification.
--
-- Notes:
--   - This is not a full official OMOP CDM implementation.
--   - It is a simplified Sprint 1 schema for:
--       person
--       concept
--       visit_occurrence
--       condition_occurrence
--       drug_exposure
--       observation
--       measurement
--   - Additional staging/mapping tables are created separately.

-- Drop dependent tables first
DROP TABLE IF EXISTS measurement CASCADE;
DROP TABLE IF EXISTS observation CASCADE;
DROP TABLE IF EXISTS drug_exposure CASCADE;
DROP TABLE IF EXISTS condition_occurrence CASCADE;
DROP TABLE IF EXISTS visit_occurrence CASCADE;
DROP TABLE IF EXISTS concept CASCADE;
DROP TABLE IF EXISTS person CASCADE;

-- =========================
-- person
-- =========================
CREATE TABLE person (
    person_id BIGINT PRIMARY KEY,
    gender_concept_id INTEGER,
    year_of_birth INTEGER,
    month_of_birth INTEGER,
    day_of_birth INTEGER,
    birth_datetime TIMESTAMP,
    race_concept_id INTEGER,
    ethnicity_concept_id INTEGER
);

-- =========================
-- concept
-- =========================
CREATE TABLE concept (
    concept_id INTEGER PRIMARY KEY,
    concept_name TEXT,
    domain_id TEXT,
    vocabulary_id TEXT,
    concept_class_id TEXT,
    standard_concept TEXT,
    concept_code TEXT
);

-- =========================
-- visit_occurrence
-- =========================
CREATE TABLE visit_occurrence (
    visit_occurrence_id BIGINT PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES person(person_id),
    visit_concept_id INTEGER,
    visit_start_date DATE,
    visit_end_date DATE
);

-- =========================
-- condition_occurrence
-- =========================
CREATE TABLE condition_occurrence (
    condition_occurrence_id BIGINT PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES person(person_id),
    condition_concept_id INTEGER,
    condition_start_date DATE,
    condition_end_date DATE,
    visit_occurrence_id BIGINT REFERENCES visit_occurrence(visit_occurrence_id)
);

-- =========================
-- drug_exposure
-- =========================
CREATE TABLE drug_exposure (
    drug_exposure_id BIGINT PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES person(person_id),
    drug_concept_id INTEGER,
    drug_exposure_start_date DATE,
    drug_exposure_end_date DATE,
    visit_occurrence_id BIGINT REFERENCES visit_occurrence(visit_occurrence_id)
);

-- =========================
-- observation
-- =========================
CREATE TABLE observation (
    observation_id BIGINT PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES person(person_id),
    observation_concept_id INTEGER,
    observation_date DATE,
    value_as_string TEXT
);

-- =========================
-- measurement
-- =========================
CREATE TABLE measurement (
    measurement_id BIGINT PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES person(person_id),
    measurement_concept_id INTEGER,
    measurement_date DATE,
    value_as_number NUMERIC
);

-- =========================
-- Helpful indexes
-- =========================
CREATE INDEX idx_visit_occurrence_person_id
    ON visit_occurrence(person_id);

CREATE INDEX idx_condition_occurrence_person_id
    ON condition_occurrence(person_id);

CREATE INDEX idx_condition_occurrence_concept_id
    ON condition_occurrence(condition_concept_id);

CREATE INDEX idx_drug_exposure_person_id
    ON drug_exposure(person_id);

CREATE INDEX idx_observation_person_id
    ON observation(person_id);

CREATE INDEX idx_measurement_person_id
    ON measurement(person_id);