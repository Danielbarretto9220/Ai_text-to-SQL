"""
app/validation/* — the highest-value, fastest test file: no LLM calls,
everything runs against the real (read-only, for these tests) database.

See docs/API_AND_TESTING_PLAN.md B3.
"""

from app.validation.cost_estimator import check_cost
from app.validation.guardrails import check_business_rules, check_complexity, enforce_limit, run_guardrails
from app.validation.sql_parser import check_hallucinations, check_joins, is_read_only, parse_sql


# ---------------------------------------------------------------------------
# sql_parser.py — 7 scenarios per the test plan
# ---------------------------------------------------------------------------


def test_parse_valid_single_table(db_connection):
    parsed, error = parse_sql("SELECT customer_id, first_name FROM customers")
    assert error is None
    assert is_read_only(parsed)
    assert check_hallucinations(db_connection, parsed) == []


def test_parse_valid_join(db_connection):
    parsed, error = parse_sql(
        "SELECT c.first_name, l.loan_amount FROM customers c JOIN loans l ON c.customer_id = l.customer_id"
    )
    assert error is None
    assert check_hallucinations(db_connection, parsed) == []
    assert check_joins(db_connection, parsed) == []


def test_parse_select_alias_referenced_in_order_by_regression(db_connection):
    # Found live via a Groq-generated query: an ORDER BY referencing a
    # SELECT-list alias (COUNT(...) AS employee_count) was wrongly flagged
    # as an unknown column, since the alias isn't a real column in either
    # referenced table. Postgres resolves ORDER BY aliases against the
    # output list, not the underlying schema.
    parsed, error = parse_sql(
        "SELECT b.branch_name, COUNT(lo.officer_id) AS employee_count "
        "FROM loan_officers lo JOIN branches b ON lo.branch_id = b.branch_id "
        "GROUP BY b.branch_name ORDER BY employee_count DESC"
    )
    assert error is None
    assert check_hallucinations(db_connection, parsed) == []


def test_parse_unknown_table(db_connection):
    parsed, error = parse_sql("SELECT * FROM nonexistent_table")
    assert error is None
    errors = check_hallucinations(db_connection, parsed)
    assert any("Unknown table" in e for e in errors)


def test_parse_unknown_column(db_connection):
    parsed, error = parse_sql("SELECT bogus_column FROM customers")
    assert error is None
    errors = check_hallucinations(db_connection, parsed)
    assert any("Unknown column" in e for e in errors)


def test_parse_unsupported_join(db_connection):
    # customers and loans both FK to branches, but there is no direct
    # customers<->loans relationship on branch_id in meta.relationships.
    parsed, error = parse_sql(
        "SELECT * FROM customers c JOIN loans l ON c.branch_id = l.branch_id"
    )
    assert error is None
    errors = check_joins(db_connection, parsed)
    assert any("Unsupported join" in e for e in errors)


def test_parse_non_read_only_insert():
    parsed, error = parse_sql("INSERT INTO customers (first_name) VALUES ('x')")
    assert error is None
    assert is_read_only(parsed) is False


def test_parse_syntax_error():
    parsed, error = parse_sql("SELEC * FROM customers")
    assert parsed is None
    assert error is not None


# ---------------------------------------------------------------------------
# guardrails.py — LIMIT injection
# ---------------------------------------------------------------------------


def test_limit_injected_on_non_aggregate():
    parsed, _ = parse_sql("SELECT * FROM customers")
    modified, injected = enforce_limit(parsed)
    assert injected is True
    assert modified.args.get("limit") is not None


def test_limit_not_injected_when_already_present():
    parsed, _ = parse_sql("SELECT * FROM customers LIMIT 10")
    modified, injected = enforce_limit(parsed)
    assert injected is False


def test_limit_not_injected_on_pure_aggregate():
    parsed, _ = parse_sql("SELECT COUNT(*) FROM customers")
    modified, injected = enforce_limit(parsed)
    assert injected is False


def test_limit_injected_on_aggregate_with_group_by():
    # GROUP BY means multiple rows come back — not exempt like a pure
    # scalar aggregate.
    parsed, _ = parse_sql("SELECT branch_id, COUNT(*) FROM customers GROUP BY branch_id")
    modified, injected = enforce_limit(parsed)
    assert injected is True


# ---------------------------------------------------------------------------
# guardrails.py — complexity caps
# ---------------------------------------------------------------------------


def test_complexity_flags_too_many_joins():
    parsed, _ = parse_sql(
        "SELECT * FROM customers c JOIN loans l ON c.customer_id = l.customer_id "
        "JOIN emi_payments ep ON l.loan_id = ep.loan_id"
    )
    errors = check_complexity(parsed, max_joins=1)
    assert any("Too many joins" in e for e in errors)


def test_complexity_flags_too_many_subqueries():
    parsed, _ = parse_sql(
        "SELECT * FROM loans WHERE customer_id IN (SELECT customer_id FROM customers WHERE branch_id = 1)"
    )
    errors = check_complexity(parsed, max_subqueries=0)
    assert any("Too many subqueries" in e for e in errors)


def test_complexity_passes_under_default_thresholds():
    parsed, _ = parse_sql("SELECT * FROM customers c JOIN loans l ON c.customer_id = l.customer_id")
    assert check_complexity(parsed) == []


# ---------------------------------------------------------------------------
# guardrails.py — all 8 seeded business rules
# ---------------------------------------------------------------------------


def _violations(connection, sql_text, question_text=""):
    parsed, error = parse_sql(sql_text)
    assert error is None, error
    return check_business_rules(connection, parsed, sql_text, question_text)


def _messages_for(results, rule_name):
    return [r["message"] for r in results if r["rule_name"] == rule_name]


def test_rule_no_sum_principal_with_installments(db_connection):
    results = _violations(
        db_connection,
        "SELECT SUM(l.loan_amount), SUM(ep.amount_paid) FROM loans l "
        "JOIN emi_payments ep ON l.loan_id = ep.loan_id",
    )
    hits = _messages_for(results, "no_sum_principal_with_installments")
    assert hits
    assert all(r["severity"] == "error" for r in results if r["rule_name"] == "no_sum_principal_with_installments")


def test_rule_collected_emi_requires_paid_filter(db_connection):
    results = _violations(db_connection, "SELECT SUM(amount_paid) FROM emi_payments")
    assert _messages_for(results, "collected_emi_requires_paid_filter")


def test_rule_collected_emi_requires_paid_filter_satisfied_by_filter(db_connection):
    results = _violations(
        db_connection, "SELECT SUM(amount_paid) FROM emi_payments WHERE payment_status = 'Paid'"
    )
    assert not _messages_for(results, "collected_emi_requires_paid_filter")


def test_rule_no_sum_interest_rate_unqualified_column_regression(db_connection):
    """Regression test for the bug documented in CLAUDE.md: the column
    resolver originally only handled alias.column references and silently
    missed unqualified single-table queries, which is how the LLM writes
    SQL most of the time. This exact query (no table prefix on
    interest_rate) must still trigger the rule."""

    results = _violations(db_connection, "SELECT SUM(interest_rate) FROM loans")
    assert _messages_for(results, "no_sum_interest_rate")


def test_rule_valid_loan_status_values(db_connection):
    results = _violations(db_connection, "SELECT * FROM loans WHERE loan_status = 'Pending'")
    assert _messages_for(results, "valid_loan_status_values")


def test_rule_valid_loan_status_values_passes_for_allowed_value(db_connection):
    results = _violations(db_connection, "SELECT * FROM loans WHERE loan_status = 'Active'")
    assert not _messages_for(results, "valid_loan_status_values")


def test_rule_valid_payment_status_values(db_connection):
    results = _violations(db_connection, "SELECT * FROM emi_payments WHERE payment_status = 'Late'")
    assert _messages_for(results, "valid_payment_status_values")


def test_rule_active_loans_requires_explicit_status_filter(db_connection):
    results = _violations(db_connection, "SELECT * FROM loans", question_text="Show me all active loans")
    hits = [r for r in results if r["rule_name"] == "active_loans_requires_explicit_status_filter"]
    assert hits
    assert all(r["severity"] == "warning" for r in hits)


def test_rule_customers_loans_join_via_customer_id(db_connection):
    results = _violations(
        db_connection, "SELECT * FROM customers c JOIN loans l ON c.branch_id = l.branch_id"
    )
    assert _messages_for(results, "customers_loans_join_via_customer_id")


def test_rule_customers_loans_join_via_customer_id_passes_for_correct_join(db_connection):
    results = _violations(
        db_connection, "SELECT * FROM customers c JOIN loans l ON c.customer_id = l.customer_id"
    )
    assert not _messages_for(results, "customers_loans_join_via_customer_id")


def test_rule_no_pii_in_aggregate_results(db_connection):
    results = _violations(db_connection, "SELECT email, COUNT(*) FROM customers GROUP BY email")
    hits = [r for r in results if r["rule_name"] == "no_pii_in_aggregate_results"]
    assert hits
    assert all(r["severity"] == "warning" for r in hits)


def test_rule_no_pii_in_aggregate_results_does_not_flag_non_aggregate(db_connection):
    results = _violations(db_connection, "SELECT email FROM customers WHERE customer_id = 1")
    assert not _messages_for(results, "no_pii_in_aggregate_results")


def test_run_guardrails_warnings_do_not_fail_validity(db_connection):
    """Warning-severity hits are advisory — run_guardrails itself doesn't
    decide pass/fail (that's app/pipeline.py's job), but its errors list
    must not include warning-only rule hits."""

    parsed, _ = parse_sql("SELECT email, COUNT(*) FROM customers GROUP BY email")
    result = run_guardrails(db_connection, parsed, "SELECT email, COUNT(*) FROM customers GROUP BY email", "")
    assert any("PII column" in w for w in result["warnings"])
    assert not any("PII column" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# cost_estimator.py
# ---------------------------------------------------------------------------


def test_cost_estimate_passes_under_default_thresholds(db_connection):
    result = check_cost(db_connection, "SELECT * FROM customers")
    assert result["errors"] == []
    assert result["total_cost"] >= 0
    assert result["plan_rows"] >= 0


def test_cost_estimate_flags_low_thresholds(db_connection):
    result = check_cost(db_connection, "SELECT * FROM customers", max_cost=0, max_rows=0)
    assert result["errors"]
