from __future__ import annotations

import csv
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from jsonschema import Draft202012Validator


class AthenaError(Exception):
    """Raised when concept mapping cannot proceed safely."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = "athena"
        self.kind = kind
        self.details = details or {}


@dataclass(slots=True)
class AthenaApiConfig:
    base_url: str | None = None
    search_path: str = "/search"
    query_param: str = "q"
    timeout_seconds: int = 10
    enabled: bool = True


@dataclass(slots=True)
class LocalVocabularyConfig:
    concept_csv_path: str
    concept_relationship_csv_path: str
    concept_synonym_csv_path: str | None = None
    candidate_limit: int = 5
    ambiguity_delta: int = 15
    minimum_match_score: int = 120
    prefer_local: bool = False


@dataclass(slots=True)
class VocabularyConcept:
    concept_id: int
    concept_name: str
    vocabulary_id: str
    domain_id: str
    standard_concept: str | None
    invalid_reason: str | None


@dataclass(slots=True)
class Candidate:
    omop_concept_id: int
    concept_name: str
    vocabulary_id: str
    score: int


class LocalAthenaVocabulary:
    """
    Deterministic local matcher over ATHENA export files.

    Matching strategy, in order:
    1. normalized exact concept-name match
    2. normalized exact synonym match
    3. normalized prefix match
    4. token-overlap ranking

    The scoring function is entirely rule-based and stable. If the top two
    candidates are too close, the result is marked ambiguous instead of guessed.
    """

    VOCAB_BONUS = {"SNOMED": 25, "RxNorm": 25, "LOINC": 25}
    DOMAIN_MAP = {
        "condition": "condition",
        "drug": "drug",
        "drug_exposure": "drug",
        "procedure": "procedure",
        "measurement": "measurement",
        "observation": "observation",
        "visit": "visit",
    }

    def __init__(self, config: LocalVocabularyConfig) -> None:
        self.config = config
        self.concepts: dict[int, VocabularyConcept] = {}
        self.maps_to_standard: dict[int, int] = {}
        self.name_index: dict[str, list[int]] = {}
        self.synonym_index: dict[str, list[int]] = {}
        self._load()

    def search(
        self,
        raw_text: str,
        *,
        domain: str,
        vocabulary_preference: str | None,
    ) -> dict[str, Any]:
        normalized = self._normalize(raw_text)
        if not normalized:
            return self._unmapped_result()

        exact_name_ids = self.name_index.get(normalized, [])
        exact_synonym_ids = self.synonym_index.get(normalized, [])

        candidate_scores: dict[int, int] = {}
        for concept_id in exact_name_ids:
            self._boost(candidate_scores, concept_id, 1000)
        for concept_id in exact_synonym_ids:
            self._boost(candidate_scores, concept_id, 950)

        if not candidate_scores:
            for concept_id, concept in self.concepts.items():
                if concept.invalid_reason:
                    continue
                name = self._normalize(concept.concept_name)
                if name.startswith(normalized):
                    self._boost(candidate_scores, concept_id, 800)
                elif normalized in name:
                    self._boost(candidate_scores, concept_id, 600)

        if not candidate_scores and self.synonym_index:
            for synonym, concept_ids in self.synonym_index.items():
                if synonym.startswith(normalized):
                    for concept_id in concept_ids:
                        self._boost(candidate_scores, concept_id, 760)
                elif normalized in synonym:
                    for concept_id in concept_ids:
                        self._boost(candidate_scores, concept_id, 560)

        if not candidate_scores:
            query_tokens = set(normalized.split())
            for concept_id, concept in self.concepts.items():
                if concept.invalid_reason:
                    continue
                concept_tokens = set(self._normalize(concept.concept_name).split())
                overlap = len(query_tokens & concept_tokens)
                if overlap == 0:
                    continue
                coverage = overlap / max(len(query_tokens), 1)
                score = int(100 * coverage + 25 * overlap)
                self._boost(candidate_scores, concept_id, score)

        ranked = self._rank_candidates(
            candidate_scores,
            domain=domain,
            vocabulary_preference=vocabulary_preference,
        )
        if not ranked:
            return self._unmapped_result()

        limited = ranked[: self.config.candidate_limit]
        top = limited[0]
        second = limited[1] if len(limited) > 1 else None

        if top.score < self.config.minimum_match_score:
            return self._unmapped_result()

        if second and abs(top.score - second.score) <= self.config.ambiguity_delta:
            return {
                "status": "ambiguous",
                "omop_concept_id": None,
                "omop_concept_name": None,
                "candidate_concepts": [self._candidate_payload(item) for item in limited],
            }

        return {
            "status": "mapped",
            "omop_concept_id": top.omop_concept_id,
            "omop_concept_name": top.concept_name,
            "candidate_concepts": [self._candidate_payload(item) for item in limited],
        }

    def _rank_candidates(
        self,
        scores: dict[int, int],
        *,
        domain: str,
        vocabulary_preference: str | None,
    ) -> list[Candidate]:
        domain_target = self.DOMAIN_MAP.get(domain, domain).lower()
        candidates: list[Candidate] = []

        for raw_concept_id, base_score in scores.items():
            concept_id = self._resolve_standard_id(raw_concept_id)
            concept = self.concepts.get(concept_id)
            if not concept or concept.invalid_reason:
                continue

            score = base_score
            concept_domain = concept.domain_id.lower()
            if concept_domain == domain_target:
                score += 60
            elif domain_target not in concept_domain:
                score -= 200

            if concept.standard_concept == "S":
                score += 40
            if vocabulary_preference and concept.vocabulary_id == vocabulary_preference:
                score += self.VOCAB_BONUS.get(vocabulary_preference, 15)

            if score > 0:
                candidates.append(
                    Candidate(
                        omop_concept_id=concept.concept_id,
                        concept_name=concept.concept_name,
                        vocabulary_id=concept.vocabulary_id,
                        score=score,
                    )
                )

        candidates.sort(
            key=lambda item: (-item.score, item.vocabulary_id, item.concept_name.lower(), item.omop_concept_id)
        )

        deduped: list[Candidate] = []
        seen: set[int] = set()
        for candidate in candidates:
            if candidate.omop_concept_id in seen:
                continue
            seen.add(candidate.omop_concept_id)
            deduped.append(candidate)
        return deduped

    def _resolve_standard_id(self, concept_id: int) -> int:
        seen: set[int] = set()
        current = concept_id
        while current not in seen and current in self.maps_to_standard:
            seen.add(current)
            current = self.maps_to_standard[current]
        return current

    def _load(self) -> None:
        self._load_concepts(Path(self.config.concept_csv_path))
        self._load_relationships(Path(self.config.concept_relationship_csv_path))
        if self.config.concept_synonym_csv_path:
            self._load_synonyms(Path(self.config.concept_synonym_csv_path))

    def _load_concepts(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    concept_id = self._as_int(row, "concept_id")
                    concept_name = self._required_value(row, "concept_name")
                    vocabulary_id = self._required_value(row, "vocabulary_id")
                    domain_id = self._required_value(row, "domain_id")
                    standard_concept = self._optional_value(row, "standard_concept")
                    invalid_reason = self._optional_value(row, "invalid_reason")
                    concept = VocabularyConcept(
                        concept_id=concept_id,
                        concept_name=concept_name,
                        vocabulary_id=vocabulary_id,
                        domain_id=domain_id,
                        standard_concept=standard_concept,
                        invalid_reason=invalid_reason,
                    )
                    self.concepts[concept_id] = concept
                    normalized_name = self._normalize(concept_name)
                    self.name_index.setdefault(normalized_name, []).append(concept_id)
        except FileNotFoundError as exc:
            raise AthenaError(
                f"Concept CSV not found: {path}",
                kind="local_vocabulary_missing",
            ) from exc

    def _load_relationships(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    relationship_id = self._required_value(row, "relationship_id")
                    if relationship_id.lower() != "maps to":
                        continue
                    source_id = self._as_int(row, "concept_id_1")
                    target_id = self._as_int(row, "concept_id_2")
                    self.maps_to_standard[source_id] = target_id
        except FileNotFoundError as exc:
            raise AthenaError(
                f"Concept relationship CSV not found: {path}",
                kind="local_vocabulary_missing",
            ) from exc

    def _load_synonyms(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    concept_id = self._as_int(row, "concept_id")
                    synonym = self._optional_value(row, "concept_synonym_name")
                    if not synonym:
                        continue
                    normalized = self._normalize(synonym)
                    self.synonym_index.setdefault(normalized, []).append(concept_id)
        except FileNotFoundError as exc:
            raise AthenaError(
                f"Concept synonym CSV not found: {path}",
                kind="local_vocabulary_missing",
            ) from exc

    @staticmethod
    def _normalize(value: str) -> str:
        cleaned = value.lower().strip()
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _boost(scores: dict[int, int], concept_id: int, increment: int) -> None:
        scores[concept_id] = max(scores.get(concept_id, 0), increment)

    @staticmethod
    def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
        return {
            "omop_concept_id": candidate.omop_concept_id,
            "concept_name": candidate.concept_name,
            "vocabulary_id": candidate.vocabulary_id,
        }

    @staticmethod
    def _unmapped_result() -> dict[str, Any]:
        return {
            "status": "unmapped",
            "omop_concept_id": None,
            "omop_concept_name": None,
            "candidate_concepts": [],
        }

    @staticmethod
    def _normalize_header_map(row: dict[str, Any]) -> dict[str, Any]:
        return {key.lower(): value for key, value in row.items()}

    def _required_value(self, row: dict[str, Any], key: str) -> str:
        normalized_row = self._normalize_header_map(row)
        value = normalized_row.get(key.lower())
        if value is None or str(value).strip() == "":
            raise AthenaError(
                f"Required CSV column '{key}' is missing or empty.",
                kind="csv_shape",
                details={"row": row},
            )
        return str(value).strip()

    def _optional_value(self, row: dict[str, Any], key: str) -> str | None:
        normalized_row = self._normalize_header_map(row)
        value = normalized_row.get(key.lower())
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _as_int(self, row: dict[str, Any], key: str) -> int:
        value = self._required_value(row, key)
        try:
            return int(value)
        except ValueError as exc:
            raise AthenaError(
                f"Column '{key}' must contain an integer, got {value!r}.",
                kind="csv_shape",
                details={"row": row},
            ) from exc


class AthenaConceptResolver:
    def __init__(
        self,
        *,
        schema_path: str,
        api_config: AthenaApiConfig,
        local_config: LocalVocabularyConfig,
    ) -> None:
        self.api_config = api_config
        self.local_config = local_config
        self.local_vocabulary = LocalAthenaVocabulary(local_config)
        self.schema_path = Path(schema_path)
        self.schema = self._load_schema(self.schema_path)
        self.validator = Draft202012Validator(self.schema)

    def map_protocol(self, protocol: dict[str, Any]) -> dict[str, Any]:
        candidate = deepcopy(protocol)
        self._validate_protocol(candidate, stage="input")

        warnings = list(candidate.get("issues", {}).get("warnings", []))
        blocking_errors = list(candidate.get("issues", {}).get("blocking_errors", []))

        for concept_set in candidate.get("concept_sets", []):
            concept_ref = concept_set.get("concept_ref", "<unknown>")
            raw_text = concept_set.get("raw_text", "")
            domain = concept_set.get("domain", "condition")
            vocab_pref = concept_set.get("standard_vocab_preference")
            mapping_result: dict[str, Any] | None = None
            remote_failure: dict[str, Any] | None = None

            if self.api_config.enabled and self.api_config.base_url and not self.local_config.prefer_local:
                try:
                    mapping_result = self._search_remote(raw_text, domain=domain, vocabulary_preference=vocab_pref)
                except AthenaError as exc:
                    remote_failure = {"kind": exc.kind, "message": str(exc), "details": exc.details}
                    warnings.append(
                        {
                            "code": "ATHENA_API_FALLBACK",
                            "message": f"Remote Athena lookup failed for concept_ref={concept_ref}; falling back to local vocabulary.",
                            "field_path": f"concept_sets[{concept_ref}]",
                        }
                    )

            if mapping_result is None:
                mapping_result = self.local_vocabulary.search(
                    raw_text,
                    domain=domain,
                    vocabulary_preference=vocab_pref,
                )

            concept_set["mapping"] = mapping_result

            if mapping_result["status"] == "ambiguous":
                warnings.append(
                    {
                        "code": "AMBIGUOUS_CONCEPT",
                        "message": f"Concept '{raw_text}' matched multiple plausible OMOP concepts and needs human selection.",
                        "field_path": f"concept_sets.{concept_ref}",
                    }
                )
            elif mapping_result["status"] == "unmapped":
                blocking_errors.append(
                    {
                        "code": "UNMAPPED_CONCEPT",
                        "message": f"Concept '{raw_text}' could not be mapped to a standard OMOP concept.",
                        "field_path": f"concept_sets.{concept_ref}",
                    }
                )
            if remote_failure:
                warnings.append(
                    {
                        "code": "ATHENA_REMOTE_FAILURE_DETAIL",
                        "message": f"Remote Athena failure for concept_ref={concept_ref}: {remote_failure['message']}",
                        "field_path": f"concept_sets.{concept_ref}",
                    }
                )

        candidate.setdefault("issues", {})
        candidate["issues"]["warnings"] = warnings
        candidate["issues"]["blocking_errors"] = blocking_errors

        any_ambiguous = any(item["mapping"]["status"] == "ambiguous" for item in candidate.get("concept_sets", []))
        any_unmapped = any(item["mapping"]["status"] == "unmapped" for item in candidate.get("concept_sets", []))

        candidate.setdefault("execution", {})
        candidate["execution"]["human_review_required"] = True
        candidate["execution"]["human_mapping_confirmation_required"] = True
        candidate["execution"]["sql_template"] = candidate.get("study_type")

        if any_unmapped:
            candidate["protocol_status"] = "blocked"
            candidate["execution"]["ready_for_execution"] = False
        elif any_ambiguous:
            candidate["protocol_status"] = "needs_review"
            candidate["execution"]["ready_for_execution"] = False
        else:
            candidate["protocol_status"] = "executable"
            candidate["execution"]["ready_for_execution"] = True

        self._validate_protocol(candidate, stage="output")
        return candidate

    def _search_remote(
        self,
        raw_text: str,
        *,
        domain: str,
        vocabulary_preference: str | None,
    ) -> dict[str, Any]:
        if not self.api_config.base_url:
            raise AthenaError("Remote Athena base_url is not configured.", kind="athena_api_not_configured")

        url = f"{self.api_config.base_url.rstrip('/')}{self.api_config.search_path}"
        params = {self.api_config.query_param: raw_text, "domain": domain}
        if vocabulary_preference:
            params["vocabulary"] = vocabulary_preference

        try:
            response = requests.get(url, params=params, timeout=self.api_config.timeout_seconds)
        except requests.Timeout as exc:
            raise AthenaError(
                "Timed out while calling the remote Athena endpoint.",
                kind="athena_api_timeout",
                details={"timeout_seconds": self.api_config.timeout_seconds},
            ) from exc
        except requests.RequestException as exc:
            raise AthenaError(
                "Network error while calling the remote Athena endpoint.",
                kind="athena_api_network",
                details={"error": str(exc)},
            ) from exc

        if response.status_code >= 400:
            raise AthenaError(
                f"Remote Athena endpoint returned HTTP {response.status_code}.",
                kind="athena_api_http",
                details={"status_code": response.status_code, "response": response.text[:2000]},
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AthenaError(
                "Remote Athena endpoint did not return JSON.",
                kind="athena_api_response_shape",
                details={"response": response.text[:2000]},
            ) from exc

        candidates = self._extract_remote_candidates(payload)
        if not candidates:
            return {
                "status": "unmapped",
                "omop_concept_id": None,
                "omop_concept_name": None,
                "candidate_concepts": [],
            }

        if len(candidates) == 1:
            candidate = candidates[0]
            return {
                "status": "mapped",
                "omop_concept_id": candidate["omop_concept_id"],
                "omop_concept_name": candidate["concept_name"],
                "candidate_concepts": candidates,
            }

        return {
            "status": "ambiguous",
            "omop_concept_id": None,
            "omop_concept_name": None,
            "candidate_concepts": candidates[: self.local_config.candidate_limit],
        }

    def _extract_remote_candidates(self, payload: Any) -> list[dict[str, Any]]:
        raw_items: list[Any]
        if isinstance(payload, list):
            raw_items = payload
        elif isinstance(payload, dict):
            for key in ("results", "items", "candidates", "data"):
                if isinstance(payload.get(key), list):
                    raw_items = payload[key]
                    break
            else:
                raw_items = []
        else:
            raw_items = []

        candidates: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            concept_id = item.get("omop_concept_id") or item.get("concept_id") or item.get("conceptId")
            concept_name = item.get("concept_name") or item.get("conceptName") or item.get("name")
            vocabulary_id = item.get("vocabulary_id") or item.get("vocabularyId") or item.get("vocabulary")
            if concept_id is None or concept_name is None or vocabulary_id is None:
                continue
            try:
                concept_id = int(concept_id)
            except (TypeError, ValueError):
                continue
            candidates.append(
                {
                    "omop_concept_id": concept_id,
                    "concept_name": str(concept_name),
                    "vocabulary_id": str(vocabulary_id),
                }
            )
        return candidates[: self.local_config.candidate_limit]

    def _validate_protocol(self, protocol: dict[str, Any], *, stage: str) -> None:
        errors = sorted(self.validator.iter_errors(protocol), key=lambda err: list(err.path))
        if errors:
            raise AthenaError(
                f"Protocol failed schema validation at Athena {stage} stage.",
                kind="schema_validation",
                details={
                    "stage": stage,
                    "errors": [
                        {
                            "path": self._format_error_path(error.absolute_path),
                            "message": error.message,
                        }
                        for error in errors
                    ],
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
            raise AthenaError(
                f"Schema file not found: {schema_path}",
                kind="schema_file_missing",
            ) from exc
        except json.JSONDecodeError as exc:
            raise AthenaError(
                f"Schema file is not valid JSON: {schema_path}",
                kind="schema_file_invalid",
                details={"error": str(exc)},
            ) from exc
