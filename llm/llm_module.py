from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import requests
from jsonschema import Draft202012Validator


class LLMError(Exception):
    """Raised when the LLM layer fails in a way the caller should handle."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        model: str | None = None,
        attempt: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = "llm"
        self.kind = kind
        self.model = model
        self.attempt = attempt
        self.details = details or {}


@dataclass(slots=True)
class VeniceModelConfig:
    name: str
    retries: int = 2
    temperature: float = 0.0
    max_tokens: int = 2600


@dataclass(slots=True)
class LLMConfig:
    schema_path: str
    api_key: str | None = None
    base_url: str = "https://api.venice.ai/api/v1"
    timeout_seconds: int = 60
    models: list[VeniceModelConfig] = field(default_factory=list)
    mock_protocol_path: str | None = None
    include_venice_system_prompt: bool = False
    semantic_verification_enabled: bool = False
    verification_models: list[VeniceModelConfig] = field(default_factory=list)
    verification_timeout_seconds: int | None = None


class ProtocolLLMGenerator:
    """
    Generates a study protocol JSON from a clinician question.

    The generation stage asks the model for a smaller interpretation object and
    then deterministically builds the full protocol JSON in Python. An optional
    semantic verification stage can then ask a stronger model to review and
    correct the generated protocol while preserving schema validity.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.schema_path = Path(config.schema_path)
        self.schema = self._load_schema(self.schema_path)
        self.validator = Draft202012Validator(self.schema)
        self.interpretation_schema = self._build_interpretation_schema()
        self.interpretation_validator = Draft202012Validator(self.interpretation_schema)
        if not self.config.models:
            self.config.models = [
                VeniceModelConfig(name="zai-org-glm-5", retries=2),
                VeniceModelConfig(name="kimi-k2-5", retries=2),
            ]
        if not self.config.verification_models:
            self.config.verification_models = [
                VeniceModelConfig(name="kimi-k2-5", retries=2),
                VeniceModelConfig(name="zai-org-glm-5", retries=1),
            ]

    def generate_protocol(
        self,
        question: str,
        *,
        verify: bool | None = None,
        on_progress: Callable[[dict], None] | None = None,
    ) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise LLMError(
                "The clinician question is empty.",
                kind="input_error",
                details={"question": question},
            )

        api_key = self.config.api_key or os.getenv("VENICE_API_KEY")
        if not self.config.mock_protocol_path and not api_key:
            raise LLMError(
                "Missing Venice API key. Set VENICE_API_KEY or pass api_key explicitly.",
                kind="authentication",
            )

        if self.config.mock_protocol_path:
            protocol = self._load_and_validate_mock_protocol(question)
        else:
            interpretation = self._generate_interpretation(
                question, api_key=api_key or "", on_progress=on_progress
            )
            self._emit(
                on_progress,
                "interpretation_completed",
                "Interpretation parsed and validated",
            )
            protocol = self._build_protocol_from_interpretation(question, interpretation)
            self._emit(
                on_progress,
                "protocol_built",
                "Built draft protocol from interpretation",
            )
            protocol = self._apply_pre_mapping_defaults(protocol, question)
            self._validate_protocol(protocol)
            self._emit(
                on_progress,
                "schema_validated",
                "Draft protocol passes schema validation",
            )

        verify_enabled = (
            verify if verify is not None else self.config.semantic_verification_enabled
        )
        if verify_enabled:
            if not api_key:
                raise LLMError(
                    "Semantic verification was enabled but no Venice API key is available.",
                    kind="authentication",
                )
            self._emit(
                on_progress,
                "verification_started",
                "Starting clinical review of the generated protocol",
            )
            protocol = self._semantic_verify_protocol(
                question, protocol, api_key, on_progress=on_progress
            )
            self._emit(
                on_progress,
                "verification_completed",
                "Protocol verified",
            )

        return protocol

    # ---------------------------------------------------------------------
    # Progress emission helper
    # ---------------------------------------------------------------------
    @staticmethod
    def _emit(
        on_progress: Callable[[dict], None] | None,
        event: str,
        message: str,
        **fields: Any,
    ) -> None:
        if on_progress is None:
            return
        on_progress({"event": event, "message": message, **fields})

    # ---------------------------------------------------------------------
    # Venice calling
    # ---------------------------------------------------------------------
    def _call_venice_api(
        self,
        *,
        api_key: str,
        model_config: VeniceModelConfig,
        messages: list[dict[str, str]],
        timeout_seconds: int,
    ) -> str:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": model_config.name,
            "messages": messages,
            "temperature": model_config.temperature,
            "max_tokens": model_config.max_tokens,
        }
        if self.config.include_venice_system_prompt:
            payload["venice_parameters"] = {"include_venice_system_prompt": True}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
        except requests.Timeout as exc:
            raise LLMError(
                "Timed out while calling the Venice chat completions endpoint.",
                kind="timeout",
                model=model_config.name,
                details={"timeout_seconds": timeout_seconds},
            ) from exc
        except requests.RequestException as exc:
            raise LLMError(
                "Network error while calling the Venice API.",
                kind="network",
                model=model_config.name,
                details={"error": str(exc)},
            ) from exc

        if response.status_code >= 400:
            try:
                detail: Any = response.json()
            except Exception:
                detail = response.text
            kind = "authentication" if response.status_code in {401, 403} else "venice_api"
            raise LLMError(
                f"Venice API returned HTTP {response.status_code}.",
                kind=kind,
                model=model_config.name,
                details={"status_code": response.status_code, "response": detail},
            )

        try:
            body = response.json()
            message = body["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "Venice API response did not match the expected chat completion shape.",
                kind="response_shape",
                model=model_config.name,
                details={"response_text": response.text[:4000]},
            ) from exc

        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
            joined = "\n".join(text_parts).strip()
            if joined:
                return joined

        raise LLMError(
            "Venice API returned an empty assistant message.",
            kind="empty_response",
            model=model_config.name,
            details={"message": message if isinstance(message, dict) else None},
        )

    # ---------------------------------------------------------------------
    # Generation stage
    # ---------------------------------------------------------------------
    def _generate_interpretation(
        self,
        question: str,
        *,
        api_key: str,
        on_progress: Callable[[dict], None] | None = None,
    ) -> dict[str, Any]:
        base_messages = self._build_generation_messages(question)
        failures: list[dict[str, Any]] = []

        for model_config in self.config.models:
            messages = list(base_messages)
            previous_response: str | None = None
            for attempt in range(1, model_config.retries + 1):
                self._emit(
                    on_progress,
                    "interpretation_attempt",
                    f"Interpreting question with {model_config.name} "
                    f"(attempt {attempt}/{model_config.retries})",
                    model=model_config.name,
                    attempt=attempt,
                    max_attempts=model_config.retries,
                )
                try:
                    response_text = self._call_venice_api(
                        api_key=api_key,
                        model_config=model_config,
                        messages=messages,
                        timeout_seconds=self.config.timeout_seconds,
                    )
                    previous_response = response_text
                    interpretation = self._parse_json_response(response_text)
                    self._validate_interpretation(interpretation)
                    return interpretation
                except LLMError as exc:
                    failures.append(
                        {
                            "model": model_config.name,
                            "attempt": attempt,
                            "kind": exc.kind,
                            "message": str(exc),
                            "details": exc.details,
                        }
                    )
                    if attempt < model_config.retries:
                        messages = self._build_generation_repair_messages(
                            question=question,
                            previous_response=previous_response,
                            error_details=exc.details,
                        )

        raise LLMError(
            "All configured Venice models failed to produce a valid interpretation object.",
            kind="all_models_failed",
            details={"failures": failures},
        )

    def _build_generation_messages(self, question: str) -> list[dict[str, str]]:
        example = {
            "study_type": "cohort_characterization",
            "normalized_question": "Characterize adults with type 2 diabetes treated with metformin in the last 5 years.",
            "target": {
                "label": "Adults with type 2 diabetes treated with metformin in the last 5 years",
                "index": {"raw_text": "type 2 diabetes", "domain": "condition"},
                "include": [
                    {
                        "raw_text": "metformin",
                        "domain": "drug",
                        "min_occurrences": 1,
                        "timing": {"start_day_offset": -1825, "end_day_offset": 0},
                    }
                ],
                "exclude": [],
            },
            "comparator": {"enabled": False, "label": None, "index": None, "include": [], "exclude": []},
            "outcome": {"required": False, "term": None, "incident_only": False, "clean_period_days": None},
            "demographics": {"min_age": 18, "max_age": None, "sex": ["male", "female", "unknown"]},
            "requested_outputs": {"measures": ["cohort_size", "demographics"], "stratify_by": ["sex", "age_group"]},
            "assumptions": [],
        }
        system_prompt = (
            "You are an expert clinical protocol interpreter for the RWE-Gen MVP. "
            "Translate the clinician question into a SMALL JSON interpretation object only. "
            "Do not output the final protocol schema. Do not output SQL. Do not output prose. "
            "Return a single JSON object only. The output must follow these rules: \n"
            "1. study_type must be either cohort_characterization or incidence_analysis.\n"
            "2. target.index is the single main anchor event for the target cohort. It must contain one raw_text and one domain.\n"
            "3. target.include contains additional required concepts beyond the anchor.\n"
            "4. comparator.enabled=false if no comparator is asked for.\n"
            "5. outcome.required=false for characterization questions and true for incidence questions.\n"
            "6. Use domains only from: condition, drug, procedure, measurement, observation, visit.\n"
            "7. If a time phrase such as 'in the last 5 years' clearly applies to a concept, attach it to that concept in timing.start_day_offset/end_day_offset using negative day offsets.\n"
            "8. Keep demographics explicit. Adults means min_age=18.\n"
            "9. requested_outputs should be minimal and aligned with the study type.\n"
            "10. Prefer concise raw_text values exactly as the clinician would expect Athena to map.\n\n"
            "Example valid interpretation JSON:\n"
            f"{json.dumps(example, ensure_ascii=False)}"
        )
        user_prompt = (
            "Clinician question:\n"
            f"{question}\n\n"
            "Return only the interpretation JSON object."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_generation_repair_messages(
        self,
        *,
        question: str,
        previous_response: str | None,
        error_details: dict[str, Any],
    ) -> list[dict[str, str]]:
        system_prompt = (
            "You must repair the previous interpretation attempt. "
            "Return ONLY a corrected JSON interpretation object. "
            "Do not return markdown, comments, or explanations."
        )
        user_prompt = (
            "Clinician question:\n"
            f"{question}\n\n"
            "Previous response:\n"
            f"{previous_response or '<empty>'}\n\n"
            "Validation or parsing errors:\n"
            f"{json.dumps(error_details, ensure_ascii=False)}\n\n"
            "Return only corrected interpretation JSON."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # ---------------------------------------------------------------------
    # Semantic verification stage
    # ---------------------------------------------------------------------
    def _semantic_verify_protocol(
        self,
        question: str,
        protocol: dict[str, Any],
        api_key: str,
        *,
        on_progress: Callable[[dict], None] | None = None,
    ) -> dict[str, Any]:
        failures: list[dict[str, Any]] = []
        verification_timeout = self.config.verification_timeout_seconds or self.config.timeout_seconds
        previous_model_name: str | None = None

        for model_config in self.config.verification_models:
            if previous_model_name is not None:
                self._emit(
                    on_progress,
                    "verification_model_fallback",
                    f"Previous reviewer ({previous_model_name}) couldn't produce a "
                    f"valid protocol — handing off to {model_config.name}",
                    from_model=previous_model_name,
                    to_model=model_config.name,
                )
            previous_model_name = model_config.name

            messages = self._build_verification_messages(question, protocol)
            previous_response: str | None = None
            for attempt in range(1, model_config.retries + 1):
                self._emit(
                    on_progress,
                    "verification_attempt",
                    f"Reviewing protocol with {model_config.name} "
                    f"(attempt {attempt}/{model_config.retries})",
                    model=model_config.name,
                    attempt=attempt,
                    max_attempts=model_config.retries,
                )
                try:
                    self._emit(
                        on_progress,
                        "verification_call_started",
                        f"Asking {model_config.name} to check for clinical issues "
                        f"(up to {verification_timeout}s)",
                        model=model_config.name,
                        phase="review",
                        timeout_seconds=verification_timeout,
                    )
                    t0 = time.monotonic()
                    response_text = self._call_venice_api(
                        api_key=api_key,
                        model_config=model_config,
                        messages=messages,
                        timeout_seconds=verification_timeout,
                    )
                    elapsed = round(time.monotonic() - t0, 2)
                    self._emit(
                        on_progress,
                        "verification_call_completed",
                        f"{model_config.name} responded ({elapsed}s)",
                        model=model_config.name,
                        phase="review",
                        elapsed_seconds=elapsed,
                    )
                    previous_response = response_text
                    self._emit(
                        on_progress,
                        "verification_parsing",
                        "Parsing reviewer's response",
                        model=model_config.name,
                        phase="review",
                    )
                    candidate = self._parse_json_response(response_text)
                    candidate["original_question"] = question
                    candidate = self._apply_pre_mapping_defaults(candidate, question)
                    self._emit(
                        on_progress,
                        "verification_validating",
                        "Validating reviewed protocol against schema",
                        model=model_config.name,
                        phase="review",
                    )
                    self._validate_protocol(candidate)
                    self._emit(
                        on_progress,
                        "verification_succeeded",
                        f"Clinical review complete via {model_config.name}",
                        model=model_config.name,
                        attempt=attempt,
                        phase="review",
                    )
                    return candidate
                except LLMError as exc:
                    reasoning_text = self._extract_reasoning_text_from_error(exc)
                    if exc.kind == "empty_response" and reasoning_text:
                        self._emit(
                            on_progress,
                            "verification_reasoning_recovery",
                            f"{model_config.name} returned reasoning without JSON — "
                            "extracting the corrected protocol",
                            model=model_config.name,
                        )
                        try:
                            self._emit(
                                on_progress,
                                "verification_call_started",
                                f"Asking {model_config.name} to format the corrected "
                                f"protocol as JSON (up to {verification_timeout}s)",
                                model=model_config.name,
                                phase="finalize",
                                timeout_seconds=verification_timeout,
                            )
                            t0 = time.monotonic()
                            finalized_text = self._call_venice_api(
                                api_key=api_key,
                                model_config=model_config,
                                messages=self._build_verification_finalize_messages(
                                    question=question,
                                    original_protocol=protocol,
                                    reasoning_text=reasoning_text,
                                ),
                                timeout_seconds=verification_timeout,
                            )
                            elapsed = round(time.monotonic() - t0, 2)
                            self._emit(
                                on_progress,
                                "verification_call_completed",
                                f"{model_config.name} formatter responded ({elapsed}s)",
                                model=model_config.name,
                                phase="finalize",
                                elapsed_seconds=elapsed,
                            )
                            previous_response = finalized_text
                            self._emit(
                                on_progress,
                                "verification_parsing",
                                "Parsing formatted protocol",
                                model=model_config.name,
                                phase="finalize",
                            )
                            candidate = self._parse_json_response(finalized_text)
                            candidate["original_question"] = question
                            candidate = self._apply_pre_mapping_defaults(candidate, question)
                            self._emit(
                                on_progress,
                                "verification_validating",
                                "Validating reviewed protocol against schema",
                                model=model_config.name,
                                phase="finalize",
                            )
                            self._validate_protocol(candidate)
                            self._emit(
                                on_progress,
                                "verification_succeeded",
                                f"Clinical review complete via reasoning recovery "
                                f"({model_config.name})",
                                model=model_config.name,
                                attempt=attempt,
                                phase="finalize",
                            )
                            return candidate
                        except LLMError as finalize_exc:
                            formatter_reasoning = self._extract_reasoning_text_from_error(finalize_exc) or reasoning_text
                            try:
                                self._emit(
                                    on_progress,
                                    "verification_formatter_started",
                                    f"Reformatting reviewer reasoning into a valid "
                                    f"protocol via {model_config.name}",
                                    model=model_config.name,
                                )
                                return self._format_protocol_from_reasoning(
                                    question=question,
                                    original_protocol=protocol,
                                    reasoning_text=formatter_reasoning,
                                    api_key=api_key,
                                    timeout_seconds=verification_timeout,
                                    on_progress=on_progress,
                                )
                            except LLMError as formatter_exc:
                                failures.append(
                                    {
                                        "model": model_config.name,
                                        "attempt": attempt,
                                        "kind": "reasoning_finalize_failed",
                                        "message": str(finalize_exc),
                                        "details": {
                                            "initial_error": {
                                                "kind": exc.kind,
                                                "message": str(exc),
                                                "details": exc.details,
                                            },
                                            "finalize_error": {
                                                "kind": finalize_exc.kind,
                                                "message": str(finalize_exc),
                                                "details": finalize_exc.details,
                                            },
                                            "formatter_error": {
                                                "kind": formatter_exc.kind,
                                                "message": str(formatter_exc),
                                                "details": formatter_exc.details,
                                            },
                                        },
                                    }
                                )
                                if attempt < model_config.retries:
                                    self._emit(
                                        on_progress,
                                        "verification_repair",
                                        f"Reasoning recovery failed — retrying "
                                        f"{model_config.name} with corrections",
                                        model=model_config.name,
                                        attempt=attempt,
                                        error_kind=finalize_exc.kind,
                                    )
                                    messages = self._build_verification_repair_messages(
                                        question=question,
                                        original_protocol=protocol,
                                        previous_response=previous_response,
                                        error_details=finalize_exc.details,
                                    )
                                continue

                    failures.append(
                        {
                            "model": model_config.name,
                            "attempt": attempt,
                            "kind": exc.kind,
                            "message": str(exc),
                            "details": exc.details,
                        }
                    )
                    if attempt < model_config.retries:
                        self._emit(
                            on_progress,
                            "verification_repair",
                            f"Reviewer's output failed ({exc.kind}) — retrying "
                            f"{model_config.name} with corrections",
                            model=model_config.name,
                            attempt=attempt,
                            error_kind=exc.kind,
                        )
                        messages = self._build_verification_repair_messages(
                            question=question,
                            original_protocol=protocol,
                            previous_response=previous_response,
                            error_details=exc.details,
                        )

        candidate = self._apply_pre_mapping_defaults(protocol, question)
        candidate.setdefault("issues", {"warnings": [], "blocking_errors": []})
        candidate["issues"].setdefault("warnings", [])
        candidate["issues"]["warnings"].append(
            {
                "code": "SEMANTIC_VERIFICATION_FAILED",
                "message": "Semantic verification could not produce a reviewed protocol; returning the pre-verification protocol unchanged.",
                "field_path": None,
            }
        )
        return candidate

    def _build_verification_messages(self, question: str, protocol: dict[str, Any]) -> list[dict[str, str]]:
        schema_text = json.dumps(self.schema, ensure_ascii=False)
        system_prompt = (
            "You are a senior physician-informatician reviewing an already valid RWE-Gen study protocol. "
            "Your job is to look for semantic, clinical, and study-design flaws while preserving strict schema validity. "
            "You may correct concept roles, event domains, timing logic, cohort anchors, comparator logic, outcome logic, and requested outputs. "
            "Do NOT invent results. Do NOT map OMOP concepts. Leave every concept_sets[i].mapping in the pre-Athena unmapped state. "
            "Keep protocol_status='needs_mapping' unless the question is clearly unsupported. "
            "Return ONLY one full corrected protocol JSON object that validates against the provided schema."
        )
        user_prompt = (
            "Original clinician question:\n"
            f"{question}\n\n"
            "Protocol schema (must remain valid):\n"
            f"{schema_text}\n\n"
            "Current protocol to review and correct if needed:\n"
            f"{json.dumps(protocol, ensure_ascii=False)}\n\n"
            "Return only the corrected full protocol JSON object."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_verification_finalize_messages(
        self,
        *,
        question: str,
        original_protocol: dict[str, Any],
        reasoning_text: str,
    ) -> list[dict[str, str]]:
        schema_text = json.dumps(self.schema, ensure_ascii=False)
        system_prompt = (
            "You already completed the reasoning step. Now provide ONLY the final corrected protocol JSON object. "
            "Do not include reasoning, summaries, markdown, or prose. Output a single JSON object only. "
            "The JSON must validate against the provided schema. "
            "If the protocol needs no semantic changes, return the protocol unchanged except for any fields required to preserve schema validity."
        )
        user_prompt = (
            "Original clinician question:\n"
            f"{question}\n\n"
            "Protocol schema (must remain valid):\n"
            f"{schema_text}\n\n"
            "Original protocol:\n"
            f"{json.dumps(original_protocol, ensure_ascii=False)}\n\n"
            "Your prior reasoning summary:\n"
            f"{reasoning_text}\n\n"
            "Now output ONLY the final corrected full protocol JSON object."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_verification_repair_messages(
        self,
        *,
        question: str,
        original_protocol: dict[str, Any],
        previous_response: str | None,
        error_details: dict[str, Any],
    ) -> list[dict[str, str]]:
        system_prompt = (
            "Repair the previous reviewed protocol attempt. Return ONLY a corrected full protocol JSON object that validates against the schema."
        )
        user_prompt = (
            "Original clinician question:\n"
            f"{question}\n\n"
            "Original protocol before review:\n"
            f"{json.dumps(original_protocol, ensure_ascii=False)}\n\n"
            "Previous invalid review response:\n"
            f"{previous_response or '<empty>'}\n\n"
            "Validation or parsing errors:\n"
            f"{json.dumps(error_details, ensure_ascii=False)}\n\n"
            "Return only corrected full protocol JSON."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _format_protocol_from_reasoning(
        self,
        *,
        question: str,
        original_protocol: dict[str, Any],
        reasoning_text: str,
        api_key: str,
        timeout_seconds: int,
        on_progress: Callable[[dict], None] | None = None,
    ) -> dict[str, Any]:
        formatter_models = self.config.models or [VeniceModelConfig(name="zai-org-glm-5", retries=1)]
        failures: list[dict[str, Any]] = []
        for model_config in formatter_models:
            attempts = max(1, min(model_config.retries, 2))
            for attempt in range(1, attempts + 1):
                try:
                    self._emit(
                        on_progress,
                        "verification_call_started",
                        f"Reformatting reasoning via {model_config.name} "
                        f"(attempt {attempt}/{attempts})",
                        model=model_config.name,
                        phase="format",
                        timeout_seconds=timeout_seconds,
                    )
                    t0 = time.monotonic()
                    response_text = self._call_venice_api(
                        api_key=api_key,
                        model_config=model_config,
                        messages=self._build_reasoning_formatter_messages(
                            question=question,
                            original_protocol=original_protocol,
                            reasoning_text=reasoning_text,
                        ),
                        timeout_seconds=timeout_seconds,
                    )
                    elapsed = round(time.monotonic() - t0, 2)
                    self._emit(
                        on_progress,
                        "verification_call_completed",
                        f"{model_config.name} formatter responded ({elapsed}s)",
                        model=model_config.name,
                        phase="format",
                        elapsed_seconds=elapsed,
                    )
                    candidate = self._parse_json_response(response_text)
                    candidate["original_question"] = question
                    candidate = self._apply_pre_mapping_defaults(candidate, question)
                    self._validate_protocol(candidate)
                    self._emit(
                        on_progress,
                        "verification_succeeded",
                        f"Clinical review complete via reasoning formatter "
                        f"({model_config.name})",
                        model=model_config.name,
                        attempt=attempt,
                        phase="format",
                    )
                    return candidate
                except LLMError as exc:
                    failures.append(
                        {
                            "model": model_config.name,
                            "attempt": attempt,
                            "kind": exc.kind,
                            "message": str(exc),
                            "details": exc.details,
                        }
                    )
        raise LLMError(
            "Could not convert verifier reasoning into a valid reviewed protocol.",
            kind="verification_reasoning_formatter_failed",
            details={"failures": failures},
        )

    def _build_reasoning_formatter_messages(
        self,
        *,
        question: str,
        original_protocol: dict[str, Any],
        reasoning_text: str,
    ) -> list[dict[str, str]]:
        schema_text = json.dumps(self.schema, ensure_ascii=False)
        system_prompt = (
            "You are a strict JSON formatter. Convert the supplied physician review reasoning into one corrected full protocol JSON object. "
            "Return ONLY JSON. Do not include markdown, comments, or explanations. The JSON must validate against the provided schema."
        )
        user_prompt = (
            "Original clinician question:\n"
            f"{question}\n\n"
            "Protocol schema:\n"
            f"{schema_text}\n\n"
            "Original protocol:\n"
            f"{json.dumps(original_protocol, ensure_ascii=False)}\n\n"
            "Reviewer reasoning to apply:\n"
            f"{reasoning_text}\n\n"
            "Return only the corrected full protocol JSON object."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # ---------------------------------------------------------------------
    # Deterministic protocol construction
    # ---------------------------------------------------------------------
    def _build_protocol_from_interpretation(self, question: str, interpretation: dict[str, Any]) -> dict[str, Any]:
        concept_registry: dict[tuple[str, str, str | None], str] = {}
        concept_sets: list[dict[str, Any]] = []

        def register_term(raw_text: str | None, domain: str | None) -> str | None:
            if not raw_text or not domain:
                return None
            cleaned_text = raw_text.strip()
            cleaned_domain = domain.strip()
            if not cleaned_text or not cleaned_domain:
                return None
            key = (cleaned_text.lower(), cleaned_domain.lower(), self._preferred_vocab_for_domain(cleaned_domain))
            if key in concept_registry:
                return concept_registry[key]
            concept_ref = f"concept_{len(concept_registry) + 1}"
            concept_registry[key] = concept_ref
            concept_sets.append(
                {
                    "concept_ref": concept_ref,
                    "raw_text": cleaned_text,
                    "domain": cleaned_domain.lower(),
                    "standard_vocab_preference": self._preferred_vocab_for_domain(cleaned_domain),
                    "mapping": {
                        "status": "unmapped",
                        "omop_concept_id": None,
                        "omop_concept_name": None,
                        "candidate_concepts": [],
                    },
                }
            )
            return concept_ref

        study_type = interpretation.get("study_type", "cohort_characterization")
        target = interpretation.get("target", {})
        target_index = target.get("index") or {}
        target_index_ref = register_term(target_index.get("raw_text"), target_index.get("domain"))
        if not target_index_ref:
            raise LLMError(
                "The generated interpretation did not contain a usable target cohort index term.",
                kind="interpretation_missing_target_index",
                details={"interpretation": interpretation},
            )

        target_index_event_type = self._event_type_from_concept_domain(target_index.get("domain", "condition"))
        target_inclusion = self._build_criteria_list(target.get("include", []), register_term)
        target_exclusion = self._build_criteria_list(target.get("exclude", []), register_term)

        comparator_interp = interpretation.get("comparator", {})
        comparator_enabled = bool(comparator_interp.get("enabled", False))
        comparator: dict[str, Any]
        if comparator_enabled:
            comp_index = comparator_interp.get("index") or {}
            comp_index_ref = register_term(comp_index.get("raw_text"), comp_index.get("domain"))
            if not comp_index_ref:
                comparator_enabled = False
            else:
                comparator = {
                    "enabled": True,
                    "label": comparator_interp.get("label") or "Comparator cohort",
                    "definition": {
                        "index_event": {
                            "event_type": self._event_type_from_concept_domain(comp_index.get("domain", "condition")),
                            "concept_refs": [comp_index_ref],
                            "occurrence": "first",
                            "index_date_rule": "first_qualifying_event",
                        },
                        "inclusion_criteria": self._build_criteria_list(comparator_interp.get("include", []), register_term),
                        "exclusion_criteria": self._build_criteria_list(comparator_interp.get("exclude", []), register_term),
                        "demographic_filters": self._build_demographic_filters(interpretation.get("demographics", {})),
                    },
                    "comparison_mode": "parallel_cohort",
                }
        if not comparator_enabled:
            comparator = {
                "enabled": False,
                "label": None,
                "definition": None,
                "comparison_mode": "none",
            }

        outcome_interp = interpretation.get("outcome", {})
        outcome_required = bool(outcome_interp.get("required", study_type == "incidence_analysis"))
        outcome_term = outcome_interp.get("term") if isinstance(outcome_interp.get("term"), dict) else None
        outcome_ref = register_term(
            outcome_term.get("raw_text") if outcome_term else None,
            outcome_term.get("domain") if outcome_term else None,
        )
        if outcome_required and not outcome_ref:
            raise LLMError(
                "The generated interpretation marked the outcome as required but did not provide a usable outcome term.",
                kind="interpretation_missing_outcome",
                details={"interpretation": interpretation},
            )

        protocol = {
            "schema_version": "1.0.0",
            "protocol_status": "needs_mapping",
            "original_question": question,
            "normalized_question": interpretation.get("normalized_question") or question,
            "study_type": study_type,
            "target_cohort": {
                "label": target.get("label") or question.rstrip("."),
                "index_event": {
                    "event_type": target_index_event_type,
                    "concept_refs": [target_index_ref],
                    "occurrence": "first",
                    "index_date_rule": "first_qualifying_event",
                },
                "inclusion_criteria": target_inclusion,
                "exclusion_criteria": target_exclusion,
                "demographic_filters": self._build_demographic_filters(interpretation.get("demographics", {})),
            },
            "comparator": comparator,
            "outcome": self._build_outcome_object(outcome_required, outcome_ref, outcome_interp),
            "time_windows": self._build_time_windows(study_type, outcome_required),
            "requested_outputs": self._build_requested_outputs(interpretation.get("requested_outputs", {}), study_type),
            "concept_sets": concept_sets,
            "assumptions": interpretation.get("assumptions", []) if isinstance(interpretation.get("assumptions"), list) else [],
            "issues": {"warnings": [], "blocking_errors": []},
            "execution": {
                "human_review_required": True,
                "human_mapping_confirmation_required": True,
                "sql_template": study_type,
                "ready_for_execution": False,
            },
        }
        return protocol

    def _build_criteria_list(self, items: list[Any], register_term: Any) -> list[dict[str, Any]]:
        criteria: list[dict[str, Any]] = []
        for index, item in enumerate(items or [], start=1):
            if not isinstance(item, dict):
                continue
            concept_ref = register_term(item.get("raw_text"), item.get("domain"))
            if not concept_ref:
                continue
            timing = item.get("timing") or {}
            criteria.append(
                {
                    "criterion_id": item.get("criterion_id") or f"criterion_{index}",
                    "domain": self._criterion_domain_from_concept_domain(item.get("domain", "condition")),
                    "concept_refs": [concept_ref],
                    "rule_type": item.get("rule_type") or "has",
                    "operator": item.get("operator") or ("exists" if (item.get("rule_type") or "has") in {"has", "not_has"} else "gte"),
                    "value": item.get("value"),
                    "unit": item.get("unit"),
                    "min_occurrences": item.get("min_occurrences", 1),
                    "timing": {
                        "relation_to_index": timing.get("relation_to_index") or "during",
                        "start_day_offset": timing.get("start_day_offset"),
                        "end_day_offset": timing.get("end_day_offset"),
                    },
                }
            )
        return criteria

    def _build_demographic_filters(self, demographics: dict[str, Any]) -> dict[str, Any]:
        sex_values = demographics.get("sex") if isinstance(demographics.get("sex"), list) else None
        if not sex_values:
            sex_values = ["male", "female", "unknown"]
        return {
            "age": {
                "min": demographics.get("min_age"),
                "max": demographics.get("max_age"),
                "unit": "years",
                "evaluated_at": "index_date",
            },
            "sex": sex_values,
        }

    def _build_outcome_object(self, required: bool, outcome_ref: str | None, outcome_interp: dict[str, Any]) -> dict[str, Any]:
        if not required:
            return {
                "required": False,
                "label": None,
                "concept_refs": [],
                "occurrence": "first",
                "incident_only": False,
                "clean_period_days": None,
            }
        return {
            "required": True,
            "label": outcome_interp.get("term", {}).get("raw_text") if isinstance(outcome_interp.get("term"), dict) else "Outcome",
            "concept_refs": [outcome_ref] if outcome_ref else [],
            "occurrence": "first",
            "incident_only": bool(outcome_interp.get("incident_only", True)),
            "clean_period_days": outcome_interp.get("clean_period_days"),
        }

    def _build_time_windows(self, study_type: str, outcome_required: bool) -> dict[str, Any]:
        return {
            "calendar_window": {"start_date": None, "end_date": None},
            "prior_observation": {"min_prior_observation_days": None},
            "washout": {"washout_period_days": None},
            "time_at_risk": {
                "start_anchor": "index_date",
                "start_day_offset": 0,
                "end_anchor": "end_of_observation" if not outcome_required else "outcome_date",
                "end_day_offset": None,
                "max_followup_days": None,
                "censor_on_outcome": bool(study_type == "incidence_analysis"),
            },
        }

    def _build_requested_outputs(self, requested_outputs: dict[str, Any], study_type: str) -> dict[str, Any]:
        default_measures = ["cohort_size", "demographics"] if study_type == "cohort_characterization" else ["cohort_size", "incidence_rate"]
        default_stratify = ["sex", "age_group"]
        measures = requested_outputs.get("measures") if isinstance(requested_outputs.get("measures"), list) else default_measures
        stratify_by = requested_outputs.get("stratify_by") if isinstance(requested_outputs.get("stratify_by"), list) else default_stratify
        return {"measures": measures, "stratify_by": stratify_by}

    # ---------------------------------------------------------------------
    # Validation / parsing helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _extract_reasoning_text_from_error(error: LLMError) -> str | None:
        if not isinstance(error.details, dict):
            return None
        message = error.details.get("message")
        if not isinstance(message, dict):
            return None
        reasoning_content = message.get("reasoning_content")
        if isinstance(reasoning_content, str) and reasoning_content.strip():
            return reasoning_content.strip()
        reasoning_details = message.get("reasoning_details")
        if isinstance(reasoning_details, list):
            parts: list[str] = []
            for item in reasoning_details:
                if not isinstance(item, dict):
                    continue
                summary = item.get("summary")
                if isinstance(summary, str) and summary.strip():
                    parts.append(summary.strip())
            if parts:
                return "\n\n".join(parts)
        return None

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            candidate = json.loads(cleaned)
        except json.JSONDecodeError:
            candidate = self._extract_first_json_object(cleaned)
        if not isinstance(candidate, dict):
            raise LLMError(
                "The LLM response was valid JSON but not a JSON object.",
                kind="json_shape",
                details={"response": text[:4000]},
            )
        return candidate

    def _extract_first_json_object(self, text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for start_index, char in enumerate(text):
            if char != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[start_index:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
        raise LLMError(
            "The LLM response did not contain a parseable JSON object.",
            kind="json_parse",
            details={"response": text[:4000]},
        )

    def _validate_interpretation(self, interpretation: dict[str, Any]) -> None:
        errors = sorted(self.interpretation_validator.iter_errors(interpretation), key=lambda err: list(err.path))
        if errors:
            raise LLMError(
                "The LLM interpretation object did not validate.",
                kind="interpretation_validation",
                details={
                    "errors": [
                        {"path": self._format_error_path(error.absolute_path), "message": error.message}
                        for error in errors
                    ]
                },
            )

    def _apply_pre_mapping_defaults(self, protocol: dict[str, Any], question: str) -> dict[str, Any]:
        candidate = deepcopy(protocol)
        candidate.setdefault("schema_version", "1.0.0")
        candidate["original_question"] = question
        candidate.setdefault("normalized_question", question)
        candidate.setdefault("protocol_status", "needs_mapping")
        candidate.setdefault("assumptions", [])
        candidate.setdefault("issues", {"warnings": [], "blocking_errors": []})
        candidate.setdefault(
            "execution",
            {
                "human_review_required": True,
                "human_mapping_confirmation_required": True,
                "sql_template": candidate.get("study_type"),
                "ready_for_execution": False,
            },
        )
        if isinstance(candidate.get("execution"), dict):
            candidate["execution"]["human_review_required"] = True
            candidate["execution"]["human_mapping_confirmation_required"] = True
            candidate["execution"]["ready_for_execution"] = False
            candidate["execution"]["sql_template"] = candidate.get("study_type")
        for concept_set in candidate.get("concept_sets", []):
            concept_set["mapping"] = {
                "status": "unmapped",
                "omop_concept_id": None,
                "omop_concept_name": None,
                "candidate_concepts": [],
            }
        return candidate

    def _validate_protocol(self, protocol: dict[str, Any]) -> None:
        errors = sorted(self.validator.iter_errors(protocol), key=lambda err: list(err.path))
        if errors:
            raise LLMError(
                "The LLM output did not validate against the protocol schema.",
                kind="schema_validation",
                details={
                    "errors": [
                        {"path": self._format_error_path(error.absolute_path), "message": error.message}
                        for error in errors
                    ]
                },
            )

    @staticmethod
    def _format_error_path(path: Iterable[Any]) -> str:
        parts = [str(part) for part in path]
        return ".".join(parts) if parts else "<root>"

    @staticmethod
    def _load_schema(schema_path: Path) -> dict[str, Any]:
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LLMError(f"Schema file not found: {schema_path}", kind="schema_file_missing") from exc
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Schema file is not valid JSON: {schema_path}",
                kind="schema_file_invalid",
                details={"error": str(exc)},
            ) from exc

    def _load_and_validate_mock_protocol(self, question: str) -> dict[str, Any]:
        mock_path = Path(self.config.mock_protocol_path or "")
        try:
            protocol = json.loads(mock_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LLMError(f"Mock protocol file not found: {mock_path}", kind="mock_file_missing") from exc
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Mock protocol file is not valid JSON: {mock_path}",
                kind="mock_file_invalid",
                details={"error": str(exc)},
            ) from exc
        protocol["original_question"] = question
        protocol = self._apply_pre_mapping_defaults(protocol, question)
        self._validate_protocol(protocol)
        return protocol

    # ---------------------------------------------------------------------
    # Small interpretation schema
    # ---------------------------------------------------------------------
    def _build_interpretation_schema(self) -> dict[str, Any]:
        domain_enum = ["condition", "drug", "procedure", "measurement", "observation", "visit"]
        measure_enum = ["cohort_size", "demographics", "incidence_rate", "event_count", "person_time"]
        stratify_enum = ["sex", "age_group"]
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "study_type",
                "normalized_question",
                "target",
                "comparator",
                "outcome",
                "demographics",
                "requested_outputs",
                "assumptions",
            ],
            "properties": {
                "study_type": {"type": "string", "enum": ["cohort_characterization", "incidence_analysis"]},
                "normalized_question": {"type": "string", "minLength": 1},
                "target": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "index", "include", "exclude"],
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "index": {"$ref": "#/$defs/conceptTerm"},
                        "include": {"type": "array", "items": {"$ref": "#/$defs/criterionTerm"}},
                        "exclude": {"type": "array", "items": {"$ref": "#/$defs/criterionTerm"}},
                    },
                },
                "comparator": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["enabled", "label", "index", "include", "exclude"],
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "label": {"type": ["string", "null"]},
                        "index": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/conceptTerm"}]},
                        "include": {"type": "array", "items": {"$ref": "#/$defs/criterionTerm"}},
                        "exclude": {"type": "array", "items": {"$ref": "#/$defs/criterionTerm"}},
                    },
                },
                "outcome": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["required", "term", "incident_only", "clean_period_days"],
                    "properties": {
                        "required": {"type": "boolean"},
                        "term": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/conceptTerm"}]},
                        "incident_only": {"type": "boolean"},
                        "clean_period_days": {"type": ["integer", "null"], "minimum": 0},
                    },
                },
                "demographics": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["min_age", "max_age", "sex"],
                    "properties": {
                        "min_age": {"type": ["integer", "null"]},
                        "max_age": {"type": ["integer", "null"]},
                        "sex": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["male", "female", "unknown"]},
                            "uniqueItems": True,
                        },
                    },
                },
                "requested_outputs": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["measures", "stratify_by"],
                    "properties": {
                        "measures": {"type": "array", "items": {"type": "string", "enum": measure_enum}, "minItems": 1, "uniqueItems": True},
                        "stratify_by": {"type": "array", "items": {"type": "string", "enum": stratify_enum}, "uniqueItems": True},
                    },
                },
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "$defs": {
                "conceptTerm": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["raw_text", "domain"],
                    "properties": {
                        "raw_text": {"type": "string", "minLength": 1},
                        "domain": {"type": "string", "enum": domain_enum},
                    },
                },
                "criterionTerm": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["raw_text", "domain", "min_occurrences", "timing"],
                    "properties": {
                        "raw_text": {"type": "string", "minLength": 1},
                        "domain": {"type": "string", "enum": domain_enum},
                        "min_occurrences": {"type": ["integer", "null"], "minimum": 1},
                        "timing": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["start_day_offset", "end_day_offset"],
                            "properties": {
                                "start_day_offset": {"type": ["integer", "null"]},
                                "end_day_offset": {"type": ["integer", "null"]},
                                "relation_to_index": {"type": "string", "enum": ["before", "after", "on_or_before", "on_or_after", "during"]},
                            },
                        },
                        "criterion_id": {"type": "string"},
                        "rule_type": {"type": "string", "enum": ["has", "not_has", "value_compare"]},
                        "operator": {"type": "string", "enum": ["exists", "eq", "neq", "gt", "gte", "lt", "lte", "between"]},
                        "value": {"oneOf": [{"type": "null"}, {"type": "string"}, {"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}]},
                        "unit": {"type": ["string", "null"]},
                    },
                },
            },
        }

    @staticmethod
    def _preferred_vocab_for_domain(domain: str | None) -> str | None:
        normalized = (domain or "").strip().lower()
        if normalized in {"condition", "procedure", "observation", "visit"}:
            return "SNOMED"
        if normalized == "drug":
            return "RxNorm"
        if normalized == "measurement":
            return "LOINC"
        return None

    @staticmethod
    def _criterion_domain_from_concept_domain(domain: str) -> str:
        normalized = domain.strip().lower()
        if normalized == "drug":
            return "drug_exposure"
        return normalized

    @staticmethod
    def _event_type_from_concept_domain(domain: str) -> str:
        normalized = domain.strip().lower()
        if normalized == "drug":
            return "drug_exposure"
        return normalized
