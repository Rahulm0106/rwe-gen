"""
tests/test_smoke.py — Updated smoke tests for Sprint 2 architecture + stream endpoint.

WHAT CHANGED FROM SPRINT 1
───────────────────────────
The _build_execute_request() helper now uses Simon's full nested protocol
structure instead of the old flat 6-field ProtocolResponse.

The /generate-protocol and /validate-concepts tests still use mocked responses
because the real Venice and LOF services require live credentials. Endpoint
shape validation is the goal here — not end-to-end integration.

For live integration tests (TC-04, TC-05, TC-06, TC-10), see Rahul's
integration test suite which runs against the real endpoints with credentials.
"""

import json

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

client = TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

def test_health_check_returns_200():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["llm_provider"] == "venice"


# ─────────────────────────────────────────────────────────────────────────────
# /generate-protocol — test with mocked LLM module
#
# WHY WE MOCK HERE
# ─────────────────
# Real Venice API calls require credentials and network access — not available
# in CI. We mock app.state.llm so we can test that:
#   1. The endpoint accepts a valid question
#   2. The endpoint rejects an invalid question (too short)
#   3. The endpoint correctly propagates LLMError as a 500/422
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_protocol() -> dict:
    """Returns the minimal valid protocol dict matching Simon's schema."""
    return {
        "schema_version": "1.0.0",
        "original_question": "What is the incidence of CKD in T2D patients on metformin?",
        "normalized_question": "What is the incidence of CKD in T2D patients on metformin?",
        "study_type": "incidence_analysis",
        "protocol_status": "needs_mapping",
        "target_cohort": {
            "label": "T2D patients on metformin",
            "index_event": {
                "event_type": "condition",
                "concept_refs": ["concept_1"],
                "index_date_rule": "first_event",
            },
            "demographic_filters": {},
            "inclusion_criteria": [],
            "exclusion_criteria": [],
        },
        "comparator": {"enabled": False, "label": None, "definition": {}},
        "outcome": {
            "required": True,
            "concept_refs": ["concept_2"],
            "incident_only": True,
            "clean_period_days": 0,
        },
        "time_windows": {
            "calendar_window": {"start": "2019-01-01", "end": "2024-12-31"},
            "prior_observation": {"min_prior_observation_days": 365},
            "washout": {"washout_period_days": 0},
            "time_at_risk": {"start_offset_days": 1, "end_offset_days": 365},
        },
        "concept_sets": [
            {
                "concept_ref": "concept_1",
                "raw_text": "Type 2 diabetes mellitus",
                "domain": "condition",
                "standard_vocab_preference": "SNOMED",
                "mapping": {"status": "unmapped", "omop_concept_id": None,
                            "omop_concept_name": None, "candidate_concepts": []},
            },
            {
                "concept_ref": "concept_2",
                "raw_text": "Chronic kidney disease",
                "domain": "condition",
                "standard_vocab_preference": "SNOMED",
                "mapping": {"status": "unmapped", "omop_concept_id": None,
                            "omop_concept_name": None, "candidate_concepts": []},
            },
        ],
        "execution": {
            "human_review_required": True,
            "human_mapping_confirmation_required": True,
            "ready_for_execution": False,
            "sql_template": "incidence_analysis",
        },
        "issues": {"warnings": [], "blocking_errors": []},
        "assumptions": [],
        "requested_outputs": ["cohort_size", "demographics", "incidence_rate"],
    }


def _executable_protocol() -> dict:
    """Minimal protocol with all concepts mapped and ready_for_execution=True."""
    p = _minimal_protocol()
    p["protocol_status"] = "executable"
    p["execution"]["ready_for_execution"] = True
    p["execution"]["human_review_required"] = False
    p["execution"]["human_mapping_confirmation_required"] = False
    for cs in p["concept_sets"]:
        cs["mapping"] = {
            "status": "mapped",
            "omop_concept_id": 201826,
            "omop_concept_name": "Type 2 diabetes mellitus",
            "candidate_concepts": [],
        }
    return p


def test_generate_protocol_rejects_short_question():
    """Short questions fail Pydantic validation before hitting the endpoint."""
    response = client.post("/generate-protocol", json={"question": "hi"})
    assert response.status_code == 422


def test_generate_protocol_rejects_missing_question():
    response = client.post("/generate-protocol", json={})
    assert response.status_code == 422


def test_generate_protocol_with_mock_llm():
    """With mocked LLM, endpoint returns the protocol dict."""
    mock_llm = MagicMock()
    mock_llm.generate_protocol.return_value = _minimal_protocol()

    with patch.object(app.state, "llm", mock_llm, create=True):
        response = client.post(
            "/generate-protocol",
            json={"question": "What is the incidence of CKD in T2D patients on metformin?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "study_type" in data
    assert "concept_sets" in data
    assert "protocol_status" in data
    assert data["protocol_status"] == "needs_mapping"


# ─────────────────────────────────────────────────────────────────────────────
# /validate-concepts — test with mocked concept mapper
# ─────────────────────────────────────────────────────────────────────────────

def _mapped_protocol() -> dict:
    """Protocol after map_protocol() runs — all concepts mapped."""
    p = _executable_protocol()
    p["protocol_status"] = "executable"
    return p


def test_validate_concepts_rejects_missing_protocol():
    response = client.post("/validate-concepts", json={})
    assert response.status_code == 422


def test_validate_concepts_with_mock_mapper():
    """With mocked concept mapper, endpoint returns ConceptValidationResponse."""
    mock_mapper = MagicMock()
    mock_mapper.remote_client = {"base_url": "https://mock.lof.com"}
    mock_mapper.map_protocol.return_value = _mapped_protocol()

    with patch.object(app.state, "concept_mapper", mock_mapper, create=True):
        response = client.post(
            "/validate-concepts",
            json={"protocol": _minimal_protocol()},
        )

    assert response.status_code == 200
    data = response.json()
    assert "protocol" in data
    assert "mapped" in data
    assert "unmatched" in data
    assert "protocol_status" in data


# ─────────────────────────────────────────────────────────────────────────────
# /execute-query
# ─────────────────────────────────────────────────────────────────────────────

def _build_execute_request() -> dict:
    return {
        "protocol": _executable_protocol(),
        "validated_concepts": [
            {
                "name": "Type 2 diabetes mellitus",
                "concept_id": 201826,
                "domain": "Condition",
                "vocabulary": "SNOMED",
                "matched": True,
            }
        ],
    }


def test_execute_query_happy_path():
    response = client.post("/execute-query", json=_build_execute_request())
    assert response.status_code == 200
    data = response.json()
    assert "cohort_size" in data
    assert isinstance(data["cohort_size"], int)
    assert data["cohort_size"] >= 0
    assert "demographics" in data
    assert "query_time_ms" in data


def test_execute_query_rejects_non_executable_protocol():
    """Protocol without ready_for_execution=True must be rejected with 422."""
    body = _build_execute_request()
    body["protocol"]["execution"]["ready_for_execution"] = False
    body["protocol"]["protocol_status"] = "needs_review"
    response = client.post("/execute-query", json=body)
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "PROTOCOL_NOT_EXECUTABLE"


def test_execute_query_rejects_missing_protocol():
    response = client.post("/execute-query", json={"validated_concepts": []})
    assert response.status_code == 422


def test_execute_query_demographics_sum_to_cohort_size():
    """Sex breakdown total should equal cohort_size — data integrity check."""
    response = client.post("/execute-query", json=_build_execute_request())
    data = response.json()
    sex = data["demographics"]["sex"]
    assert sex["male"] + sex["female"] + sex["other"] == data["cohort_size"]


# ─────────────────────────────────────────────────────────────────────────────
# /generate-protocol/stream
# ─────────────────────────────────────────────────────────────────────────────

def _parse_sse_frames(raw: str) -> list[dict]:
    """Parse a raw SSE response body into a list of {event, data} dicts.

    Skips comment lines (keepalives) and blank frames.
    """
    frames = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        frame: dict = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                frame["event"] = line[len("event:"):].strip()
            elif line.startswith("data:"):
                raw_data = line[len("data:"):].strip()
                try:
                    frame["data"] = json.loads(raw_data)
                except json.JSONDecodeError:
                    frame["data"] = raw_data
        if frame:
            frames.append(frame)
    return frames


def test_stream_generate_protocol_http_plumbing():
    """HTTP plumbing test: mock returns protocol directly (no on_progress calls).

    Verifies that the stream endpoint:
    - Returns 200 with text/event-stream content type
    - Always emits a 'received' frame first
    - Always emits a 'done' frame last
    - The 'done' data contains the protocol shape (study_type, concept_sets)
    """
    mock_rwe = MagicMock()
    mock_rwe.generate_protocol.return_value = _minimal_protocol()

    with patch.object(app.state, "rwe", mock_rwe, create=True):
        response = client.post(
            "/generate-protocol/stream",
            json={"question": "What is the incidence of CKD in T2D patients on metformin?"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    frames = _parse_sse_frames(response.text)
    events = [f["event"] for f in frames]

    assert events[0] == "received"
    assert events[-1] == "done"

    done_data = frames[-1]["data"]
    assert "study_type" in done_data
    assert "concept_sets" in done_data
    assert done_data["protocol_status"] == "needs_mapping"


def test_stream_generate_protocol_event_sequence():
    """Event sequence test: side_effect fires on_progress at every stage boundary.

    Verifies that when the pipeline calls on_progress correctly, the stream
    endpoint emits events in the expected order:
    received → interpretation_attempt → interpretation_completed →
    protocol_built → schema_validated → done
    """
    def _fake_generate_protocol(question, *, verify=None, on_progress=None):
        if on_progress:
            on_progress({"event": "interpretation_attempt", "model": "zai-org-glm-5", "attempt": 1, "max_attempts": 2})
            on_progress({"event": "interpretation_completed"})
            on_progress({"event": "protocol_built"})
            on_progress({"event": "schema_validated"})
        return _minimal_protocol()

    mock_rwe = MagicMock()
    mock_rwe.generate_protocol.side_effect = _fake_generate_protocol

    with patch.object(app.state, "rwe", mock_rwe, create=True):
        response = client.post(
            "/generate-protocol/stream",
            json={"question": "What is the incidence of CKD in T2D patients on metformin?"},
        )

    assert response.status_code == 200
    frames = _parse_sse_frames(response.text)
    events = [f["event"] for f in frames]

    assert events[0] == "received"
    assert "interpretation_attempt" in events
    assert "interpretation_completed" in events
    assert "protocol_built" in events
    assert "schema_validated" in events
    assert events[-1] == "done"

    # interpretation_attempt carries model metadata
    attempt_frame = next(f for f in frames if f["event"] == "interpretation_attempt")
    assert attempt_frame["data"]["model"] == "zai-org-glm-5"
    assert attempt_frame["data"]["attempt"] == 1
    assert attempt_frame["data"]["max_attempts"] == 2


def test_stream_generate_protocol_error_emits_error_event():
    """When the pipeline raises PipelineStageError, the stream emits an error frame."""
    from llm.api import PipelineStageError

    mock_rwe = MagicMock()
    mock_rwe.generate_protocol.side_effect = PipelineStageError(
        "llm", "all_models_failed", "All models failed."
    )

    with patch.object(app.state, "rwe", mock_rwe, create=True):
        response = client.post(
            "/generate-protocol/stream",
            json={"question": "What is the incidence of CKD in T2D patients on metformin?"},
        )

    assert response.status_code == 200
    frames = _parse_sse_frames(response.text)
    events = [f["event"] for f in frames]

    assert "error" in events
    error_frame = next(f for f in frames if f["event"] == "error")
    assert error_frame["data"]["error_code"] == "ALL_MODELS_FAILED"
    assert error_frame["data"]["recoverable"] is True


def test_stream_generate_protocol_rejects_short_question():
    """Pydantic validation (min_length=10) fires before the stream opens."""
    response = client.post("/generate-protocol/stream", json={"question": "hi"})
    assert response.status_code == 422
