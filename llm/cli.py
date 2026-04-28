from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from api import PipelineSettings, PipelineStageError, RWEGenAPI
from llm_module import VeniceModelConfig


EXAMPLE_QUESTIONS = [
    "Characterize adults with type 2 diabetes treated with metformin in the last 5 years.",
    "What is the incidence of chronic kidney disease after type 2 diabetes diagnosis in adults aged 40 to 75?",
    "Among adults with obesity, characterize patients who also have hypertension.",
    "What is the incidence of chronic kidney disease in type 2 diabetes patients compared with patients without diabetes?",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rwe-gen-cli",
        description=(
            "Developer CLI for the RWE-Gen pre-execution pipeline. It converts a clinician question "
            "into a validated protocol JSON, maps OMOP concepts, and builds populated OMOP SQL without executing it."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full pipeline: LLM -> concept mapping -> SQL.")
    add_shared_arguments(run_parser)
    run_parser.add_argument("question", help="Clinician question in natural language.")

    llm_parser = subparsers.add_parser("llm", help="Run only the LLM stage and print the protocol JSON.")
    add_shared_arguments(llm_parser, include_athena=False)
    llm_parser.add_argument("question", help="Clinician question in natural language.")

    concept_parser = subparsers.add_parser(
        "athena",
        aliases=["concept-mapping", "map"],
        help="Run only the concept mapping stage on a protocol JSON file.",
    )
    add_shared_arguments(concept_parser, include_llm=False)
    concept_parser.add_argument("--protocol-json", required=True, help="Path to the input protocol JSON file.")

    sql_parser = subparsers.add_parser("sql", help="Run only the SQL population stage on a mapped protocol JSON file.")
    add_shared_arguments(sql_parser, include_llm=False, include_athena=False)
    sql_parser.add_argument("--mapped-protocol-json", required=True, help="Path to the mapped protocol JSON file.")

    subparsers.add_parser("examples", help="Print example questions and example CLI calls.")
    return parser


def add_shared_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_llm: bool = True,
    include_athena: bool = True,
) -> None:
    parser.add_argument(
        "--schema-path",
        default=str(Path(__file__).resolve().parents[1] / "protocol_schema_validator.json"),
        help="Path to protocol_schema_validator.json.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs.")
    parser.add_argument("--save-output", help="Write the final command output to this JSON file.")
    parser.add_argument("--show-llm", action="store_true", help="Print the LLM protocol output.")
    parser.add_argument(
        "--show-athena",
        dest="show_concept_mapping",
        action="store_true",
        help="Print the concept mapping output (legacy flag name).",
    )
    parser.add_argument(
        "--show-concept-mapping",
        dest="show_concept_mapping",
        action="store_true",
        help="Print the concept mapping output.",
    )
    parser.add_argument("--show-sql", action="store_true", help="Print the populated SQL output.")

    if include_llm:
        parser.add_argument(
            "--venice-model",
            action="append",
            dest="venice_models",
            default=[],
            help=(
                "Model definition in the form model_name[:retries]. "
                "Repeat the flag to define fallback order. Example: --venice-model zai-org-glm-5:2 --venice-model kimi-k2-5:1"
            ),
        )
        parser.add_argument("--venice-api-key", help="Venice API key. If omitted, VENICE_API_KEY is used.")
        parser.add_argument("--venice-base-url", default="https://api.venice.ai/api/v1", help="Venice base URL.")
        parser.add_argument("--venice-timeout", type=int, default=60, help="Per-request timeout in seconds for Venice.")
        parser.add_argument(
            "--mock-protocol-json",
            help="Bypass Venice and load this protocol JSON file instead. Useful for local testing.",
        )
        parser.add_argument(
            "--include-venice-system-prompt",
            action="store_true",
            help="Pass Venice's extra system prompt through venice_parameters.",
        )
        parser.add_argument(
            "--enable-semantic-verification",
            action="store_true",
            help="Run an additional expert-review step after protocol generation using one or more verifier models.",
        )
        parser.add_argument(
            "--llm-verifier-model",
            action="append",
            dest="llm_verifier_models",
            default=[],
            help=(
                "Verifier model definition in the form model_name[:retries]. "
                "Repeat the flag to define verifier fallback order. Example: --llm-verifier-model kimi-k2-5:2"
            ),
        )
        parser.add_argument(
            "--llm-verifier-timeout",
            type=int,
            help="Per-request timeout in seconds for the semantic verification step. Defaults to --venice-timeout.",
        )

    if include_athena:
        parser.add_argument(
            "--concept-mapping-source",
            choices=["auto", "local", "remote"],
            default="auto",
            help=(
                "How to use the concept mapping sources. "
                "auto = remote IMO first with local fallback, local = local matcher only, remote = remote IMO only (no lexical local fallback)."
            ),
        )
        parser.add_argument("--athena-api-base-url", help="Optional LOF service base URL override for the remote IMO path.")
        parser.add_argument("--athena-api-search-path", default="/search", help=argparse.SUPPRESS)
        parser.add_argument("--athena-api-query-param", default="q", help=argparse.SUPPRESS)
        parser.add_argument("--athena-api-timeout", type=int, default=10, help="HTTP timeout for the remote IMO/LOF path.")
        parser.add_argument("--athena-disable-api", action="store_true", help="Legacy flag: use local concept mapping only.")
        parser.add_argument("--athena-prefer-local", action="store_true", help="Legacy flag: use local concept mapping only.")
        parser.add_argument("--athena-concept-csv", required=True, help="Path to ATHENA/OMOP CONCEPT.csv.")
        parser.add_argument("--athena-relationship-csv", required=True, help="Path to ATHENA/OMOP CONCEPT_RELATIONSHIP.csv.")
        parser.add_argument("--athena-synonym-csv", help="Path to ATHENA/OMOP CONCEPT_SYNONYM.csv.")
        parser.add_argument("--athena-candidate-limit", type=int, default=5, help="Maximum number of candidate concepts to keep.")
        parser.add_argument("--athena-ambiguity-delta", type=int, default=15, help="If top scores are within this delta, mark the result ambiguous.")
        parser.add_argument("--athena-minimum-match-score", type=int, default=120, help="Minimum deterministic score required to accept a concept as mapped.")


def parse_models(raw_models: list[str]) -> list[VeniceModelConfig]:
    if not raw_models:
        return [VeniceModelConfig(name="zai-org-glm-5", retries=2), VeniceModelConfig(name="kimi-k2-5", retries=2)]
    parsed: list[VeniceModelConfig] = []
    for raw in raw_models:
        if ":" in raw:
            name, retries_text = raw.split(":", 1)
            parsed.append(VeniceModelConfig(name=name.strip(), retries=int(retries_text.strip())))
        else:
            parsed.append(VeniceModelConfig(name=raw.strip(), retries=2))
    return parsed


def resolve_concept_mapping_source(args: argparse.Namespace) -> str:
    source = getattr(args, "concept_mapping_source", "auto")
    if getattr(args, "athena_disable_api", False) or getattr(args, "athena_prefer_local", False):
        return "local"
    return source


def build_settings(args: argparse.Namespace) -> PipelineSettings:
    settings_kwargs: dict[str, Any] = {
        "schema_path": args.schema_path,
    }

    if hasattr(args, "venice_models"):
        settings_kwargs.update(
            {
                "venice_api_key": getattr(args, "venice_api_key", None),
                "venice_base_url": getattr(args, "venice_base_url", "https://api.venice.ai/api/v1"),
                "venice_timeout_seconds": getattr(args, "venice_timeout", 60),
                "venice_models": parse_models(getattr(args, "venice_models", [])),
                "llm_mock_protocol_path": getattr(args, "mock_protocol_json", None),
                "include_venice_system_prompt": getattr(args, "include_venice_system_prompt", False),
                "llm_semantic_verification_enabled": getattr(args, "enable_semantic_verification", False),
                "llm_verification_models": parse_models(getattr(args, "llm_verifier_models", [])),
                "llm_verification_timeout_seconds": getattr(args, "llm_verifier_timeout", None),
            }
        )

    if hasattr(args, "athena_concept_csv"):
        concept_mapping_source = resolve_concept_mapping_source(args)
        settings_kwargs.update(
            {
                "athena_api_base_url": getattr(args, "athena_api_base_url", None),
                "athena_api_search_path": getattr(args, "athena_api_search_path", "/search"),
                "athena_api_query_param": getattr(args, "athena_api_query_param", "q"),
                "athena_api_timeout_seconds": getattr(args, "athena_api_timeout", 10),
                "athena_api_enabled": concept_mapping_source != "local",
                "athena_concept_csv_path": args.athena_concept_csv,
                "athena_concept_relationship_csv_path": args.athena_relationship_csv,
                "athena_concept_synonym_csv_path": getattr(args, "athena_synonym_csv", None),
                "athena_candidate_limit": getattr(args, "athena_candidate_limit", 5),
                "athena_ambiguity_delta": getattr(args, "athena_ambiguity_delta", 15),
                "athena_minimum_match_score": getattr(args, "athena_minimum_match_score", 120),
                "athena_prefer_local": concept_mapping_source == "local",
                "concept_mapping_source": concept_mapping_source,
            }
        )

    return PipelineSettings(**settings_kwargs)


def pretty_json(data: Any, pretty: bool) -> str:
    if pretty:
        return json.dumps(data, indent=2, ensure_ascii=False)
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def save_output(path: str | None, payload: Any, *, pretty: bool) -> None:
    if not path:
        return
    Path(path).write_text(pretty_json(payload, pretty), encoding="utf-8")


def print_stage(title: str, payload: Any, *, pretty: bool) -> None:
    print(f"\n=== {title} ===")
    if isinstance(payload, str):
        print(payload)
    else:
        print(pretty_json(payload, pretty))


def handle_pipeline_error(exc: PipelineStageError) -> int:
    print("\nPIPELINE ERROR", file=sys.stderr)
    print(f"stage : {exc.stage}", file=sys.stderr)
    print(f"kind  : {exc.kind}", file=sys.stderr)
    print(f"error : {exc}", file=sys.stderr)
    if exc.details:
        print("details:", file=sys.stderr)
        print(json.dumps(exc.details, indent=2, ensure_ascii=False), file=sys.stderr)
    return 2


def print_examples() -> None:
    print("Example clinician questions:\n")
    for index, question in enumerate(EXAMPLE_QUESTIONS, start=1):
        print(f"{index}. {question}")
    print("\nExample CLI calls:\n")
    print(
        "python cli.py run \\\n"
        "  --schema-path ../protocol_schema_validator.json \\\n"
        "  --concept-mapping-source auto \\\n"
        "  --athena-concept-csv /data/athena/CONCEPT.csv \\\n"
        "  --athena-relationship-csv /data/athena/CONCEPT_RELATIONSHIP.csv \\\n"
        "  --athena-synonym-csv /data/athena/CONCEPT_SYNONYM.csv \\\n"
        "  --show-llm --show-concept-mapping --show-sql --pretty \\\n"
        '  "What is the incidence of chronic kidney disease after type 2 diabetes diagnosis in adults aged 40 to 75?"'
    )
    print()
    print(
        "python cli.py concept-mapping \\\n"
        "  --schema-path ../protocol_schema_validator.json \\\n"
        "  --concept-mapping-source remote \\\n"
        "  --athena-concept-csv /data/athena/CONCEPT.csv \\\n"
        "  --athena-relationship-csv /data/athena/CONCEPT_RELATIONSHIP.csv \\\n"
        "  --athena-synonym-csv /data/athena/CONCEPT_SYNONYM.csv \\\n"
        "  --protocol-json ./protocol_from_llm.json \\\n"
        "  --pretty"
    )
    print()
    print(
        "python cli.py llm \\\n"
        "  --schema-path ../protocol_schema_validator.json \\\n"
        "  --venice-model zai-org-glm-5:2 \\\n"
        "  --enable-semantic-verification \\\n"
        "  --llm-verifier-model openai-gpt-54:1 \\\n"
        "  --pretty \\\n"
        '  "Characterize adults with type 2 diabetes treated with metformin in the last 5 years."'
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "examples":
        print_examples()
        return 0

    settings = build_settings(args)
    api = RWEGenAPI(settings)

    try:
        if args.command == "llm":
            protocol = api.generate_protocol(args.question)
            print_stage("LLM OUTPUT", protocol, pretty=args.pretty)
            save_output(args.save_output, protocol, pretty=args.pretty)
            return 0

        if args.command in {"athena", "concept-mapping", "map"}:
            protocol = json.loads(Path(args.protocol_json).read_text(encoding="utf-8"))
            mapped_protocol = api.map_protocol(protocol)
            print_stage("CONCEPT MAPPING OUTPUT", mapped_protocol, pretty=args.pretty)
            save_output(args.save_output, mapped_protocol, pretty=args.pretty)
            return 0

        if args.command == "sql":
            mapped_protocol = json.loads(Path(args.mapped_protocol_json).read_text(encoding="utf-8"))
            sql_result = api.populate_sql(mapped_protocol)
            payload = {
                "template_name": sql_result.template_name,
                "parameters": sql_result.parameters,
                "sql": sql_result.sql,
            }
            print_stage("SQL OUTPUT", payload, pretty=args.pretty)
            save_output(args.save_output, payload, pretty=args.pretty)
            return 0

        if args.command == "run":
            payload = api.run_pipeline(args.question)
            if args.show_llm:
                print_stage("LLM OUTPUT", payload["protocol"], pretty=args.pretty)
            if getattr(args, "show_concept_mapping", False):
                print_stage("CONCEPT MAPPING OUTPUT", payload["mapped_protocol"], pretty=args.pretty)
            if args.show_sql:
                print_stage("SQL OUTPUT", payload["sql"], pretty=args.pretty)
            if not any([args.show_llm, getattr(args, "show_concept_mapping", False), args.show_sql]):
                print_stage("PIPELINE OUTPUT", payload, pretty=args.pretty)
            save_output(args.save_output, payload, pretty=args.pretty)
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 1
    except PipelineStageError as exc:
        return handle_pipeline_error(exc)
    except FileNotFoundError as exc:
        error = PipelineStageError("cli", "file_missing", str(exc), details={"path": exc.filename})
        return handle_pipeline_error(error)
    except json.JSONDecodeError as exc:
        error = PipelineStageError(
            "cli",
            "json_parse",
            f"Failed to parse JSON file: {exc}",
            details={"line": exc.lineno, "column": exc.colno},
        )
        return handle_pipeline_error(error)
    except Exception as exc:  # pragma: no cover - safety net for developer CLI
        error = PipelineStageError("cli", "unexpected", str(exc))
        return handle_pipeline_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
