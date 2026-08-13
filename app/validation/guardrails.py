"""
Read-only enforcement, LIMIT injection, query-complexity limits, and
business-rule checks (meta.business_rules) on parsed SQL.

meta.business_rules' rule_logic JSONB is genuinely heterogeneous across
rule_type values (and even inconsistent within forbidden_aggregation —
two seeded rows use different key names), so each rule_type gets its own
checker function, dispatched defensively: an unknown rule_type is
skipped, and any exception evaluating one rule's rule_logic is caught
and reported as a skipped-rule warning rather than crashing the whole
check.

See enterprise-text-to-sql-architecture.md §5.
"""

from sqlglot import exp

from app.db.metadata_loader import get_connection, load_business_rules
from app.validation.sql_parser import parse_sql


def _build_alias_map(parsed):
    """Alias/real-name -> real table name. Also maps the empty-string
    qualifier ("") to the sole table when the query references exactly
    one, so unqualified column references (very common in real LLM
    output, e.g. single-table queries with no table prefix) still
    resolve instead of silently failing to match any rule."""

    alias_to_table = {}
    distinct_tables = set()

    for table_node in parsed.find_all(exp.Table):
        table_name = table_node.name.lower()
        distinct_tables.add(table_name)
        alias_to_table[table_name] = table_name
        alias_to_table[table_node.alias_or_name.lower()] = table_name

    if len(distinct_tables) == 1:
        alias_to_table[""] = next(iter(distinct_tables))

    return alias_to_table


def _real_column_ref(column_node, alias_to_table):
    """'table.column' (lowercase) if resolvable via alias_to_table
    (including the unqualified/single-table case), else None."""

    qualifier = column_node.table.lower() if column_node.table else ""
    real_table = alias_to_table.get(qualifier)
    if not real_table:
        return None
    return f"{real_table}.{column_node.name.lower()}"


def _literal_value(expression):
    return expression.this if isinstance(expression, exp.Literal) else None


def _has_filter(parsed, require_filter, alias_to_table):
    """Whether the WHERE clause has an equality comparison matching
    require_filter = {"column": "table.col", "operator": "=", "value": X}."""

    if not require_filter:
        return True

    where = parsed.args.get("where")
    if where is None:
        return False

    target_column = str(require_filter.get("column", "")).lower()
    target_value = str(require_filter.get("value", "")).lower()

    for eq in where.find_all(exp.EQ):
        left, right = eq.this, eq.expression
        if not isinstance(left, exp.Column):
            continue
        if _real_column_ref(left, alias_to_table) != target_column:
            continue
        value = _literal_value(right)
        if value is not None and str(value).lower() == target_value:
            return True

    return False


def _aggregate_calls(parsed, alias_to_table):
    """List of (FUNC_NAME_UPPER, 'table.column') for every aggregate
    function call whose argument is a resolvable column reference."""

    calls = []
    for agg in parsed.find_all(exp.AggFunc):
        if isinstance(agg.this, exp.Column):
            ref = _real_column_ref(agg.this, alias_to_table)
            if ref:
                calls.append((type(agg).__name__.upper(), ref))
    return calls


def _check_forbidden_aggregation(rule_logic, parsed, alias_to_table, question_text):
    violations = []
    agg_calls = _aggregate_calls(parsed, alias_to_table)

    forbidden_pair = rule_logic.get("forbidden_pair")
    if forbidden_pair:
        pair_lower = {c.lower() for c in forbidden_pair}
        pair_functions = {f.upper() for f in rule_logic.get("aggregate_functions", [])}
        matched = {ref for func, ref in agg_calls if func in pair_functions and ref in pair_lower}
        if pair_lower <= matched:
            violations.append(rule_logic.get("reason", f"Forbidden aggregation combination: {forbidden_pair}"))

    single_column = rule_logic.get("column")
    if single_column:
        column_lower = single_column.lower()
        forbidden_functions = {f.upper() for f in rule_logic.get("forbidden_aggregate_functions", [])}
        for func, ref in agg_calls:
            if ref == column_lower and func in forbidden_functions:
                violations.append(rule_logic.get("reason", f"Forbidden aggregate {func} on {single_column}"))
                break

    return violations


def _check_required_filter(rule_logic, parsed, alias_to_table, question_text):
    violations = []
    require_filter = rule_logic.get("require_filter", {})

    trigger_column = rule_logic.get("trigger_column")
    trigger_aggregate = rule_logic.get("trigger_aggregate")
    if trigger_column and trigger_aggregate:
        triggered = any(
            func == trigger_aggregate.upper() and ref == trigger_column.lower()
            for func, ref in _aggregate_calls(parsed, alias_to_table)
        )
        if triggered and not _has_filter(parsed, require_filter, alias_to_table):
            violations.append(rule_logic.get("reason", f"Missing required filter: {require_filter}"))

    intent_keywords = rule_logic.get("intent_keywords")
    if intent_keywords and question_text:
        question_lower = question_text.lower()
        if any(keyword.lower() in question_lower for keyword in intent_keywords):
            if not _has_filter(parsed, require_filter, alias_to_table):
                violations.append(
                    f"Question implies {intent_keywords} but query is missing filter: {require_filter}"
                )

    return violations


def _check_value_constraint(rule_logic, parsed, alias_to_table, question_text):
    violations = []
    column = str(rule_logic.get("column", "")).lower()
    allowed_values = {str(v).lower() for v in rule_logic.get("allowed_values", [])}

    where = parsed.args.get("where")
    if not where or not column:
        return violations

    for eq in where.find_all(exp.EQ):
        left, right = eq.this, eq.expression
        if not isinstance(left, exp.Column) or _real_column_ref(left, alias_to_table) != column:
            continue
        value = _literal_value(right)
        if value is not None and str(value).lower() not in allowed_values:
            violations.append(f"Value {value!r} not in allowed values for {column}: {sorted(allowed_values)}")

    return violations


def _check_join_constraint(rule_logic, parsed, alias_to_table, question_text):
    violations = []
    tables = {t.lower() for t in rule_logic.get("tables", [])}
    forbidden_column = str(rule_logic.get("forbidden_join_column", "")).lower()

    for join_node in parsed.find_all(exp.Join):
        on_condition = join_node.args.get("on")
        if on_condition is None:
            continue
        for eq in on_condition.find_all(exp.EQ):
            left, right = eq.this, eq.expression
            if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
                continue
            left_table = alias_to_table.get(left.table.lower()) if left.table else None
            right_table = alias_to_table.get(right.table.lower()) if right.table else None
            if (
                left_table in tables
                and right_table in tables
                and left.name.lower() == forbidden_column
                and right.name.lower() == forbidden_column
            ):
                violations.append(
                    rule_logic.get("reason", f"Forbidden join column {forbidden_column!r} used between {tables}")
                )

    return violations


def _check_pii_exposure(rule_logic, parsed, alias_to_table, question_text):
    violations = []
    pii_columns = {c.lower() for c in rule_logic.get("columns", [])}
    is_aggregate_query = bool(parsed.args.get("group")) or any(parsed.find_all(exp.AggFunc))

    if is_aggregate_query:
        flagged = set()
        for column_node in parsed.find_all(exp.Column):
            ref = _real_column_ref(column_node, alias_to_table)
            if ref in pii_columns and ref not in flagged:
                flagged.add(ref)
                action = rule_logic.get("action", "review needed")
                violations.append(f"PII column {ref} referenced in an aggregate/summary query - {action}")

    return violations


RULE_TYPE_CHECKERS = {
    "forbidden_aggregation": _check_forbidden_aggregation,
    "required_filter": _check_required_filter,
    "value_constraint": _check_value_constraint,
    "join_constraint": _check_join_constraint,
    "pii_exposure": _check_pii_exposure,
}


def check_business_rules(connection, parsed, sql_text, question_text):
    """Dispatches every active meta.business_rules row to its rule_type
    checker. Returns a list of {rule_name, severity, message}. An
    unrecognized rule_type is skipped; an exception evaluating one rule
    is caught and reported as a skipped-rule warning rather than
    crashing the whole check."""

    alias_to_table = _build_alias_map(parsed)
    results = []

    for row in load_business_rules(connection):
        (
            rule_id,
            rule_name,
            description,
            rule_type,
            applies_to_tables,
            applies_to_columns,
            rule_logic,
            severity,
            is_active,
        ) = row

        checker = RULE_TYPE_CHECKERS.get(rule_type)
        if checker is None:
            continue

        try:
            violations = checker(rule_logic, parsed, alias_to_table, question_text)
        except Exception as exc:
            results.append(
                {"rule_name": rule_name, "severity": "warning", "message": f"Rule check failed to evaluate ({exc}); skipped."}
            )
            continue

        for violation in violations:
            results.append({"rule_name": rule_name, "severity": severity, "message": violation})

    return results


def _is_pure_aggregate(parsed):
    """No GROUP BY and every top-level SELECT expression is an aggregate
    function call — matches the seeded system prompt's rule 4 exemption
    from the default LIMIT."""

    if parsed.args.get("group"):
        return False

    expressions = parsed.expressions
    if not expressions:
        return False

    for expression in expressions:
        target = expression.this if isinstance(expression, exp.Alias) else expression
        if not isinstance(target, exp.AggFunc):
            return False

    return True


def enforce_limit(parsed, default_limit=100):
    """Injects LIMIT default_limit if absent and the query isn't a pure
    aggregate (system prompt rule 4). Returns (parsed, was_injected)."""

    if parsed.args.get("limit") is not None:
        return parsed, False

    if _is_pure_aggregate(parsed):
        return parsed, False

    return parsed.limit(default_limit), True


def check_complexity(parsed, max_joins=4, max_subqueries=2):
    """Rejects queries beyond join/subquery thresholds sized for this
    project's 5-table schema."""

    errors = []

    join_count = len(list(parsed.find_all(exp.Join)))
    if join_count > max_joins:
        errors.append(f"Too many joins: {join_count} > {max_joins}")

    subquery_count = len(list(parsed.find_all(exp.Subquery)))
    if subquery_count > max_subqueries:
        errors.append(f"Too many subqueries: {subquery_count} > {max_subqueries}")

    return errors


def run_guardrails(connection, parsed, sql_text, question_text):
    """Combines LIMIT injection, complexity checks, and business rules
    into one result. warning-severity rule hits never fail the query;
    error-severity ones do, as does exceeding a complexity threshold."""

    modified_parsed, limit_injected = enforce_limit(parsed)

    complexity_errors = check_complexity(modified_parsed)
    rule_results = check_business_rules(connection, modified_parsed, sql_text, question_text)

    errors = list(complexity_errors) + [r["message"] for r in rule_results if r["severity"] == "error"]
    warnings = [r["message"] for r in rule_results if r["severity"] == "warning"]

    return {
        "parsed": modified_parsed,
        "final_sql": modified_parsed.sql(dialect="postgres"),
        "limit_injected": limit_injected,
        "errors": errors,
        "warnings": warnings,
        "rule_results": rule_results,
    }


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        sql_text = input("Enter SQL: ").strip()
        question_text = input("Enter the original question (or leave blank): ").strip()

        parsed, error = parse_sql(sql_text)
        if error:
            print(f"\nSyntax error: {error}")
            return

        result = run_guardrails(connection, parsed, sql_text, question_text)

        print(f"\nFinal SQL: {result['final_sql']}")
        print(f"LIMIT injected: {result['limit_injected']}")
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result["errors"]:
            print(f"  - {err}")
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warn in result["warnings"]:
            print(f"  - {warn}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
