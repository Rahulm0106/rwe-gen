from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from concept_mapping_module import AthenaApiConfig, AthenaConceptResolver, AthenaError, LocalVocabularyConfig
from llm_module import LLMConfig, LLMError, ProtocolLLMGenerator, VeniceModelConfig
from omop_sql_module import OmopSqlTemplatePopulator, SqlBuildResult, SqlPopulationError


class PipelineStageError(Exception):
    """Unified error surface exposed to the CLI and future frontends."""

    def __init__(
        self,
        stage: str,
        kind: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.kind = kind
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "kind": self.kind,
            "message": str(self),
            "details": self.details,
        }


@dataclass(slots=True)
class PipelineSettings:
    schema_path: str
    venice_api_key: str | None = None
    venice_base_url: str = "https://api.venice.ai/api/v1"
    venice_timeout_seconds: int = 60
    venice_models: list[VeniceModelConfig] = field(default_factory=list)
    llm_mock_protocol_path: str | None = None
    include_venice_system_prompt: bool = False
    llm_semantic_verification_enabled: bool = False
    llm_verification_models: list[VeniceModelConfig] = field(default_factory=list)
    llm_verification_timeout_seconds: int | None = None
    athena_api_base_url: str | None = None
    athena_api_search_path: str = "/search"
    athena_api_query_param: str = "q"
    athena_api_timeout_seconds: int = 10
    athena_api_enabled: bool = True
    athena_concept_csv_path: str = ""
    athena_concept_relationship_csv_path: str = ""
    athena_concept_synonym_csv_path: str | None = None
    athena_candidate_limit: int = 5
    athena_ambiguity_delta: int = 15
    athena_minimum_match_score: int = 120
    athena_prefer_local: bool = False
    concept_mapping_source: str = "auto"


class RWEGenAPI:
    """
    Facade for the whole pre-execution pipeline.

    The CLI only talks to this class. Future interfaces can do the same.
    Concept mapping and SQL are initialized lazily so the `llm` command does not
    require local vocabulary files or OMOP-related setup.
    """

    def __init__(self, settings: PipelineSettings) -> None:
        self.settings = settings
        self.protocol_generator = ProtocolLLMGenerator(
            LLMConfig(
                schema_path=settings.schema_path,
                api_key=settings.venice_api_key,
                base_url=settings.venice_base_url,
                timeout_seconds=settings.venice_timeout_seconds,
                models=settings.venice_models,
                mock_protocol_path=settings.llm_mock_protocol_path,
                include_venice_system_prompt=settings.include_venice_system_prompt,
                semantic_verification_enabled=settings.llm_semantic_verification_enabled,
                verification_models=settings.llm_verification_models,
                verification_timeout_seconds=settings.llm_verification_timeout_seconds,
            )
        )
        self._concept_mapping_resolver: AthenaConceptResolver | None = None
        self._sql_populator: OmopSqlTemplatePopulator | None = None

    def _get_concept_mapping_resolver(self) -> AthenaConceptResolver:
        if self._concept_mapping_resolver is None:
            self._concept_mapping_resolver = AthenaConceptResolver(
                schema_path=self.settings.schema_path,
                api_config=AthenaApiConfig(
                    base_url=self.settings.athena_api_base_url,
                    search_path=self.settings.athena_api_search_path,
                    query_param=self.settings.athena_api_query_param,
                    timeout_seconds=self.settings.athena_api_timeout_seconds,
                    enabled=self.settings.athena_api_enabled,
                    source_mode=self.settings.concept_mapping_source,
                ),
                local_config=LocalVocabularyConfig(
                    concept_csv_path=self.settings.athena_concept_csv_path,
                    concept_relationship_csv_path=self.settings.athena_concept_relationship_csv_path,
                    concept_synonym_csv_path=self.settings.athena_concept_synonym_csv_path,
                    candidate_limit=self.settings.athena_candidate_limit,
                    ambiguity_delta=self.settings.athena_ambiguity_delta,
                    minimum_match_score=self.settings.athena_minimum_match_score,
                    prefer_local=self.settings.athena_prefer_local,
                ),
            )
        return self._concept_mapping_resolver

    def _get_sql_populator(self) -> OmopSqlTemplatePopulator:
        if self._sql_populator is None:
            self._sql_populator = OmopSqlTemplatePopulator()
        return self._sql_populator

    def generate_protocol(self, question: str) -> dict[str, Any]:
        try:
            return self.protocol_generator.generate_protocol(question)
        except LLMError as exc:
            raise PipelineStageError("llm", exc.kind, str(exc), details=exc.details) from exc

    def map_protocol(self, protocol: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._get_concept_mapping_resolver().map_protocol(protocol)
        except AthenaError as exc:
            raise PipelineStageError("athena", exc.kind, str(exc), details=exc.details) from exc

    def populate_sql(self, mapped_protocol: dict[str, Any]) -> SqlBuildResult:
        try:
            return self._get_sql_populator().populate(mapped_protocol)
        except SqlPopulationError as exc:
            raise PipelineStageError("sql", exc.kind, str(exc), details=exc.details) from exc

    def run_pipeline(self, question: str) -> dict[str, Any]:
        protocol = self.generate_protocol(question)
        mapped_protocol = self.map_protocol(protocol)
        sql_result = self.populate_sql(mapped_protocol)
        return {
            "question": question,
            "protocol": protocol,
            "mapped_protocol": mapped_protocol,
            "sql": {
                "template_name": sql_result.template_name,
                "sql": sql_result.sql,
                "parameters": sql_result.parameters,
            },
        }

    @classmethod
    def build_default(cls, *, schema_path: str) -> "RWEGenAPI":
        base_dir = Path(schema_path).resolve().parent
        return cls(
            PipelineSettings(
                schema_path=schema_path,
                athena_concept_csv_path=str(base_dir / "CONCEPT.csv"),
                athena_concept_relationship_csv_path=str(base_dir / "CONCEPT_RELATIONSHIP.csv"),
                athena_concept_synonym_csv_path=str(base_dir / "CONCEPT_SYNONYM.csv"),
            )
        )
