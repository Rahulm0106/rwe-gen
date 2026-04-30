"""
config.py — Backend configuration for the RWEGenAPI-backed FastAPI layer.

DESIGN
──────
Every knob mirrors a flag in Simon's llm/cli.py so the HTTP backend and
his CLI produce identical runs for identical inputs. The mapping from env
var to CLI flag is documented inline next to each field below, and the
translation into Simon's PipelineSettings dataclass happens in
main.py::_build_pipeline_settings().

LOF CREDENTIAL INJECTION
────────────────────────
Simon's concept_mapping_module._build_remote_client() reads LOF credentials
via os.getenv() with multiple fallback names (client_id / CLIENT_ID /
IMO_CLIENT_ID). The backend reads lof_client_id / lof_client_secret from
this Settings object and writes them into os.environ at lifespan startup
(main.py), so his detection logic still works while keeping the env-var
names explicit in our config.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ── Venice LLM ────────────────────────────────────────────────────────────
    # Primary LLM provider. Mirrors Simon's CLI flags in llm/cli.py one-for-one
    # so identical specs produce identical runs between CLI and HTTP backend.
    #
    # CLI flag                       → env var
    # ─────────────────────────────────────────────────────────────
    # --venice-api-key               → VENICE_API_KEY
    # --venice-base-url              → VENICE_BASE_URL
    # --venice-timeout               → VENICE_TIMEOUT_SECONDS
    # --venice-model (repeatable)    → VENICE_MODELS (CSV of name[:retries])
    # --mock-protocol-json           → LLM_MOCK_PROTOCOL_PATH
    # --include-venice-system-prompt → INCLUDE_VENICE_SYSTEM_PROMPT (bool)
    # --enable-semantic-verification → LLM_SEMANTIC_VERIFICATION_ENABLED (bool)
    # --llm-verifier-model (rep.)    → LLM_VERIFIER_MODELS (CSV of name[:retries])
    # --llm-verifier-timeout         → LLM_VERIFIER_TIMEOUT_SECONDS
    #
    # Empty VENICE_MODELS / LLM_VERIFIER_MODELS → Simon's defaults apply
    # (see _parse_models in main.py, which mirrors llm/cli.py::parse_models).
    venice_api_key: Optional[str] = None
    venice_base_url: str = "https://api.venice.ai/api/v1"
    venice_timeout_seconds: int = 60
    venice_models: str = ""                         # CSV, e.g. "zai-org-glm-5:2,kimi-k2-5:1"
    llm_mock_protocol_path: Optional[str] = None
    include_venice_system_prompt: bool = False
    llm_semantic_verification_enabled: bool = False
    llm_verifier_models: str = ""                   # CSV, same format as venice_models
    llm_verifier_timeout_seconds: Optional[int] = None

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
    # RWEGenAPI loads this at startup. A missing file surfaces as
    # PipelineStageError(stage="llm", kind="schema_file_missing"). The default
    # is relative to the uvicorn working dir (backend/); .env pins the canonical
    # repo path.
    # --schema-path
    schema_path: str = "../docs/protocol_schema_validator.json"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql://rwe_user:rwe_dev_password@localhost:5432/omop_rwe"
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    skip_concept_warmup: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
