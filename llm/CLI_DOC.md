# RWE-Gen Developer CLI Helper

This CLI exercises the full pre-execution pipeline:

1. clinician question -> protocol JSON through the Venice-backed LLM layer
2. protocol JSON -> OMOP concept mapping through the concept mapping layer
3. mapped protocol -> populated OMOP SQL through the SQL layer

The SQL is **never executed** by this codebase.

## Files

- `cli.py` — developer CLI
- `api.py` — single facade used by the CLI
- `llm_module.py` — Venice-backed protocol generation with retries, model fallback, and optional semantic verification
- `concept_mapping_module.py` — concept mapping with remote IMO-through-LOF plus deterministic local OMOP vocabulary fallback
- `athena_module.py` — compatibility shim that re-exports `concept_mapping_module.py`
- `omop_sql_module.py` — fixed SQL template population only

## Environment

For the live LLM path:

```bash
export VENICE_API_KEY="your-api-key"
```

For the remote IMO path through LOF:

```bash
export client_id="your_lof_client_id"
export client_secret="your_lof_client_secret"
```

The concept mapping stage still requires local OMOP vocabulary files even in remote mode, because remote codes are resolved to OMOP `concept_id` values locally.

## Key concept mapping modes

Use `--concept-mapping-source` to control source usage:

- `auto` — remote IMO first, local lexical fallback if needed
- `local` — local deterministic matcher only
- `remote` — remote IMO only, no lexical local fallback

Legacy compatibility flags:

- `--athena-disable-api` -> local only
- `--athena-prefer-local` -> local only

## Example commands

### 1. Full pipeline with all intermediate outputs

```bash
python cli.py run \
  --schema-path ../protocol_schema_validator.json \
  --concept-mapping-source auto \
  --athena-concept-csv /data/athena/CONCEPT.csv \
  --athena-relationship-csv /data/athena/CONCEPT_RELATIONSHIP.csv \
  --athena-synonym-csv /data/athena/CONCEPT_SYNONYM.csv \
  --show-llm --show-concept-mapping --show-sql --pretty \
  "What is the incidence of chronic kidney disease after type 2 diabetes diagnosis in adults aged 40 to 75?"
```

### 2. Only inspect LLM output with semantic verification

```bash
python cli.py llm \
  --schema-path ../protocol_schema_validator.json \
  --venice-model zai-org-glm-5:2 \
  --enable-semantic-verification \
  --llm-verifier-model openai-gpt-54:1 \
  --pretty \
  "Characterize adults with type 2 diabetes treated with metformin in the last 5 years."
```

### 3. Map a saved protocol JSON using local-only concept mapping

```bash
python cli.py concept-mapping \
  --schema-path ../protocol_schema_validator.json \
  --concept-mapping-source local \
  --athena-concept-csv /data/athena/CONCEPT.csv \
  --athena-relationship-csv /data/athena/CONCEPT_RELATIONSHIP.csv \
  --athena-synonym-csv /data/athena/CONCEPT_SYNONYM.csv \
  --protocol-json ./protocol_from_llm.json \
  --pretty
```

### 4. Map a saved protocol JSON using remote-only concept mapping

```bash
python cli.py concept-mapping \
  --schema-path ../protocol_schema_validator.json \
  --concept-mapping-source remote \
  --athena-concept-csv /data/athena/CONCEPT.csv \
  --athena-relationship-csv /data/athena/CONCEPT_RELATIONSHIP.csv \
  --athena-synonym-csv /data/athena/CONCEPT_SYNONYM.csv \
  --protocol-json ./protocol_from_llm.json \
  --pretty
```

### 5. Populate SQL from a saved mapped protocol only

```bash
python cli.py sql \
  --schema-path ../protocol_schema_validator.json \
  --mapped-protocol-json ./mapped_protocol.json \
  --pretty
```

## Deterministic local-matching approach

The local matcher is deliberately deterministic. It applies the same ordered rules every time:

1. normalized exact concept-name match
2. normalized exact synonym match
3. normalized prefix / substring match
4. token-overlap scoring
5. vocabulary and domain bonuses
6. standard-concept preference through `Maps to` resolution
7. ambiguity detection when top scores are too close

That makes local mapping inspectable, repeatable, and safe for debugging.

## Remote path summary

The remote path uses the LOF service proxy and IMO Normalize, not public Athena:

- get bearer token from `/generate-access-token/`
- call `/imo/normalize`
- extract codes such as SNOMED and RxNorm
- resolve those codes to OMOP concepts using local `CONCEPT.csv`

## Required local vocabulary files

The concept mapping layer expects local OMOP vocabulary exports:

- `CONCEPT.csv`
- `CONCEPT_RELATIONSHIP.csv`
- `CONCEPT_SYNONYM.csv` (optional but strongly recommended)

## Notes

- The preferred module name is now `concept_mapping_module.py`.
- The CLI still keeps `athena` as a command alias and `--athena-*` option names for backward compatibility.
- The current SQL populator supports the MVP study types only:
  - `cohort_characterization`
  - `incidence_analysis`
- The current SQL stage only builds SQL for protocols that are already fully executable.
