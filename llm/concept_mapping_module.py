from __future__ import annotations

import csv
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TextIO

import os

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
    # Kept backward-compatible with earlier CLI/API construction.
    base_url: str | None = None
    search_path: str = "/search"
    query_param: str = "q"
    timeout_seconds: int = 10
    enabled: bool = True
    use_athena_client: bool = False
    lof_token_path: str = "/generate-access-token/"
    imo_normalize_path: str = "/imo/normalize"
    source_mode: str = "auto"


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
    concept_code: str | None = None


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
        self.code_index: dict[tuple[str, str], list[int]] = {}
        self._raise_csv_field_limit()
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

    @staticmethod
    def _raise_csv_field_limit() -> None:
        limit = sys.maxsize
        while True:
            try:
                csv.field_size_limit(limit)
                return
            except OverflowError:
                limit = limit // 10
                if limit <= 0:
                    return

    @staticmethod
    def _sniff_delimiter(sample: str) -> str:
        delimiters = ["\t", ",", ";", "|"]
        lines = [line for line in sample.splitlines() if line.strip()][:5]
        if not lines:
            return ","

        try:
            dialect = csv.Sniffer().sniff("\n".join(lines), delimiters="\t,;|")
            return dialect.delimiter
        except csv.Error:
            counts = {d: sum(line.count(d) for line in lines) for d in delimiters}
            best = max(counts, key=counts.get)
            return best if counts[best] > 0 else ","

    def _open_dict_reader(self, path: Path) -> tuple[TextIO, csv.DictReader]:
        if path.is_dir():
            raise AthenaError(
                f"Expected a file but got a directory: {path}",
                kind="local_vocabulary_missing",
                details={"path": str(path)},
            )

        try:
            handle = path.open("r", encoding="utf-8-sig", newline="")
        except FileNotFoundError as exc:
            raise AthenaError(
                f"CSV not found: {path}",
                kind="local_vocabulary_missing",
            ) from exc

        try:
            sample = handle.read(65536)
            handle.seek(0)
            delimiter = self._sniff_delimiter(sample)
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise AthenaError(
                    f"CSV appears to be empty or missing a header row: {path}",
                    kind="csv_shape",
                    details={"path": str(path)},
                )
            return handle, reader
        except Exception:
            handle.close()
            raise

    def _load_concepts(self, path: Path) -> None:
        try:
            handle, reader = self._open_dict_reader(path)
            with handle:
                for row in reader:
                    concept_id = self._as_int(row, "concept_id")
                    concept_name = self._required_value(row, "concept_name")
                    vocabulary_id = self._required_value(row, "vocabulary_id")
                    domain_id = self._required_value(row, "domain_id")
                    standard_concept = self._optional_value(row, "standard_concept")
                    invalid_reason = self._optional_value(row, "invalid_reason")
                    concept_code = self._optional_value(row, "concept_code")
                    concept = VocabularyConcept(
                        concept_id=concept_id,
                        concept_name=concept_name,
                        vocabulary_id=vocabulary_id,
                        domain_id=domain_id,
                        standard_concept=standard_concept,
                        invalid_reason=invalid_reason,
                        concept_code=concept_code,
                    )
                    self.concepts[concept_id] = concept
                    normalized_name = self._normalize(concept_name)
                    self.name_index.setdefault(normalized_name, []).append(concept_id)
                    if concept_code:
                        code_key = (self._normalize_vocabulary_id(vocabulary_id), concept_code.strip())
                        self.code_index.setdefault(code_key, []).append(concept_id)
        except csv.Error as exc:
            raise AthenaError(
                f"Failed to parse concept CSV: {path}",
                kind="csv_shape",
                details={"path": str(path), "error": str(exc)},
            ) from exc
    def _load_relationships(self, path: Path) -> None:
        try:
            handle, reader = self._open_dict_reader(path)
            with handle:
                for row in reader:
                    relationship_id = self._required_value(row, "relationship_id")
                    if relationship_id.lower() != "maps to":
                        continue
                    source_id = self._as_int(row, "concept_id_1")
                    target_id = self._as_int(row, "concept_id_2")
                    self.maps_to_standard[source_id] = target_id
        except csv.Error as exc:
            raise AthenaError(
                f"Failed to parse concept relationship CSV: {path}",
                kind="csv_shape",
                details={"path": str(path), "error": str(exc)},
            ) from exc

    def _load_synonyms(self, path: Path) -> None:
        try:
            handle, reader = self._open_dict_reader(path)
            with handle:
                for row in reader:
                    concept_id = self._as_int(row, "concept_id")
                    synonym = self._optional_value(row, "concept_synonym_name")
                    if not synonym:
                        continue
                    normalized = self._normalize(synonym)
                    self.synonym_index.setdefault(normalized, []).append(concept_id)
        except csv.Error as exc:
            raise AthenaError(
                f"Failed to parse concept synonym CSV: {path}",
                kind="csv_shape",
                details={"path": str(path), "error": str(exc)},
            ) from exc

    @staticmethod
    def _normalize_vocabulary_id(vocabulary_id: str | None) -> str:
        raw = (vocabulary_id or "").strip()
        compact = re.sub(r"[^A-Za-z0-9]+", "", raw).upper()
        mapping = {
            "SNOMED": "SNOMED",
            "SNOMEDCT": "SNOMED",
            "SNOMEDINTERNATIONAL": "SNOMED",
            "RXNORM": "RxNorm",
            "LOINC": "LOINC",
            "CPT": "CPT4",
            "CPT4": "CPT4",
            "HCPCS": "HCPCS",
            "ICD10CM": "ICD10CM",
            "ICD9CM": "ICD9CM",
        }
        return mapping.get(compact, raw)

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
        return {str(key).lower(): value for key, value in row.items() if key is not None}

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
    DEFAULT_LOF_BASE_URL = "https://api.leapoffaith.com/api/service"
    IMO_DOMAIN_MAP = {
        "condition": "Problem",
        "drug": "Medication",
        "drug_exposure": "Medication",
        "procedure": "Procedure",
    }

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
        self.source_mode = self._normalize_source_mode(self.api_config.source_mode)
        self.remote_client = self._build_remote_client()
        self._lof_access_token: str | None = None

    @staticmethod
    def _normalize_source_mode(source_mode: str | None) -> str:
        normalized = (source_mode or "auto").strip().lower()
        if normalized not in {"auto", "local", "remote"}:
            raise AthenaError(
                f"Unsupported concept-mapping source mode: {source_mode!r}",
                kind="invalid_source_mode",
                details={"source_mode": source_mode},
            )
        return normalized

    def _ensure_source_mode_ready(self) -> None:
        if self.source_mode == "remote" and not self.api_config.enabled:
            raise AthenaError(
                "Remote-only concept mapping was requested but remote access is disabled.",
                kind="remote_forced_disabled",
            )
        if self.source_mode == "remote" and self.remote_client is None:
            raise AthenaError(
                "Remote-only concept mapping was requested but LOF/IMO credentials were not found in the environment.",
                kind="remote_forced_unavailable",
            )

    def map_protocol(self, protocol: dict[str, Any]) -> dict[str, Any]:
        candidate = deepcopy(protocol)
        self._validate_protocol(candidate, stage="input")

        self._ensure_source_mode_ready()

        warnings = list(candidate.get("issues", {}).get("warnings", []))
        blocking_errors = list(candidate.get("issues", {}).get("blocking_errors", []))
        warnings.extend(self._remote_mode_warnings())

        for concept_set in candidate.get("concept_sets", []):
            concept_ref = concept_set.get("concept_ref", "<unknown>")
            raw_text = concept_set.get("raw_text", "")
            domain = concept_set.get("domain", "condition")
            vocab_pref = concept_set.get("standard_vocab_preference")
            mapping_result: dict[str, Any] | None = None
            remote_failure: dict[str, Any] | None = None

            if self._should_attempt_remote():
                try:
                    mapping_result, remote_source = self._search_remote(
                        raw_text,
                        domain=domain,
                        vocabulary_preference=vocab_pref,
                    )
                    if mapping_result["status"] == "unmapped":
                        if self.source_mode == "remote":
                            warnings.append(
                                {
                                    "code": "IMO_REMOTE_NO_MATCH",
                                    "message": f"Remote IMO normalize returned no OMOP-resolved concept for concept_ref={concept_ref}; remote-only mode prevents local fallback.",
                                    "field_path": f"concept_sets.{concept_ref}",
                                }
                            )
                        else:
                            warnings.append(
                                {
                                    "code": "IMO_REMOTE_NO_MATCH",
                                    "message": f"Remote IMO normalize returned no OMOP-resolved concept for concept_ref={concept_ref}; falling back to local vocabulary.",
                                    "field_path": f"concept_sets.{concept_ref}",
                                }
                            )
                            mapping_result = None
                    else:
                        warnings.append(
                            {
                                "code": "IMO_REMOTE_USED",
                                "message": f"Remote IMO normalize used for concept_ref={concept_ref} via {remote_source}.",
                                "field_path": f"concept_sets.{concept_ref}",
                            }
                        )
                except AthenaError as exc:
                    remote_failure = {"kind": exc.kind, "message": str(exc), "details": exc.details}
                    if self.source_mode == "remote":
                        raise AthenaError(
                            f"Remote-only concept mapping failed for concept_ref={concept_ref}.",
                            kind="remote_forced_failed",
                            details={
                                "concept_ref": concept_ref,
                                "raw_text": raw_text,
                                "remote_error": remote_failure,
                            },
                        ) from exc
                    warnings.append(
                        {
                            "code": "IMO_API_FALLBACK",
                            "message": f"Remote IMO normalize failed for concept_ref={concept_ref}; falling back to local vocabulary.",
                            "field_path": f"concept_sets.{concept_ref}",
                        }
                    )

            if mapping_result is None and self.source_mode != "remote":
                mapping_result = self.local_vocabulary.search(
                    raw_text,
                    domain=domain,
                    vocabulary_preference=vocab_pref,
                )
                warnings.append(
                    {
                        "code": "ATHENA_LOCAL_USED",
                        "message": f"Local ATHENA vocabulary matcher used for concept_ref={concept_ref}.",
                        "field_path": f"concept_sets.{concept_ref}",
                    }
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
                        "code": "IMO_REMOTE_FAILURE_DETAIL",
                        "message": f"Remote IMO failure for concept_ref={concept_ref}: {remote_failure['message']}",
                        "field_path": f"concept_sets.{concept_ref}",
                    }
                )
                warnings.append(
                    {
                        "code": "IMO_REMOTE_FAILURE_KIND",
                        "message": f"Remote IMO failure kind={remote_failure['kind']} details={json.dumps(remote_failure['details'])[:500]}",
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

    def _build_remote_client(self) -> dict[str, Any] | None:
        if not self.api_config.enabled or self.source_mode == "local":
            return None

        client_id = (
            os.getenv("client_id")
            or os.getenv("CLIENT_ID")
            or os.getenv("IMO_CLIENT_ID")
            or os.getenv("IMO_API_KEY")
        )
        client_secret = (
            os.getenv("client_secret")
            or os.getenv("CLIENT_SECRET")
            or os.getenv("IMO_CLIENT_SECRET")
            or os.getenv("IMO_API_SECRET")
        )
        if not client_id or not client_secret:
            return None

        base_url = (self.api_config.base_url or self.DEFAULT_LOF_BASE_URL).rstrip("/")
        return {
            "base_url": base_url,
            "client_id": client_id,
            "client_secret": client_secret,
        }

    def _should_attempt_remote(self) -> bool:
        if self.source_mode == "local":
            return False
        if self.source_mode == "remote":
            return self.api_config.enabled and self.remote_client is not None
        return self.remote_client is not None and self.api_config.enabled

    def _remote_mode_warnings(self) -> list[dict[str, Any]]:
        if self.source_mode == "local":
            return [{
                "code": "IMO_REMOTE_SKIPPED",
                "message": "Remote IMO normalize was skipped because concept-mapping source was forced to local.",
                "field_path": None,
            }]
        if not self.api_config.enabled:
            return [{
                "code": "IMO_REMOTE_SKIPPED",
                "message": "Remote IMO normalize was skipped because remote API is disabled.",
                "field_path": None,
            }]
        if self.remote_client is not None:
            mode_note = "remote-only" if self.source_mode == "remote" else "remote-first with local fallback"
            return [{
                "code": "IMO_REMOTE_MODE",
                "message": f"Remote IMO normalize is enabled via LOF service proxy at {self.remote_client['base_url']} ({mode_note}).",
                "field_path": None,
            }]
        if self.source_mode == "remote":
            return [{
                "code": "IMO_REMOTE_MODE",
                "message": "Remote-only concept mapping was requested, but LOF/IMO credentials were not found in the environment.",
                "field_path": None,
            }]
        return [{
            "code": "IMO_REMOTE_SKIPPED",
            "message": "Remote IMO normalize was skipped because LOF/IMO credentials were not found in the environment.",
            "field_path": None,
        }]

    def _search_remote(
        self,
        raw_text: str,
        *,
        domain: str,
        vocabulary_preference: str | None,
    ) -> tuple[dict[str, Any], str]:
        return (
            self._search_remote_via_lof_imo(
                raw_text,
                domain=domain,
                vocabulary_preference=vocabulary_preference,
            ),
            "lof-imo-normalize",
        )

    def _search_remote_via_lof_imo(
        self,
        raw_text: str,
        *,
        domain: str,
        vocabulary_preference: str | None,
    ) -> dict[str, Any]:
        remote_domain = self.IMO_DOMAIN_MAP.get(domain)
        if not remote_domain:
            raise AthenaError(
                f"IMO normalize is not configured for domain {domain!r}.",
                kind="imo_domain_unsupported",
                details={"domain": domain},
            )

        token = self._get_lof_access_token()
        url = f"{self.remote_client['base_url']}{self.api_config.imo_normalize_path}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "entities": [raw_text],
            "domain": remote_domain,
            "match_field": "input_term",
            "input_code_system": "",
            "threshold": 0,
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.api_config.timeout_seconds)
        except requests.Timeout as exc:
            raise AthenaError(
                "Timed out while calling the remote IMO normalize endpoint.",
                kind="imo_api_timeout",
                details={"timeout_seconds": self.api_config.timeout_seconds},
            ) from exc
        except requests.RequestException as exc:
            raise AthenaError(
                "Network error while calling the remote IMO normalize endpoint.",
                kind="imo_api_network",
                details={"error": str(exc)},
            ) from exc

        if response.status_code >= 400:
            body = self._safe_response_body(response)
            raise AthenaError(
                f"Remote IMO normalize endpoint returned HTTP {response.status_code}.",
                kind="imo_api_http",
                details={"status_code": response.status_code, "response": body},
            )

        try:
            remote_payload = response.json()
        except json.JSONDecodeError as exc:
            raise AthenaError(
                "Remote IMO normalize endpoint did not return JSON.",
                kind="imo_api_response_shape",
                details={"response": response.text[:2000]},
            ) from exc

        code_candidates = self._extract_imo_code_candidates(remote_payload)
        return self._resolve_remote_codes_to_omop(
            code_candidates,
            domain=domain,
            vocabulary_preference=vocabulary_preference,
        )

    def _get_lof_access_token(self) -> str:
        if self._lof_access_token:
            return self._lof_access_token
        if not self.remote_client:
            raise AthenaError(
                "LOF/IMO remote client is not configured.",
                kind="imo_not_configured",
            )

        url = f"{self.remote_client['base_url']}{self.api_config.lof_token_path}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "client_id": self.remote_client["client_id"],
            "client_secret": self.remote_client["client_secret"],
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.api_config.timeout_seconds)
        except requests.Timeout as exc:
            raise AthenaError(
                "Timed out while requesting the LOF access token.",
                kind="imo_auth_timeout",
                details={"timeout_seconds": self.api_config.timeout_seconds},
            ) from exc
        except requests.RequestException as exc:
            raise AthenaError(
                "Network error while requesting the LOF access token.",
                kind="imo_auth_network",
                details={"error": str(exc)},
            ) from exc

        if response.status_code >= 400:
            body = self._safe_response_body(response)
            raise AthenaError(
                f"LOF access-token endpoint returned HTTP {response.status_code}.",
                kind="imo_auth_http",
                details={"status_code": response.status_code, "response": body},
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AthenaError(
                "LOF access-token endpoint did not return JSON.",
                kind="imo_auth_response_shape",
                details={"response": response.text[:2000]},
            ) from exc

        access_token = payload.get("access_token")
        if not access_token:
            raise AthenaError(
                "LOF access-token response did not contain 'access_token'.",
                kind="imo_auth_response_shape",
                details={"response": payload},
            )
        self._lof_access_token = str(access_token)
        return self._lof_access_token

    def _extract_imo_code_candidates(self, payload: Any) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_candidate(vocabulary_id: str | None, concept_code: str | None, title: str | None = None) -> None:
            normalized_vocab = LocalAthenaVocabulary._normalize_vocabulary_id(vocabulary_id)
            code = (concept_code or "").strip()
            if not normalized_vocab or not code:
                return
            key = (normalized_vocab, code)
            if key in seen:
                return
            seen.add(key)
            candidates.append(
                {
                    "vocabulary_id": normalized_vocab,
                    "concept_code": code,
                    "title": (title or "").strip() or None,
                }
            )

        def extract_title_from_entry(entry: dict[str, Any]) -> str | None:
            for key in ("title", "name", "description", "preferred_term", "term"):
                value = entry.get(key)
                if value:
                    return str(value)
            rx_titles = entry.get("rxnorm_titles")
            if isinstance(rx_titles, list) and rx_titles:
                first = rx_titles[0]
                if isinstance(first, dict) and first.get("title"):
                    return str(first["title"])
            return None

        def extract_code_from_entry(entry: dict[str, Any]) -> str | None:
            for key in (
                "code",
                "rxnorm_code",
                "lexical_code",
                "concept_code",
                "code_value",
                "id",
            ):
                value = entry.get(key)
                if value:
                    return str(value)
            return None

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for raw_vocab_key, value in node.items():
                    normalized_vocab = LocalAthenaVocabulary._normalize_vocabulary_id(raw_vocab_key)
                    if normalized_vocab in {"SNOMED", "RxNorm", "LOINC", "CPT4", "HCPCS", "ICD10CM", "ICD9CM"}:
                        if isinstance(value, dict):
                            codes = value.get("codes")
                            if isinstance(codes, list):
                                for item in codes:
                                    if isinstance(item, dict):
                                        add_candidate(
                                            normalized_vocab,
                                            extract_code_from_entry(item),
                                            extract_title_from_entry(item),
                                        )
                        elif isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    add_candidate(
                                        normalized_vocab,
                                        extract_code_from_entry(item),
                                        extract_title_from_entry(item),
                                    )
                code_system = (
                    node.get("code_system")
                    or node.get("coding_system")
                    or node.get("codeSystem")
                    or node.get("vocabulary")
                    or node.get("vocabulary_id")
                )
                if code_system:
                    normalized_vocab = LocalAthenaVocabulary._normalize_vocabulary_id(str(code_system))
                    add_candidate(
                        normalized_vocab,
                        extract_code_from_entry(node),
                        extract_title_from_entry(node),
                    )
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        return candidates

    def _resolve_remote_codes_to_omop(
        self,
        code_candidates: list[dict[str, Any]],
        *,
        domain: str,
        vocabulary_preference: str | None,
    ) -> dict[str, Any]:
        if not code_candidates:
            return {
                "status": "unmapped",
                "omop_concept_id": None,
                "omop_concept_name": None,
                "candidate_concepts": [],
            }

        candidate_scores: dict[int, int] = {}
        for rank, code_candidate in enumerate(code_candidates):
            vocabulary_id = LocalAthenaVocabulary._normalize_vocabulary_id(code_candidate["vocabulary_id"])
            concept_code = str(code_candidate["concept_code"]).strip()
            matching_ids = self.local_vocabulary.code_index.get((vocabulary_id, concept_code), [])
            for concept_id in matching_ids:
                self.local_vocabulary._boost(candidate_scores, concept_id, max(1, 2000 - rank * 25))

        ranked = self.local_vocabulary._rank_candidates(
            candidate_scores,
            domain=domain,
            vocabulary_preference=vocabulary_preference,
        )
        if not ranked:
            return {
                "status": "unmapped",
                "omop_concept_id": None,
                "omop_concept_name": None,
                "candidate_concepts": [],
            }

        limited = ranked[: self.local_config.candidate_limit]
        top = limited[0]
        second = limited[1] if len(limited) > 1 else None

        if second and abs(top.score - second.score) <= self.local_config.ambiguity_delta:
            return {
                "status": "ambiguous",
                "omop_concept_id": None,
                "omop_concept_name": None,
                "candidate_concepts": [self.local_vocabulary._candidate_payload(item) for item in limited],
            }

        return {
            "status": "mapped",
            "omop_concept_id": top.omop_concept_id,
            "omop_concept_name": top.concept_name,
            "candidate_concepts": [self.local_vocabulary._candidate_payload(item) for item in limited],
        }

    @staticmethod
    def _safe_response_body(response: requests.Response) -> str:
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type.lower():
            try:
                return json.dumps(response.json())[:2000]
            except Exception:
                pass
        return response.text[:2000]

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
