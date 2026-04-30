"""
main.py — FastAPI app built on 's RWEGenAPI facade.

ARCHITECTURE
────────────
Sprint 1 (stub):   3 hardcoded mock endpoints.
Sprint 2 (prev):   imported ProtocolLLMGenerator / AthenaConceptResolver
                   directly and constructed them manually.
Sprint 2 (now):    this layer owns only HTTP concerns — Pydantic validation,
                   CORS, PipelineStageError → status code mapping. All
                   pipeline work is delegated to app.state.rwe (RWEGenAPI).

ENDPOINT → FACADE MAPPING
─────────────────────────
/generate-protocol  → rwe.generate_protocol(question)
/validate-concepts  → rwe.map_protocol(protocol_dict)
/execute-query      → rwe.populate_sql(protocol) + Laya's psycopg2 runner (Sprint 3)

TWO PRAGMATIC WORKAROUNDS (remove once  extends the facade)
──────────────────────────────────────────────────────────────────
1. LOF credentials via env vars.
   llm/concept_mapping_module._build_remote_client() reads
   client_id / client_secret from os.getenv(). PipelineSettings does not
   expose these fields, so we copy them from our Settings into os.environ
   (setdefault, so explicit env wins) before constructing RWEGenAPI.

2. Eager warmup through a private accessor.
   RWEGenAPI lazy-inits the concept mapper on first call (CONCEPT.csv is
   ~5M rows, 10-30s to load). We force the load at startup by calling
   _get_concept_mapping_resolver(). Replace with rwe.warmup() when 
   exposes one.
"""

import asyncio
import json
import os
import sys
import time
import logging
from contextlib import asynccontextmanager
from typing import Any

import psycopg2
from psycopg2 import pool as pg_pool
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from config import get_settings
from schemas import (
    ProtocolRequest,
    ConceptValidationRequest,
    ConceptValidationResponse,
    ValidatedConcept,
    ExecuteQueryRequest,
    ExecuteQueryResponse,
    CohortResult,
    ErrorResponse,
)

_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "llm"))

from llm.api import RWEGenAPI, PipelineSettings, PipelineStageError
from llm.llm_module import VeniceModelConfig

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("rwe_gen")


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN — build RWEGenAPI once at startup, warm the concept mapper
# ─────────────────────────────────────────────────────────────────────────────

def _parse_models(spec: str) -> list[VeniceModelConfig]:
    """Mirror llm/cli.py::parse_models() verbatim so env and CLI parse identically.

    Empty string → 's default pair [zai-org-glm-5:2, kimi-k2-5:2].
    Otherwise each CSV item is `name` or `name:retries` (retries default 2).
    """
    raw_models = [s.strip() for s in spec.split(",") if s.strip()]
    if not raw_models:
        return [
            VeniceModelConfig(name="zai-org-glm-5", retries=2),
            VeniceModelConfig(name="kimi-k2-5", retries=2),
        ]
    parsed: list[VeniceModelConfig] = []
    for raw in raw_models:
        if ":" in raw:
            name, retries_text = raw.split(":", 1)
            parsed.append(VeniceModelConfig(name=name.strip(), retries=int(retries_text.strip())))
        else:
            parsed.append(VeniceModelConfig(name=raw.strip(), retries=2))
    return parsed


def _build_pipeline_settings(s) -> PipelineSettings:
    """Translate our pydantic Settings into 's dataclass.

    Field mapping matches llm/cli.py::build_settings() one-for-one so the HTTP
    backend and 's CLI produce identical runs for identical inputs.

    Notes:
      - lof_base_url → athena_api_base_url (legacy naming on 's side)
      - lof_token_path / imo_normalize_path are NOT on PipelineSettings today.
        AthenaApiConfig defaults ("/generate-access-token/", "/imo/normalize")
        match our config defaults, so this is fine unless someone needs to
        override them.
    """
    return PipelineSettings(
        schema_path=s.schema_path,

        # --- LLM / Venice (matches --venice-* and --llm-verifier-* CLI flags) ---
        venice_api_key=s.venice_api_key,
        venice_base_url=s.venice_base_url,
        venice_timeout_seconds=s.venice_timeout_seconds,
        venice_models=_parse_models(s.venice_models),
        llm_mock_protocol_path=s.llm_mock_protocol_path,
        include_venice_system_prompt=s.include_venice_system_prompt,
        llm_semantic_verification_enabled=s.llm_semantic_verification_enabled,
        llm_verification_models=_parse_models(s.llm_verifier_models),
        llm_verification_timeout_seconds=s.llm_verifier_timeout_seconds,

        # --- Concept mapping / LOF / IMO (matches --athena-* / --concept-mapping-source) ---
        athena_api_base_url=s.lof_base_url,
        athena_api_timeout_seconds=s.lof_timeout_seconds,
        athena_api_enabled=s.concept_mapping_source != "local",
        athena_concept_csv_path=s.athena_concept_csv_path,
        athena_concept_relationship_csv_path=s.athena_concept_relationship_csv_path,
        athena_concept_synonym_csv_path=s.athena_concept_synonym_csv_path,
        athena_candidate_limit=s.athena_candidate_limit,
        athena_ambiguity_delta=s.athena_ambiguity_delta,
        athena_minimum_match_score=s.athena_minimum_match_score,
        athena_prefer_local=s.concept_mapping_source == "local",
        concept_mapping_source=s.concept_mapping_source,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RWE-Gen API starting up")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Concept mapping source: {settings.concept_mapping_source}")

    # Workaround 1: inject LOF creds into env so _build_remote_client
    # picks them up. setdefault — explicit env vars still win.
    if settings.lof_client_id:
        os.environ.setdefault("client_id", settings.lof_client_id)
    if settings.lof_client_secret:
        os.environ.setdefault("client_secret", settings.lof_client_secret)

    try:
        app.state.rwe = RWEGenAPI(_build_pipeline_settings(settings))
        logger.info("RWEGenAPI initialized — Venice LLM ready")
    except Exception as exc:
        logger.error(f"Failed to initialize RWEGenAPI: {exc}")
        raise

    # Workaround 2: force lazy concept-mapper init at startup so the first
    # request doesn't pay the CONCEPT.csv load cost.
    if not settings.skip_concept_warmup:
        try:
            resolver = app.state.rwe._get_concept_mapping_resolver()
            remote = getattr(resolver, "remote_client", None)
            if remote:
                logger.info(
                    f"Concept mapper ready — LOF remote at "
                    f"{remote.get('base_url', 'unknown')}"
                )
            else:
                logger.warning(
                    f"Concept mapper ready — LOF credentials not found, "
                    f"local-only fallback (source_mode={settings.concept_mapping_source}). "
                    f"Set LOF_CLIENT_ID and LOF_CLIENT_SECRET to enable remote IMO."
                )
        except PipelineStageError as exc:
            logger.error(f"Concept mapper init failed — {exc.stage}/{exc.kind}: {exc}")
            raise
    else:
        logger.warning(
            "Concept mapper warmup skipped (SKIP_CONCEPT_WARMUP=true). "
            "Concept mapping will lazy-load on first /validate-concepts call."
        )

    # Postgres connection pool for /execute-query. Small pool — single backend
    # process, queries are short-lived. Fails fast if the DB is unreachable
    # rather than deferring the error to the first request.
    try:
        app.state.db_pool = pg_pool.SimpleConnectionPool(
            minconn=1, maxconn=5, dsn=settings.database_url
        )
        logger.info("Postgres connection pool ready")
    except psycopg2.Error as exc:
        logger.error(f"Postgres pool init failed: {exc}")
        raise

    yield

    logger.info("RWE-Gen API shutting down")
    if getattr(app.state, "db_pool", None) is not None:
        app.state.db_pool.closeall()


# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RWE-Gen API",
    description=(
        "AI-Powered Real-World Evidence Generator. "
        "Venice LLM → LOF/IMO concept mapping → OMOP PostgreSQL execution. "
        "HTTP facade over RWEGenAPI."
    ),
    version="0.3.0-rwegenapi",
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
# PipelineStageError → HTTP status mapping
# ─────────────────────────────────────────────────────────────────────────────

# (stage, kind) → (http_status, recoverable). Unknown kinds fall through to
# the default at the bottom of _stage_error_to_response.
_STAGE_KIND_STATUS: dict[tuple[str, str], tuple[int, bool]] = {
    # LLM / interpretation stage
    ("llm", "schema_file_missing"):                      (500, False),
    ("llm", "schema_file_invalid"):                      (500, False),
    ("llm", "mock_file_missing"):                        (500, False),
    ("llm", "mock_file_invalid"):                        (500, False),
    ("llm", "empty_question"):                           (422, True),
    ("llm", "non_clinical"):                             (422, True),
    ("llm", "input_error"):                              (422, True),
    ("llm", "authentication"):                           (500, False),
    ("llm", "timeout"):                                  (504, True),
    ("llm", "network"):                                  (502, True),
    ("llm", "all_models_failed"):                        (502, True),
    # Verifier stage (only fires when llm_semantic_verification_enabled=True)
    ("llm", "verification_reasoning_formatter_failed"):  (502, True),
    # Concept mapping stage
    ("athena", "remote_forced_unavailable"):             (503, False),
    ("athena", "imo_not_configured"):                    (503, False),
    ("athena", "schema_validation"):                     (422, True),
    # SQL population stage (omop_sql_module.SqlPopulationError kinds)
    ("sql", "protocol_not_executable"):                  (422, True),
    ("sql", "protocol_not_ready"):                       (422, True),
    ("sql", "unsupported_study_type"):                   (422, False),
    ("sql", "unmapped_concept"):                         (422, True),
    ("sql", "missing_concept_ref"):                      (422, True),
    ("sql", "unsupported_event_type"):                   (422, False),
    ("sql", "unsupported_criterion"):                    (422, False),
    ("sql", "invalid_incidence_protocol"):               (422, True),
}


def _stage_error_to_response(exc: PipelineStageError) -> JSONResponse:
    http_status, recoverable = _STAGE_KIND_STATUS.get(
        (exc.stage, exc.kind),
        (status.HTTP_500_INTERNAL_SERVER_ERROR, True),
    )
    return JSONResponse(
        status_code=http_status,
        content=ErrorResponse(
            error_code=exc.kind.upper(),
            message=str(exc),
            recoverable=recoverable,
            stage=exc.stage,
            details=exc.details,
        ).model_dump(),
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
    return {
        "status": "ok",
        "sprint": "2",
        "version": "0.3.0-rwegenapi",
        "llm_provider": "venice",
        "concept_mapping": settings.concept_mapping_source,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1 — POST /generate-protocol
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
    logger.info(f"generate_protocol — question: '{request.question[:80]}'")

    try:
        protocol = http_request.app.state.rwe.generate_protocol(
            request.question, verify=request.verify
        )
    except PipelineStageError as exc:
        logger.error(f"generate_protocol — {exc.stage}/{exc.kind}: {exc}")
        return _stage_error_to_response(exc)

    logger.info(
        f"generate_protocol — success, study_type={protocol.get('study_type')}, "
        f"concept_sets={len(protocol.get('concept_sets', []))}"
    )
    return protocol


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1b — POST /generate-protocol/stream
#
# SSE variant of /generate-protocol. Emits one event per pipeline stage so
# the frontend can render a live stepper. The existing /generate-protocol
# endpoint is unchanged — CLI callers and smoke tests keep using it.
#
# Bridge pattern: sync pipeline runs in a thread via asyncio.to_thread so the
# event loop stays free. The on_progress callback calls queue.put_nowait which
# is thread-safe. The async generator drains the queue, yielding keepalive
# comments every 15 s so proxies don't close idle connections.
#
# SSE frame format: "event: {name}\ndata: {json}\n\n"
# Keepalive format: ": keepalive\n\n"  (SSE comment — browsers ignore it)
# ─────────────────────────────────────────────────────────────────────────────

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
_HEARTBEAT_SECONDS = 15


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@app.post(
    "/generate-protocol/stream",
    tags=["pipeline"],
    summary="Step 1 (streaming) — protocol generation with per-stage SSE events",
)
async def stream_generate_protocol(
    http_request: Request,
    request: ProtocolRequest,
):
    rwe = http_request.app.state.rwe
    queue: asyncio.Queue = asyncio.Queue()

    def _callback(event: dict) -> None:
        queue.put_nowait(event)

    async def _event_stream():
        yield _sse("received", {})

        task = asyncio.create_task(
            asyncio.to_thread(
                rwe.generate_protocol,
                request.question,
                verify=request.verify,
                on_progress=_callback,
            )
        )

        while not task.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
                yield _sse(event["event"], {k: v for k, v in event.items() if k != "event"})
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

        # Drain any events the callback queued after the task finished
        while not queue.empty():
            event = queue.get_nowait()
            yield _sse(event["event"], {k: v for k, v in event.items() if k != "event"})

        exc = task.exception()
        if exc is None:
            yield _sse("done", task.result())
        else:
            if isinstance(exc, PipelineStageError):
                http_status, recoverable = _STAGE_KIND_STATUS.get(
                    (exc.stage, exc.kind),
                    (status.HTTP_500_INTERNAL_SERVER_ERROR, True),
                )
                yield _sse("error", {
                    "error_code": exc.kind.upper(),
                    "message": str(exc),
                    "recoverable": recoverable,
                    "stage": exc.stage,
                    "details": exc.details,
                })
            else:
                logger.error(f"stream_generate_protocol — unhandled: {exc}")
                yield _sse("error", {
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred.",
                    "recoverable": True,
                })

    return StreamingResponse(_event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2 — POST /validate-concepts
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/validate-concepts",
    status_code=status.HTTP_200_OK,
    tags=["pipeline"],
    summary="Step 2 — Map clinical terms to OMOP concept IDs (LOF/IMO + local fallback)",
)
async def validate_concepts(
    http_request: Request,
    request: ConceptValidationRequest,
) -> ConceptValidationResponse:
    logger.info(
        f"validate_concepts — concept_sets={len(request.protocol.get('concept_sets', []))}"
    )

    try:
        mapped_protocol = http_request.app.state.rwe.map_protocol(request.protocol)
    except PipelineStageError as exc:
        logger.error(f"validate_concepts — {exc.stage}/{exc.kind}: {exc}")
        return _stage_error_to_response(exc)

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
#
# Pipeline:
#   1. rwe.populate_sql(protocol)   — Simon's OmopSqlTemplatePopulator builds
#      a fully-inlined SQL string. Concept IDs are baked into the SQL text
#      (see omop_sql_module._csv); SqlBuildResult.parameters is metadata only,
#      not psycopg2 bind params. So we pass sql_result.sql to cur.execute()
#      with no parameter tuple.
#   2. Run against the OMOP Postgres via the lifespan-owned pool.
#   3. Marshal each returned row into a CohortResult. Both templates share the
#      first two columns (population_label, cohort_size); the rest are
#      template-specific and the populator simply omits the ones that don't
#      apply, so we map by column name from cursor.description.
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/execute-query",
    response_model=ExecuteQueryResponse,
    status_code=status.HTTP_200_OK,
    tags=["pipeline"],
    summary="Step 3 — Execute validated OMOP query against PostgreSQL",
)
async def execute_query(
    http_request: Request,
    request: ExecuteQueryRequest,
) -> ExecuteQueryResponse:
    logger.info(
        f"execute_query — study_type={request.protocol.get('study_type')}, "
        f"concepts={len(request.validated_concepts)}"
    )

    protocol_ready = request.protocol.get("execution", {}).get("ready_for_execution")
    if not protocol_ready:
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

    try:
        sql_result = http_request.app.state.rwe.populate_sql(request.protocol)
    except PipelineStageError as exc:
        logger.error(f"execute_query — sql population: {exc.kind}: {exc}")
        return _stage_error_to_response(exc)

    logger.info(
        f"execute_query — built SQL template={sql_result.template_name}, "
        f"chars={len(sql_result.sql)}"
    )

    start_ms = time.time()
    db_pool = http_request.app.state.db_pool
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql_result.sql)
            columns = [desc[0] for desc in cur.description]
            raw_rows = cur.fetchall()
        conn.commit()
    except psycopg2.Error as exc:
        conn.rollback()
        logger.error(f"execute_query — psycopg2 error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error_code="DB_EXECUTION_FAILED",
                message=str(exc),
                recoverable=True,
                stage="backend",
                details={"template": sql_result.template_name},
            ).model_dump(),
        )
    finally:
        db_pool.putconn(conn)

    elapsed_ms = max(int((time.time() - start_ms) * 1000), 1)

    cohorts = [CohortResult(**dict(zip(columns, row))) for row in raw_rows]
    logger.info(
        f"execute_query — success, rows={len(cohorts)}, elapsed_ms={elapsed_ms}"
    )

    return ExecuteQueryResponse(
        template_name=sql_result.template_name,
        cohorts=cohorts,
        query_time_ms=elapsed_ms,
    )
