"""
config.py — Application configuration for the updated architecture.

WHAT CHANGED FROM SPRINT 1
───────────────────────────
Sprint 1 had:  GROQ_API_KEY, single LLM config
Now we have:   Venice API (LLM), LOF/IMO proxy (concept mapping primary),
               CONCEPT.csv local vocab (concept mapping fallback),
               protocol_schema_validator.json path

KEY DESIGN DECISION — env var names vs Simon's auto-detection
──────────────────────────────────────────────────────────────
Simon's concept_mapping_module reads LOF credentials via os.getenv() with
multiple fallback names: client_id / CLIENT_ID / IMO_CLIENT_ID / IMO_API_KEY.
This config.py uses explicit field names (lof_client_id, lof_client_secret)
and passes them directly when constructing AthenaConceptResolver — so we never
rely on Simon's env var auto-detection. This avoids hidden env var mismatches.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ── Venice LLM ────────────────────────────────────────────────────────────
    # Primary LLM provider. Models: zai-org-glm-5, kimi-k2-5 (Simon's defaults).
    venice_api_key: Optional[str] = None
    venice_base_url: str = "https://api.venice.ai/api/v1"
    venice_timeout_seconds: int = 60

    # ── LOF / IMO Normalize (concept mapping — primary path) ──────────────────
    # Leap of Faith proxy credentials for remote IMO Normalize calls.
    # If missing, concept_mapping_module falls back to local vocab silently
    # in "auto" mode, or raises AthenaError in "remote" mode.
    lof_client_id: Optional[str] = None
    lof_client_secret: Optional[str] = None
    lof_base_url: str = "https://api.leapoffaith.com/api/service"
    lof_token_path: str = "/generate-access-token/"
    imo_normalize_path: str = "/imo/normalize"
    lof_timeout_seconds: int = 10

    # concept_mapping_source controls which path is used:
    #   "auto"   — remote first, local fallback if remote fails/no result
    #   "local"  — local vocabulary only (no network calls)
    #   "remote" — remote only, raise error if credentials missing
    concept_mapping_source: str = "auto"

    # ── Local ATHENA vocabulary (concept mapping — fallback path) ─────────────
    # CONCEPT.csv is still needed even in remote mode because IMO returns
    # SNOMED/RxNorm codes and those must be resolved to OMOP concept_ids locally.
    # Set these to empty string if local vocab is not available — module will
    # raise AthenaError only when local path is actually attempted.
    athena_concept_csv_path: str = ""
    athena_concept_relationship_csv_path: str = ""
    athena_concept_synonym_csv_path: Optional[str] = None
    athena_candidate_limit: int = 5
    athena_ambiguity_delta: int = 15
    athena_minimum_match_score: int = 120

    # ── Protocol schema validator ─────────────────────────────────────────────
    # Simon's LLMConfig requires this file at startup.
    # ProtocolLLMGenerator.__init__ raises LLMError(kind="schema_file_missing")
    # if this path points to a non-existent file.
    schema_path: str = "protocol_schema_validator.json"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql://rwe_user:rwe_dev_password@localhost:5432/omop_rwe"
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
