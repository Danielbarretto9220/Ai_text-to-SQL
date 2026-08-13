-- ==========================================================
-- Populate meta.business_rules
-- Hand-authored, grounded in this schema's actual data quirks (not
-- generic examples) — e.g. rule 2 below exists because
-- emi_payments.amount_paid is populated even on Missed/Overdue rows
-- (verified against the loaded dummy data), so summing it without a
-- status filter silently overstates real collections.
-- Safe to rerun.
-- ==========================================================

INSERT INTO meta.business_rules
(rule_name, description, rule_type, applies_to_tables, applies_to_columns, rule_logic, severity)
VALUES
(
    'no_sum_principal_with_installments',
    'loan_amount (principal disbursed) and amount_paid (a single EMI installment) must not be summed together in the same aggregate expression — they are different units of measure and combining them produces a meaningless total.',
    'forbidden_aggregation',
    ARRAY['loans', 'emi_payments'],
    ARRAY['loans.loan_amount', 'emi_payments.amount_paid'],
    '{"forbidden_pair": ["loans.loan_amount", "emi_payments.amount_paid"], "aggregate_functions": ["SUM"], "reason": "principal disbursed vs. a single installment amount are not the same unit of measure"}'::jsonb,
    'error'
),
(
    'collected_emi_requires_paid_filter',
    'Any aggregate over emi_payments.amount_paid intended to represent money actually collected must filter payment_status = ''Paid''. amount_paid holds the due amount even on Missed/Overdue rows, so an unfiltered SUM overstates real collections.',
    'required_filter',
    ARRAY['emi_payments'],
    ARRAY['emi_payments.amount_paid', 'emi_payments.payment_status'],
    '{"trigger_column": "emi_payments.amount_paid", "trigger_aggregate": "SUM", "require_filter": {"column": "emi_payments.payment_status", "operator": "=", "value": "Paid"}, "reason": "amount_paid is populated regardless of payment_status; only Paid rows reflect money actually received"}'::jsonb,
    'error'
),
(
    'no_sum_interest_rate',
    'loans.interest_rate is a percentage; it must not be aggregated with SUM. Use AVG (or MIN/MAX) when aggregating interest rates across multiple loans.',
    'forbidden_aggregation',
    ARRAY['loans'],
    ARRAY['loans.interest_rate'],
    '{"column": "loans.interest_rate", "forbidden_aggregate_functions": ["SUM"], "allowed_aggregate_functions": ["AVG", "MIN", "MAX"], "reason": "summing a percentage rate across rows is not a meaningful quantity"}'::jsonb,
    'error'
),
(
    'valid_loan_status_values',
    'loans.loan_status must be filtered/compared only against its known values: Active, Closed, Defaulted. A generated query using any other literal likely hallucinated a status that does not exist in this data.',
    'value_constraint',
    ARRAY['loans'],
    ARRAY['loans.loan_status'],
    '{"column": "loans.loan_status", "allowed_values": ["Active", "Closed", "Defaulted"]}'::jsonb,
    'error'
),
(
    'valid_payment_status_values',
    'emi_payments.payment_status must be filtered/compared only against its known values: Paid, Overdue, Missed.',
    'value_constraint',
    ARRAY['emi_payments'],
    ARRAY['emi_payments.payment_status'],
    '{"column": "emi_payments.payment_status", "allowed_values": ["Paid", "Overdue", "Missed"]}'::jsonb,
    'error'
),
(
    'active_loans_requires_explicit_status_filter',
    'Questions about "active" or "current" loans must add an explicit loan_status = ''Active'' filter, not rely on the absence of a status filter — an unfiltered query silently includes Closed and Defaulted loans too.',
    'required_filter',
    ARRAY['loans'],
    ARRAY['loans.loan_status'],
    '{"intent_keywords": ["active loans", "current loans", "ongoing loans"], "require_filter": {"column": "loans.loan_status", "operator": "=", "value": "Active"}}'::jsonb,
    'warning'
),
(
    'customers_loans_join_via_customer_id',
    'customers must be joined to loans via customers.customer_id = loans.customer_id, never via branch_id alone — a branch_id-only join fans out to every customer x every loan sharing that branch, producing a cartesian-like row explosion.',
    'join_constraint',
    ARRAY['customers', 'loans'],
    ARRAY['customers.customer_id', 'loans.customer_id', 'customers.branch_id', 'loans.branch_id'],
    '{"tables": ["customers", "loans"], "forbidden_join_column": "branch_id", "required_join": {"left": "customers.customer_id", "right": "loans.customer_id"}, "reason": "branch_id alone is not selective enough to relate a specific customer to a specific loan"}'::jsonb,
    'error'
),
(
    'no_pii_in_aggregate_results',
    'customers.email and customers.phone are PII and must not be included in aggregate/summary result sets (GROUP BY, COUNT, SUM, etc.) unless the user explicitly asks for contact information.',
    'pii_exposure',
    ARRAY['customers'],
    ARRAY['customers.email', 'customers.phone'],
    '{"columns": ["customers.email", "customers.phone"], "condition": "aggregate_or_summary_query", "action": "exclude_unless_explicitly_requested"}'::jsonb,
    'warning'
)
ON CONFLICT (rule_name) DO UPDATE SET
    description = EXCLUDED.description,
    rule_type = EXCLUDED.rule_type,
    applies_to_tables = EXCLUDED.applies_to_tables,
    applies_to_columns = EXCLUDED.applies_to_columns,
    rule_logic = EXCLUDED.rule_logic,
    severity = EXCLUDED.severity;
