"""
schemas.py — Pydantic models aligned with Simon's protocol schema.

WHAT CHANGED FROM SPRINT 1
───────────────────────────
ProtocolResponse was a flat 6-field model. It is now replaced with Simon's
full nested protocol structure that matches protocol_schema_validator.json.

The new structure reflects how the LLM pipeline actually works:
  - concept_sets[] holds the clinical terms to be mapped
  - target_cohort / comparator / outcome define the study design
  - execution{} tracks human gate status (review_required, ready_for_execution)
  - protocol_status drives the frontend state machine: needs_mapping → needs_review
    → executable (or blocked)

WHAT DID NOT CHANGE
────────────────────
ErrorResponse, ConceptValidationResponse, ValidatedConcept, ExecuteQueryResponse
are all unchanged — these are independent of the protocol shape.
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST MODELS (what the frontend sends)
# ─────────────────────────────────────────────────────────────────────────────

class ProtocolRequest(BaseModel):
    """Step 1 — researcher types a plain-English clinical question."""
    question: str = Field(..., min_length=10,
                          description="Plain-English clinical research question")


class ConceptValidationRequest(BaseModel):
    """Step 2 — researcher sends the approved protocol for concept mapping.

    WHY A FULL PROTOCOL DICT INSTEAD OF A FLAT LIST OF STRINGS?
    ─────────────────────────────────────────────────────────────
    Simon's map_protocol() processes concept_sets[] inside the protocol.
    Each concept_set has: raw_text, domain, standard_vocab_preference.
    The mapper needs all three to score correctly. A flat string list loses
    the domain and vocab preference, making scoring much less accurate.

    This replaces the old {"concepts": [string]} interface.
    COORDINATE WITH MUKTHA — the frontend request shape changed.
    """
    protocol: dict[str, Any] = Field(
        ...,
        description="The full protocol dict returned by /generate-protocol"
    )


class ExecuteQueryRequest(BaseModel):
    """Step 3 — researcher confirms mappings; backend runs the SQL."""
    protocol: dict[str, Any] = Field(
        ...,
        description="The fully mapped protocol (protocol_status='executable')"
    )
    validated_concepts: list["ValidatedConcept"] = Field(
        ...,
        description="Concept mappings confirmed at Human Gate 2"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROTOCOL RESPONSE — Simon's full nested structure
#
# These models mirror what ProtocolLLMGenerator.generate_protocol() returns.
# We use Optional[Any] liberally for nested dicts because the full schema
# is defined in protocol_schema_validator.json — Pydantic validates the
# envelope; Simon's jsonschema validator checks the protocol internals.
#
# Trade-off: using dict[str, Any] for deeply nested fields keeps this file
# maintainable without duplicating every field from the JSON schema. The
# important thing is that the top-level structure is typed correctly so
# FastAPI can serialize it and the frontend knows what to expect.
# ─────────────────────────────────────────────────────────────────────────────

class ConceptSetMapping(BaseModel):
    """Mapping result for a single clinical term after ATHENA/IMO processing."""
    status: str   # "unmapped" | "ambiguous" | "mapped" | "not_required"
    omop_concept_id: Optional[int] = None
    omop_concept_name: Optional[str] = None
    candidate_concepts: list[dict[str, Any]] = []


class ConceptSet(BaseModel):
    """A single clinical term to be mapped to an OMOP concept ID."""
    concept_ref: str          # internal reference key, e.g. "concept_1"
    raw_text: str             # the original text from the LLM, e.g. "Type 2 diabetes"
    domain: str               # "condition" | "drug" | "procedure" | "measurement"
    standard_vocab_preference: Optional[str] = None   # "SNOMED" | "RxNorm" | "LOINC"
    mapping: ConceptSetMapping = Field(
        default_factory=lambda: ConceptSetMapping(status="unmapped")
    )


class ExecutionFlags(BaseModel):
    """Human gate status and execution readiness flags."""
    human_review_required: bool = True
    human_mapping_confirmation_required: bool = True
    ready_for_execution: bool = False
    sql_template: Optional[str] = None   # "cohort_characterization" | "incidence_analysis"


class IssueList(BaseModel):
    """Warnings and blocking errors from protocol generation or mapping."""
    warnings: list[dict[str, Any]] = []
    blocking_errors: list[dict[str, Any]] = []


class ProtocolResponse(BaseModel):
    """
    The full study protocol returned by /generate-protocol and /validate-concepts.

    protocol_status drives the frontend state machine:
      "needs_mapping"  — just generated, no OMOP IDs yet
      "needs_review"   — some concepts are ambiguous (Human Gate 2 needed)
      "executable"     — all concepts mapped, ready for SQL execution
      "blocked"        — one or more unmapped concepts, cannot proceed

    All nested study design fields (target_cohort, comparator, outcome,
    time_windows) are typed as dict[str, Any] because their internal structure
    is governed by protocol_schema_validator.json, not by these Pydantic models.
    The LLM validator enforces the internal schema; we only need the envelope.
    """
    schema_version: str = "1.0.0"
    original_question: str
    normalized_question: str
    study_type: str   # "cohort_characterization" | "incidence_analysis"
    protocol_status: str = "needs_mapping"

    # Core study design — typed as dict to avoid duplicating the full JSON schema
    target_cohort: dict[str, Any]
    comparator: dict[str, Any]
    outcome: dict[str, Any]
    time_windows: dict[str, Any]

    # Concept sets — these are the clinical terms that go to concept mapping
    concept_sets: list[ConceptSet] = []

    # Execution flags — updated by the mapping stage
    execution: ExecutionFlags = Field(default_factory=ExecutionFlags)

    # Issues — warnings and blocking errors populated by LLM and mapper
    issues: IssueList = Field(default_factory=IssueList)

    # Optional fields that may or may not be present
    assumptions: list[str] = []
    requested_outputs: list[str] = []

    model_config = {"extra": "allow"}   # allow unknown fields from LLM output


# ─────────────────────────────────────────────────────────────────────────────
# CONCEPT VALIDATION RESPONSE
# These are unchanged from Sprint 1 — just the request shape changed above.
# ─────────────────────────────────────────────────────────────────────────────

class ValidatedConcept(BaseModel):
    """A single concept that was successfully mapped."""
    name: str
    concept_id: int
    domain: str
    vocabulary: str
    matched: bool = True


class ConceptValidationResponse(BaseModel):
    """
    The mapped protocol returned by /validate-concepts.

    Returns the full updated protocol dict (with concept_sets populated)
    plus convenience lists for the frontend status panel.
    """
    protocol: dict[str, Any]          # full protocol with mapping statuses applied
    mapped: list[ValidatedConcept]     # concepts that mapped cleanly (green)
    ambiguous: list[dict[str, Any]]    # concepts needing researcher selection (amber)
    unmatched: list[str]              # terms with no match (red — blocks execution)
    protocol_status: str              # "executable" | "needs_review" | "blocked"


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTE QUERY RESPONSE
# Unchanged from Sprint 1.
# ─────────────────────────────────────────────────────────────────────────────

class AgeGroupBreakdown(BaseModel):
    age_18_30: int = Field(..., alias="18-30")
    age_31_45: int = Field(..., alias="31-45")
    age_46_60: int = Field(..., alias="46-60")
    age_61_plus: int = Field(..., alias="61+")
    model_config = {"populate_by_name": True}


class SexBreakdown(BaseModel):
    male: int
    female: int
    other: int


class Demographics(BaseModel):
    age_groups: AgeGroupBreakdown
    sex: SexBreakdown


class LabSummary(BaseModel):
    lab_name: str
    unit: str
    count: int
    mean: float
    min: float
    max: float


class ExecuteQueryResponse(BaseModel):
    """Results from PostgreSQL — every number here comes from the database."""
    cohort_size: int
    demographics: Demographics
    incidence_rate: Optional[float] = None
    incidence_rate_unit: Optional[str] = None
    lab_summaries: Optional[list[LabSummary]] = None
    query_time_ms: int


# ─────────────────────────────────────────────────────────────────────────────
# ERROR RESPONSE — unchanged
# ─────────────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error shape for all endpoints."""
    error_code: str    # SCREAMING_SNAKE_CASE, e.g. "LLM_GENERATION_FAILED"
    message: str
    recoverable: bool  # True = user can retry; False = pipeline must restart
    stage: Optional[str] = None   # "llm" | "athena" | "sql" | "backend"
    details: dict[str, Any] = {}
