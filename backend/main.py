"""
main.py — FastAPI application with Venice LLM + LOF/IMO concept mapping.

ARCHITECTURE CHANGE FROM SPRINT 1
────────────────────────────────────
Sprint 1: 3 stub endpoints returning hardcoded mock data.
Sprint 2: Real module calls using Simon's ProtocolLLMGenerator (Venice) and
          AthenaConceptResolver (LOF/IMO remote + local fallback).

MODULE INITIALIZATION STRATEGY
────────────────────────────────
Both ProtocolLLMGenerator and AthenaConceptResolver are initialized ONCE
at startup in the lifespan context manager and stored on app.state.

Why not initialize per-request?
  - LocalAthenaVocabulary loads CONCEPT.csv (~5M rows) into memory at init.
    Doing this on every request would add 10-30 seconds per call.
  - ProtocolLLMGenerator loads and validates the JSON schema at init.
  - Both are thread-safe for concurrent reads once initialized.

ENDPOINT → MODULE MAPPING
──────────────────────────
/generate-protocol  → ProtocolLLMGenerator.generate_protocol(question)
/validate-concepts  → AthenaConceptResolver.map_protocol(protocol_dict)
/execute-query      → Laya's psycopg2 SQL templates (Sprint 2/3)
"""

import json
import time
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from schemas import (
    ProtocolRequest,
    ProtocolResponse,
    ConceptValidationRequest,
    ConceptValidationResponse,
    ValidatedConcept,
    ExecuteQueryRequest,
    ExecuteQueryResponse,
    Demographics,
    AgeGroupBreakdown,
    SexBreakdown,
    LabSummary,
    ErrorResponse,
)

# Simon's modules — import from the llm/ subfolder
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from llm.llm_module import ProtocolLLMGenerator, LLMConfig, LLMError, VeniceModelConfig
from llm.concept_mapping_module import (
    AthenaConceptResolver,
    AthenaApiConfig,
    LocalVocabularyConfig,
    AthenaError,
)

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("rwe_gen")


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN — initialize heavy modules once at startup
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RWE-Gen API starting up")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Concept mapping source: {settings.concept_mapping_source}")

    # ── Initialize Venice LLM generator ──────────────────────────────────────
    try:
        app.state.llm = ProtocolLLMGenerator(
            LLMConfig(
                schema_path=settings.schema_path,
                api_key=settings.venice_api_key,
                base_url=settings.venice_base_url,
                timeout_seconds=settings.venice_timeout_seconds,
                # Use Simon's default model order: zai-org-glm-5 → kimi-k2-5
                # Override via config if needed in future
            )
        )
        logger.info("✅ Venice LLM generator initialized")
    except LLMError as exc:
        logger.error(f"❌ Failed to initialize LLM generator: {exc}")
        raise

    # ── Initialize concept mapper (LOF/IMO + local fallback) ─────────────────
    # We pass LOF credentials explicitly from config rather than relying on
    # Simon's os.getenv() auto-detection — avoids env var naming mismatches.
    # Simon's _build_remote_client() reads: client_id / CLIENT_ID / IMO_CLIENT_ID
    # We set these explicitly via environment so his detection works correctly.
    import os
    if settings.lof_client_id:
        os.environ.setdefault("client_id", settings.lof_client_id)
    if settings.lof_client_secret:
        os.environ.setdefault("client_secret", settings.lof_client_secret)

    try:
        app.state.concept_mapper = AthenaConceptResolver(
            schema_path=settings.schema_path,
            api_config=AthenaApiConfig(
                base_url=settings.lof_base_url,
                timeout_seconds=settings.lof_timeout_seconds,
                enabled=True,
                lof_token_path=settings.lof_token_path,
                imo_normalize_path=settings.imo_normalize_path,
                source_mode=settings.concept_mapping_source,
            ),
            local_config=LocalVocabularyConfig(
                concept_csv_path=settings.athena_concept_csv_path,
                concept_relationship_csv_path=settings.athena_concept_relationship_csv_path,
                concept_synonym_csv_path=settings.athena_concept_synonym_csv_path,
                candidate_limit=settings.athena_candidate_limit,
                ambiguity_delta=settings.athena_ambiguity_delta,
                minimum_match_score=settings.athena_minimum_match_score,
            ),
        )
        # Log remote client state so it's visible — avoids silent degradation
        if app.state.concept_mapper.remote_client:
            base = app.state.concept_mapper.remote_client.get("base_url", "unknown")
            logger.info(f"✅ Concept mapper initialized — LOF remote configured at {base}")
        else:
            logger.warning(
                "⚠ Concept mapper initialized — LOF credentials not found. "
                f"Running in local-only fallback (source_mode={settings.concept_mapping_source}). "
                "Set LOF_CLIENT_ID and LOF_CLIENT_SECRET to enable remote IMO path."
            )
    except AthenaError as exc:
        logger.error(f"❌ Failed to initialize concept mapper: {exc}")
        raise

    yield  # server runs here

    logger.info("RWE-Gen API shutting down")


# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RWE-Gen API",
    description=(
        "AI-Powered Real-World Evidence Generator. "
        "Venice LLM → LOF/IMO concept mapping → OMOP PostgreSQL execution."
    ),
    version="0.2.0-sprint2",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL EXCEPTION HANDLER
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again.",
            recoverable=True,
        ).model_dump(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["infra"])
async def health_check():
    """Server health check. Used by CI, Docker, and monitoring."""
    return {
        "status": "ok",
        "sprint": "2",
        "version": "0.2.0-sprint2",
        "llm_provider": "venice",
        "concept_mapping": settings.concept_mapping_source,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1 — POST /generate-protocol
# Calls Simon's ProtocolLLMGenerator via Venice API
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/generate-protocol",
    status_code=status.HTTP_200_OK,
    tags=["pipeline"],
    summary="Step 1 — Convert plain-English question to OMOP study protocol",
)
async def generate_protocol(
    http_request: Request,
    request: ProtocolRequest,
) -> dict[str, Any]:
    """
    Sends the clinical question to Venice LLM, receives a structured
    study protocol JSON validated against protocol_schema_validator.json.

    Returns Simon's full nested protocol dict — not the old flat 6-field shape.
    The protocol has protocol_status="needs_mapping" at this stage.

    HUMAN GATE 1 happens on the frontend: researcher reviews the protocol
    and approves before /validate-concepts is called.
    """
    logger.info(f"generate_protocol — question: '{request.question[:80]}'")

    try:
        protocol = http_request.app.state.llm.generate_protocol(request.question)
        logger.info(
            f"generate_protocol — success, study_type={protocol.get('study_type')}, "
            f"concept_sets={len(protocol.get('concept_sets', []))}"
        )
        return protocol

    except LLMError as exc:
        logger.error(f"generate_protocol — LLMError kind={exc.kind}: {exc}")

        # Map LLM error kinds to meaningful HTTP responses
        if exc.kind in ("schema_file_missing", "schema_file_invalid"):
            # Server misconfiguration — not user error
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
            recoverable = False
        elif exc.kind in ("empty_question", "non_clinical"):
            # User submitted invalid question — tell them to rephrase
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            recoverable = True
        else:
            # LLM failed after retries, model fallback exhausted, etc.
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
            recoverable = True

        return JSONResponse(
            status_code=http_status,
            content=ErrorResponse(
                error_code=exc.kind.upper(),
                message=str(exc),
                recoverable=recoverable,
                stage="llm",
                details=exc.details,
            ).model_dump(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2 — POST /validate-concepts
# Calls Simon's AthenaConceptResolver — LOF/IMO remote first, local fallback
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/validate-concepts",
    status_code=status.HTTP_200_OK,
    tags=["pipeline"],
    summary="Step 2 — Map clinical terms to OMOP concept IDs via LOF/IMO + local fallback",
)
async def validate_concepts(
    http_request: Request,
    request: ConceptValidationRequest,
) -> ConceptValidationResponse:
    """
    Takes the researcher-approved protocol dict and maps every concept_set
    entry to an OMOP concept ID using the LOF/IMO remote path (primary) or
    local CONCEPT.csv vocabulary (fallback).
    """
    logger.info(
        f"validate_concepts — "
        f"concept_sets={len(request.protocol.get('concept_sets', []))}"
    )

    try:
        mapped_protocol = http_request.app.state.concept_mapper.map_protocol(request.protocol)

    except AthenaError as exc:
        logger.error(f"validate_concepts — AthenaError kind={exc.kind}: {exc}")

        if exc.kind in ("remote_forced_unavailable", "imo_not_configured"):
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
            recoverable = False
        elif exc.kind in ("schema_validation",):
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            recoverable = True
        else:
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
            recoverable = True

        return JSONResponse(
            status_code=http_status,
            content=ErrorResponse(
                error_code=exc.kind.upper(),
                message=str(exc),
                recoverable=recoverable,
                stage="athena",
                details=exc.details,
            ).model_dump(),
        )

    # Build convenience lists for the frontend status panel
    mapped: list[ValidatedConcept] = []
    ambiguous: list[dict[str, Any]] = []
    unmatched: list[str] = []

    for cs in mapped_protocol.get("concept_sets", []):
        mapping = cs.get("mapping", {})
        raw_text = cs.get("raw_text", "")
        m_status = mapping.get("status", "unmapped")

        if m_status == "mapped":
            mapped.append(ValidatedConcept(
                name=raw_text,
                concept_id=mapping["omop_concept_id"],
                domain=cs.get("domain", "unknown"),
                vocabulary=mapping.get("omop_concept_name", ""),
                matched=True,
            ))
        elif m_status == "ambiguous":
            ambiguous.append({
                "raw_text": raw_text,
                "concept_ref": cs.get("concept_ref"),
                "candidates": mapping.get("candidate_concepts", []),
            })
        else:
            unmatched.append(raw_text)

    protocol_status = mapped_protocol.get("protocol_status", "blocked")
    logger.info(
        f"validate_concepts — complete. mapped={len(mapped)}, "
        f"ambiguous={len(ambiguous)}, unmatched={len(unmatched)}, "
        f"protocol_status={protocol_status}"
    )

    return ConceptValidationResponse(
        protocol=mapped_protocol,
        mapped=mapped,
        ambiguous=ambiguous,
        unmatched=unmatched,
        protocol_status=protocol_status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3 — POST /execute-query
# Calls Laya's parameterized SQL templates via psycopg2
# Sprint 2: mock data. Sprint 3: real psycopg2 execution.
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/execute-query",
    response_model=ExecuteQueryResponse,
    status_code=status.HTTP_200_OK,
    tags=["pipeline"],
    summary="Step 3 — Execute validated OMOP query against PostgreSQL",
)
async def execute_query(request: ExecuteQueryRequest) -> ExecuteQueryResponse:
    """
    Takes the fully mapped protocol (protocol_status='executable') and executes
    parameterized SQL against the OMOP PostgreSQL database.

    Every number in the response comes from the database — never from the LLM.

    Sprint 2: returns mock data. Replace with real psycopg2 call in Sprint 3.
    Sprint 3 hook:
        from db.query_engine import run_query
        return await run_query(request.protocol, request.validated_concepts)
    """
    logger.info(
        f"execute_query — study_type={request.protocol.get('study_type')}, "
        f"concepts={len(request.validated_concepts)}"
    )

    # Guard: only execute if protocol is marked executable
    protocol_status = request.protocol.get("execution", {}).get("ready_for_execution")
    if not protocol_status:
        p_status = request.protocol.get("protocol_status", "unknown")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error_code="PROTOCOL_NOT_EXECUTABLE",
                message=(
                    f"Protocol status is '{p_status}'. "
                    "All concepts must be mapped and Human Gate 2 must be confirmed "
                    "before execution."
                ),
                recoverable=True,
                stage="backend",
            ).model_dump(),
        )

    start_ms = time.time()

    # ── SPRINT 3 HOOK: replace mock below with real DB call ───────────────────
    mock_demographics = Demographics(
        age_groups=AgeGroupBreakdown(**{"18-30": 42, "31-45": 183, "46-60": 391, "61+": 231}),
        sex=SexBreakdown(male=412, female=429, other=6),
    )
    mock_lab_summaries = [
        LabSummary(lab_name="HbA1c", unit="%", count=724, mean=7.4, min=5.1, max=13.2)
    ]
    elapsed_ms = int((time.time() - start_ms) * 1000)

    return ExecuteQueryResponse(
        cohort_size=847,
        demographics=mock_demographics,
        incidence_rate=12.3,
        incidence_rate_unit="per 1000 person-years",
        lab_summaries=mock_lab_summaries,
        query_time_ms=max(elapsed_ms, 1),
    )
