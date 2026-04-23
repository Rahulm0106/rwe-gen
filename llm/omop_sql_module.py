from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class SqlPopulationError(Exception):
    """Raised when a mapped protocol cannot be translated into SQL safely."""

    def __init__(self, message: str, *, kind: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.stage = "sql"
        self.kind = kind
        self.details = details or {}


@dataclass(slots=True)
class SqlBuildResult:
    template_name: str
    sql: str
    parameters: dict[str, Any]


class OmopSqlTemplatePopulator:
    """Populate fixed OMOP SQL templates from a concept-mapped protocol.

    This module never executes SQL. It only builds populated, inspectable SQL text.
    """

    EVENT_TABLES = {
        "condition": {
            "table": "condition_occurrence",
            "concept_column": "condition_concept_id",
            "date_column": "condition_start_date",
        },
        "drug_exposure": {
            "table": "drug_exposure",
            "concept_column": "drug_concept_id",
            "date_column": "drug_exposure_start_date",
        },
        "procedure": {
            "table": "procedure_occurrence",
            "concept_column": "procedure_concept_id",
            "date_column": "procedure_date",
        },
        "measurement": {
            "table": "measurement",
            "concept_column": "measurement_concept_id",
            "date_column": "measurement_date",
            "value_column": "value_as_number",
        },
        "observation": {
            "table": "observation",
            "concept_column": "observation_concept_id",
            "date_column": "observation_date",
        },
        "visit": {
            "table": "visit_occurrence",
            "concept_column": "visit_concept_id",
            "date_column": "visit_start_date",
        },
    }

    SEX_CONCEPTS = {
        "male": 8507,
        "female": 8532,
    }

    def populate(self, protocol: dict[str, Any]) -> SqlBuildResult:
        if protocol.get("protocol_status") != "executable":
            raise SqlPopulationError(
                "SQL population requires a protocol with protocol_status='executable'.",
                kind="protocol_not_executable",
                details={"protocol_status": protocol.get("protocol_status")},
            )
        if not protocol.get("execution", {}).get("ready_for_execution"):
            raise SqlPopulationError(
                "execution.ready_for_execution must be true before SQL can be built.",
                kind="protocol_not_ready",
            )

        study_type = protocol.get("study_type")
        if study_type not in {"cohort_characterization", "incidence_analysis"}:
            raise SqlPopulationError(
                f"Unsupported study_type: {study_type!r}",
                kind="unsupported_study_type",
            )

        parameters = self._collect_parameters(protocol)
        template_name = study_type
        if study_type == "cohort_characterization":
            sql = self._build_characterization_sql(protocol, parameters)
        else:
            sql = self._build_incidence_sql(protocol, parameters)
        return SqlBuildResult(template_name=template_name, sql=sql, parameters=parameters)

    def _collect_parameters(self, protocol: dict[str, Any]) -> dict[str, Any]:
        concept_lookup = {}
        for concept_set in protocol.get("concept_sets", []):
            mapping = concept_set.get("mapping", {})
            if mapping.get("status") != "mapped":
                raise SqlPopulationError(
                    f"Concept {concept_set.get('concept_ref')} is not mapped.",
                    kind="unmapped_concept",
                    details={"concept_set": concept_set},
                )
            concept_lookup[concept_set["concept_ref"]] = mapping["omop_concept_id"]

        return {
            "study_type": protocol["study_type"],
            "target_label": protocol["target_cohort"]["label"],
            "target_index_concept_ids": self._concept_ids_for_refs(
                concept_lookup, protocol["target_cohort"]["index_event"]["concept_refs"]
            ),
            "target_event_type": protocol["target_cohort"]["index_event"]["event_type"],
            "comparator_enabled": protocol["comparator"]["enabled"],
            "calendar_window": protocol["time_windows"]["calendar_window"],
            "prior_observation_days": protocol["time_windows"]["prior_observation"]["min_prior_observation_days"],
            "washout_days": protocol["time_windows"]["washout"]["washout_period_days"],
            "time_at_risk": protocol["time_windows"]["time_at_risk"],
            "outcome_required": protocol["outcome"]["required"],
            "outcome_concept_ids": self._concept_ids_for_refs(concept_lookup, protocol["outcome"]["concept_refs"]),
            "outcome_incident_only": protocol["outcome"]["incident_only"],
            "outcome_clean_period_days": protocol["outcome"]["clean_period_days"],
            "requested_outputs": protocol["requested_outputs"],
        }

    def _build_characterization_sql(self, protocol: dict[str, Any], parameters: dict[str, Any]) -> str:
        ctes = [
            self._build_cohort_cte("target", protocol["target_cohort"], protocol),
        ]
        select_blocks = [self._build_characterization_select("target", protocol["target_cohort"]["label"])]

        if protocol["comparator"]["enabled"]:
            ctes.append(self._build_cohort_cte("comparator", protocol["comparator"]["definition"], protocol))
            select_blocks.append(self._build_characterization_select("comparator", protocol["comparator"]["label"]))

        return (
            "-- OMOP cohort characterization SQL generated by RWE-Gen\n"
            "-- This SQL is populated only. It is not executed by this module.\n"
            "WITH\n"
            + ",\n".join(ctes)
            + "\n"
            + "\nUNION ALL\n".join(select_blocks)
            + ";\n"
        )

    def _build_incidence_sql(self, protocol: dict[str, Any], parameters: dict[str, Any]) -> str:
        if not protocol["outcome"]["required"]:
            raise SqlPopulationError(
                "Incidence analysis requires outcome.required=true.",
                kind="invalid_incidence_protocol",
            )

        ctes = [
            self._build_cohort_cte("target", protocol["target_cohort"], protocol),
            self._build_outcome_cte("target_outcomes", "target", protocol),
            self._build_incidence_summary_cte("target_summary", "target", protocol["target_cohort"]["label"]),
        ]
        final_selects = ["SELECT * FROM target_summary"]

        if protocol["comparator"]["enabled"]:
            ctes.append(self._build_cohort_cte("comparator", protocol["comparator"]["definition"], protocol))
            ctes.append(self._build_outcome_cte("comparator_outcomes", "comparator", protocol))
            ctes.append(
                self._build_incidence_summary_cte(
                    "comparator_summary",
                    "comparator",
                    protocol["comparator"]["label"],
                )
            )
            final_selects.append("SELECT * FROM comparator_summary")

        return (
            "-- OMOP incidence analysis SQL generated by RWE-Gen\n"
            "-- This SQL is populated only. It is not executed by this module.\n"
            "WITH\n"
            + ",\n".join(ctes)
            + "\n"
            + "\nUNION ALL\n".join(final_selects)
            + ";\n"
        )

    def _build_cohort_cte(self, alias: str, cohort_def: dict[str, Any], protocol: dict[str, Any]) -> str:
        index_event = cohort_def["index_event"]
        event_sql = self._event_sql_parts(index_event["event_type"])
        concept_ids = self._mapped_ids(protocol, index_event["concept_refs"])
        index_date_expr = self._index_date_expression(index_event["index_date_rule"], event_sql["date_column"])
        calendar_predicate = self._calendar_window_predicate(event_sql["date_column"], protocol)
        demographic_predicates = self._demographic_predicates(cohort_def.get("demographic_filters", {}), "index_event")
        prior_observation_clause = self._prior_observation_clause(protocol)
        washout_clause = self._washout_clause(index_event, protocol, event_alias="index_event")
        inclusion_predicates = self._criteria_predicates(cohort_def.get("inclusion_criteria", []), protocol, event_alias="index_event")
        exclusion_predicates = self._criteria_predicates(
            cohort_def.get("exclusion_criteria", []),
            protocol,
            event_alias="index_event",
            negate=True,
        )

        base_filters = [f"cohort_event.{event_sql['concept_column']} IN ({self._csv(concept_ids)})"]
        if calendar_predicate:
            base_filters.append(calendar_predicate.replace("event_date", f"cohort_event.{event_sql['date_column']}"))

        outer_filters = []
        if demographic_predicates:
            outer_filters.extend(demographic_predicates)
        if prior_observation_clause:
            outer_filters.append(prior_observation_clause)
        if washout_clause:
            outer_filters.append(washout_clause)
        outer_filters.extend(inclusion_predicates)
        outer_filters.extend(exclusion_predicates)

        return f"""{alias} AS (
    SELECT
        index_event.person_id,
        index_event.index_date,
        person.gender_concept_id,
        person.year_of_birth,
        person.month_of_birth,
        person.day_of_birth
    FROM (
        SELECT
            cohort_event.person_id,
            {index_date_expr} AS index_date
        FROM {event_sql['table']} cohort_event
        WHERE {' AND '.join(base_filters) if base_filters else '1=1'}
        GROUP BY cohort_event.person_id
    ) index_event
    JOIN person ON person.person_id = index_event.person_id
    WHERE {' AND '.join(outer_filters) if outer_filters else '1=1'}
)"""

    def _build_outcome_cte(self, alias: str, cohort_alias: str, protocol: dict[str, Any]) -> str:
        outcome = protocol["outcome"]
        outcome_sql = self._event_sql_parts("condition")
        outcome_ids = self._mapped_ids(protocol, outcome["concept_refs"])
        time_at_risk = protocol["time_windows"]["time_at_risk"]
        start_expr = self._risk_start_expression("c.index_date", time_at_risk)
        end_expr = self._risk_end_expression("c.index_date", time_at_risk)
        incident_clause = self._incident_outcome_clause(outcome, protocol)

        return f"""{alias} AS (
    SELECT
        c.person_id,
        MIN(o.{outcome_sql['date_column']}) AS outcome_date
    FROM {cohort_alias} c
    JOIN {outcome_sql['table']} o
      ON o.person_id = c.person_id
     AND o.{outcome_sql['concept_column']} IN ({self._csv(outcome_ids)})
     AND o.{outcome_sql['date_column']} >= {start_expr}
     AND o.{outcome_sql['date_column']} <= {end_expr}
    WHERE {incident_clause}
    GROUP BY c.person_id
)"""

    def _build_incidence_summary_cte(self, alias: str, cohort_alias: str, label: str) -> str:
        return f"""{alias} AS (
    SELECT
        '{self._escape_literal(label)}' AS population_label,
        COUNT(*) AS cohort_size,
        COUNT(o.person_id) AS event_count,
        SUM(
            GREATEST(
                EXTRACT(DAY FROM (
                    COALESCE(o.outcome_date, CURRENT_DATE) - c.index_date
                )),
                0
            )
        ) AS person_time_days,
        CASE
            WHEN SUM(GREATEST(EXTRACT(DAY FROM (COALESCE(o.outcome_date, CURRENT_DATE) - c.index_date)), 0)) = 0 THEN NULL
            ELSE COUNT(o.person_id)::numeric /
                 NULLIF(SUM(GREATEST(EXTRACT(DAY FROM (COALESCE(o.outcome_date, CURRENT_DATE) - c.index_date)), 0)), 0)
        END AS incidence_per_person_day
    FROM {cohort_alias} c
    LEFT JOIN {cohort_alias}_outcomes o ON o.person_id = c.person_id
)"""

    def _build_characterization_select(self, cohort_alias: str, label: str) -> str:
        return f"""SELECT
    '{self._escape_literal(label)}' AS population_label,
    COUNT(*) AS cohort_size,
    AVG(EXTRACT(YEAR FROM AGE(index_date, MAKE_DATE(year_of_birth, COALESCE(month_of_birth, 1), COALESCE(day_of_birth, 1))))) AS mean_age_at_index,
    SUM(CASE WHEN gender_concept_id = 8507 THEN 1 ELSE 0 END) AS male_count,
    SUM(CASE WHEN gender_concept_id = 8532 THEN 1 ELSE 0 END) AS female_count,
    SUM(CASE WHEN gender_concept_id NOT IN (8507, 8532) OR gender_concept_id IS NULL THEN 1 ELSE 0 END) AS unknown_sex_count
FROM {cohort_alias}"""

    def _criteria_predicates(
        self,
        criteria: list[dict[str, Any]],
        protocol: dict[str, Any],
        *,
        event_alias: str,
        negate: bool = False,
    ) -> list[str]:
        predicates: list[str] = []
        for criterion in criteria:
            domain = criterion["domain"]
            if domain == "demographic":
                raise SqlPopulationError(
                    "Demographic criteria inside inclusion/exclusion_criteria are not supported by the SQL populator. Use demographic_filters instead.",
                    kind="unsupported_criterion",
                    details={"criterion": criterion},
                )
            sql_parts = self._event_sql_parts(domain)
            concept_ids = self._mapped_ids(protocol, criterion["concept_refs"])
            date_predicate = self._timing_predicate(criterion["timing"], f"evt.{sql_parts['date_column']}", f"{event_alias}.index_date")

            where_clauses = [
                f"evt.person_id = {event_alias}.person_id",
                f"evt.{sql_parts['concept_column']} IN ({self._csv(concept_ids)})",
            ]
            if date_predicate:
                where_clauses.append(date_predicate)
            if criterion["rule_type"] == "value_compare":
                if domain != "measurement":
                    raise SqlPopulationError(
                        "value_compare criteria are only supported for measurement domain in the SQL populator.",
                        kind="unsupported_criterion",
                        details={"criterion": criterion},
                    )
                where_clauses.append(self._measurement_value_predicate(sql_parts['value_column'], criterion))

            subquery = (
                f"SELECT COUNT(*) FROM {sql_parts['table']} evt "
                f"WHERE {' AND '.join(where_clauses)}"
            )

            if criterion.get("min_occurrences"):
                predicate = f"(({subquery}) >= {criterion['min_occurrences']})"
            else:
                predicate = f"EXISTS ({subquery})"

            if criterion["rule_type"] == "not_has" or negate:
                predicate = f"NOT {predicate}"
            predicates.append(predicate)
        return predicates

    def _measurement_value_predicate(self, value_column: str, criterion: dict[str, Any]) -> str:
        operator = criterion["operator"]
        value = criterion["value"]
        if operator == "between":
            low, high = value
            return f"evt.{value_column} BETWEEN {self._num(low)} AND {self._num(high)}"
        operator_map = {
            "eq": "=",
            "neq": "<>",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
        }
        if operator not in operator_map:
            raise SqlPopulationError(
                f"Unsupported measurement operator: {operator}",
                kind="unsupported_criterion",
                details={"criterion": criterion},
            )
        return f"evt.{value_column} {operator_map[operator]} {self._num(value)}"

    def _prior_observation_clause(self, protocol: dict[str, Any]) -> str | None:
        days = protocol["time_windows"]["prior_observation"]["min_prior_observation_days"]
        if days is None:
            return None
        return (
            "EXISTS (SELECT 1 FROM observation_period op "
            "WHERE op.person_id = index_event.person_id "
            f"AND op.observation_period_start_date <= index_event.index_date - INTERVAL '{days} day' "
            "AND op.observation_period_end_date >= index_event.index_date)"
        )

    def _washout_clause(self, index_event: dict[str, Any], protocol: dict[str, Any], *, event_alias: str) -> str | None:
        washout_days = protocol["time_windows"]["washout"]["washout_period_days"]
        if washout_days is None:
            return None
        event_sql = self._event_sql_parts(index_event["event_type"])
        concept_ids = self._mapped_ids(protocol, index_event["concept_refs"])
        return (
            "NOT EXISTS (SELECT 1 FROM {table} prior_evt "
            "WHERE prior_evt.person_id = index_event.person_id "
            "AND prior_evt.{concept_col} IN ({concept_ids}) "
            "AND prior_evt.{date_col} < index_event.index_date "
            "AND prior_evt.{date_col} >= index_event.index_date - INTERVAL '{washout_days} day')"
        ).format(
            table=event_sql["table"],
            concept_col=event_sql["concept_column"],
            concept_ids=self._csv(concept_ids),
            date_col=event_sql["date_column"],
            washout_days=washout_days,
        )

    def _incident_outcome_clause(self, outcome: dict[str, Any], protocol: dict[str, Any]) -> str:
        if not outcome["incident_only"]:
            return "1=1"
        clean_days = outcome.get("clean_period_days")
        if clean_days is None:
            clean_days = 0
        outcome_sql = self._event_sql_parts("condition")
        outcome_ids = self._mapped_ids(protocol, outcome["concept_refs"])
        return (
            "NOT EXISTS (SELECT 1 FROM {table} prev_outcome "
            "WHERE prev_outcome.person_id = c.person_id "
            "AND prev_outcome.{concept_col} IN ({concept_ids}) "
            "AND prev_outcome.{date_col} < c.index_date "
            "AND prev_outcome.{date_col} >= c.index_date - INTERVAL '{clean_days} day')"
        ).format(
            table=outcome_sql["table"],
            concept_col=outcome_sql["concept_column"],
            concept_ids=self._csv(outcome_ids),
            date_col=outcome_sql["date_column"],
            clean_days=clean_days,
        )

    def _demographic_predicates(self, filters: dict[str, Any], cohort_event_alias: str) -> list[str]:
        predicates: list[str] = []
        age_filter = filters.get("age", {})
        min_age = age_filter.get("min")
        max_age = age_filter.get("max")
        age_expr = (
            "EXTRACT(YEAR FROM AGE(index_event.index_date, MAKE_DATE(person.year_of_birth, COALESCE(person.month_of_birth, 1), COALESCE(person.day_of_birth, 1))))"
        )
        if min_age is not None:
            predicates.append(f"{age_expr} >= {self._num(min_age)}")
        if max_age is not None:
            predicates.append(f"{age_expr} <= {self._num(max_age)}")

        sex_values = filters.get("sex", []) or []
        concept_ids = [self.SEX_CONCEPTS[value] for value in sex_values if value in self.SEX_CONCEPTS]
        if sex_values and concept_ids:
            predicates.append(f"person.gender_concept_id IN ({self._csv(concept_ids)})")
        return predicates

    def _calendar_window_predicate(self, date_column: str, protocol: dict[str, Any]) -> str | None:
        calendar_window = protocol["time_windows"]["calendar_window"]
        start_date = calendar_window.get("start_date")
        end_date = calendar_window.get("end_date")
        predicates = []
        if start_date:
            predicates.append(f"event_date >= DATE '{start_date}'")
        if end_date:
            predicates.append(f"event_date <= DATE '{end_date}'")
        if not predicates:
            return None
        return " AND ".join(predicates)

    def _index_date_expression(self, rule: str, date_column: str) -> str:
        if rule == "latest_in_window":
            return f"MAX(cohort_event.{date_column})"
        return f"MIN(cohort_event.{date_column})"

    def _risk_start_expression(self, index_date_sql: str, time_at_risk: dict[str, Any]) -> str:
        offset = time_at_risk["start_day_offset"]
        return f"{index_date_sql} + INTERVAL '{offset} day'"

    def _risk_end_expression(self, index_date_sql: str, time_at_risk: dict[str, Any]) -> str:
        end_anchor = time_at_risk["end_anchor"]
        max_followup_days = time_at_risk.get("max_followup_days")
        end_offset = time_at_risk.get("end_day_offset") or 0

        if end_anchor == "study_end":
            base = "CURRENT_DATE"
        elif end_anchor == "end_of_observation":
            base = (
                "(SELECT MAX(op.observation_period_end_date) FROM observation_period op "
                "WHERE op.person_id = c.person_id)"
            )
        elif end_anchor == "death":
            base = "COALESCE((SELECT death_date FROM death d WHERE d.person_id = c.person_id), CURRENT_DATE)"
        elif end_anchor == "index_date":
            base = index_date_sql
        else:
            base = "CURRENT_DATE"

        expr = f"({base}) + INTERVAL '{end_offset} day'"
        if max_followup_days is not None:
            expr = f"LEAST({expr}, {index_date_sql} + INTERVAL '{max_followup_days} day')"
        return expr

    def _timing_predicate(self, timing: dict[str, Any], event_date_sql: str, index_date_sql: str) -> str | None:
        relation = timing.get("relation_to_index")
        start_offset = timing.get("start_day_offset")
        end_offset = timing.get("end_day_offset")
        comparisons = []

        if start_offset is not None:
            comparisons.append(f"{event_date_sql} >= {index_date_sql} + INTERVAL '{start_offset} day'")
        if end_offset is not None:
            comparisons.append(f"{event_date_sql} <= {index_date_sql} + INTERVAL '{end_offset} day'")

        if not comparisons:
            relation_defaults = {
                "before": f"{event_date_sql} < {index_date_sql}",
                "after": f"{event_date_sql} > {index_date_sql}",
                "on_or_before": f"{event_date_sql} <= {index_date_sql}",
                "on_or_after": f"{event_date_sql} >= {index_date_sql}",
                "during": None,
            }
            return relation_defaults.get(relation)
        return " AND ".join(comparisons)

    def _event_sql_parts(self, event_type: str) -> dict[str, str]:
        if event_type not in self.EVENT_TABLES:
            raise SqlPopulationError(
                f"Unsupported event_type for SQL population: {event_type}",
                kind="unsupported_event_type",
            )
        return self.EVENT_TABLES[event_type]

    @staticmethod
    def _concept_ids_for_refs(concept_lookup: dict[str, int], refs: list[str]) -> list[int]:
        concept_ids = []
        for ref in refs:
            if ref not in concept_lookup:
                raise SqlPopulationError(
                    f"Missing mapped concept_ref: {ref}",
                    kind="missing_concept_ref",
                    details={"concept_ref": ref},
                )
            concept_ids.append(concept_lookup[ref])
        return concept_ids

    def _mapped_ids(self, protocol: dict[str, Any], refs: list[str]) -> list[int]:
        lookup = {
            item["concept_ref"]: item["mapping"]["omop_concept_id"]
            for item in protocol.get("concept_sets", [])
            if item.get("mapping", {}).get("status") == "mapped"
        }
        return self._concept_ids_for_refs(lookup, refs)

    @staticmethod
    def _csv(values: list[int]) -> str:
        return ", ".join(str(value) for value in values)

    @staticmethod
    def _num(value: Any) -> str:
        return str(value)

    @staticmethod
    def _escape_literal(value: str) -> str:
        return value.replace("'", "''")
