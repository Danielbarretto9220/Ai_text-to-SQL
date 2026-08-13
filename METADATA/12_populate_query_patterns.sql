-- ==========================================================
-- Populate meta.query_patterns
-- Hand-authored few-shot examples spanning simple lookups through
-- multi-table aggregations, grounded in the actual banking schema.
-- Safe to rerun.
-- ==========================================================

TRUNCATE TABLE meta.query_patterns RESTART IDENTITY;

INSERT INTO meta.query_patterns
(intent_description, example_question, sql_template, tables_used)
VALUES
(
    'List all rows of a single table with no filtering.',
    'List all branches.',
    'SELECT * FROM branches;',
    ARRAY['branches']
),
(
    'Filter a table by a status/category column.',
    'Show all active loans.',
    'SELECT * FROM loans WHERE loan_status = ''Active'';',
    ARRAY['loans']
),
(
    'Count all rows in a table.',
    'How many customers do we have?',
    'SELECT COUNT(*) FROM customers;',
    ARRAY['customers']
),
(
    'Simple join to attach a related entity''s name.',
    'List customer names along with their branch name.',
    'SELECT c.first_name || '' '' || c.last_name AS customer_name, b.branch_name
FROM customers c
JOIN branches b ON b.branch_id = c.branch_id;',
    ARRAY['customers', 'branches']
),
(
    'Aggregate a numeric column grouped by a related dimension.',
    'What is the total loan amount disbursed per branch?',
    'SELECT b.branch_name, COUNT(l.loan_id) AS total_loans, SUM(l.loan_amount) AS total_disbursed
FROM branches b
LEFT JOIN loans l ON l.branch_id = b.branch_id
GROUP BY b.branch_name
ORDER BY total_disbursed DESC;',
    ARRAY['branches', 'loans']
),
(
    'Rank an entity by a related count, across a join.',
    'Which loan officers manage the most loans?',
    'SELECT lo.officer_name, b.branch_name, COUNT(l.loan_id) AS loans_managed
FROM loan_officers lo
JOIN branches b ON b.branch_id = lo.branch_id
LEFT JOIN loans l ON l.officer_id = lo.officer_id
GROUP BY lo.officer_name, b.branch_name
ORDER BY loans_managed DESC;',
    ARRAY['loan_officers', 'branches', 'loans']
),
(
    'Filter on a status value in a child table, joined back to the parent entities.',
    'Show customers with overdue or missed EMI payments.',
    'SELECT DISTINCT c.first_name || '' '' || c.last_name AS customer_name, l.loan_id, ep.payment_date, ep.payment_status
FROM emi_payments ep
JOIN loans l ON l.loan_id = ep.loan_id
JOIN customers c ON c.customer_id = l.customer_id
WHERE ep.payment_status IN (''Overdue'', ''Missed'')
ORDER BY ep.payment_date;',
    ARRAY['emi_payments', 'loans', 'customers']
),
(
    'Conditional aggregate (FILTER) alongside a status filter on the parent row.',
    'For defaulted loans, how much EMI has been collected so far?',
    'SELECT l.loan_id, c.first_name || '' '' || c.last_name AS customer_name, l.loan_amount,
       COALESCE(SUM(ep.amount_paid) FILTER (WHERE ep.payment_status = ''Paid''), 0) AS total_paid
FROM loans l
JOIN customers c ON c.customer_id = l.customer_id
LEFT JOIN emi_payments ep ON ep.loan_id = l.loan_id
WHERE l.loan_status = ''Defaulted''
GROUP BY l.loan_id, c.first_name, c.last_name, l.loan_amount
ORDER BY total_paid ASC;',
    ARRAY['loans', 'customers', 'emi_payments']
),
(
    'Average of a numeric column grouped by another numeric/categorical column.',
    'What is the average interest rate for each loan tenure?',
    'SELECT tenure_months, ROUND(AVG(interest_rate), 2) AS avg_interest_rate, COUNT(*) AS num_loans
FROM loans
GROUP BY tenure_months
ORDER BY tenure_months;',
    ARRAY['loans']
),
(
    'Group by with a HAVING filter to find entities exceeding a count threshold.',
    'Which customers have more than one loan?',
    'SELECT c.customer_id, c.first_name || '' '' || c.last_name AS customer_name,
       COUNT(l.loan_id) AS num_loans, SUM(l.loan_amount) AS total_borrowed
FROM customers c
JOIN loans l ON l.customer_id = c.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name
HAVING COUNT(l.loan_id) > 1
ORDER BY num_loans DESC;',
    ARRAY['customers', 'loans']
),
(
    'Time-series aggregation bucketed by month.',
    'Show EMI collections by month.',
    'SELECT DATE_TRUNC(''month'', payment_date)::DATE AS payment_month,
       COUNT(*) AS num_payments,
       SUM(amount_paid) FILTER (WHERE payment_status = ''Paid'') AS total_collected
FROM emi_payments
GROUP BY DATE_TRUNC(''month'', payment_date)
ORDER BY payment_month;',
    ARRAY['emi_payments']
),
(
    'Top-N ranking of an entity by an aggregated numeric value.',
    'Who are the top 5 customers by total loan amount?',
    'SELECT c.customer_id, c.first_name || '' '' || c.last_name AS customer_name, SUM(l.loan_amount) AS total_loan_amount
FROM customers c
JOIN loans l ON l.customer_id = c.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name
ORDER BY total_loan_amount DESC
LIMIT 5;',
    ARRAY['customers', 'loans']
),
(
    'Filter rows by a date range.',
    'List loans disbursed in 2024.',
    'SELECT * FROM loans WHERE start_date BETWEEN ''2024-01-01'' AND ''2024-12-31'';',
    ARRAY['loans']
),
(
    'Business-term-driven filter (defaulted/NPA loans) joined to contact details.',
    'Show all defaulted loans with the customer''s contact information.',
    'SELECT l.loan_id, c.first_name || '' '' || c.last_name AS customer_name, c.phone, c.email, l.loan_amount
FROM loans l
JOIN customers c ON c.customer_id = l.customer_id
WHERE l.loan_status = ''Defaulted'';',
    ARRAY['loans', 'customers']
),
(
    'Three-table join aggregating a payment amount up to a top-level dimension.',
    'How much EMI has been collected at each branch?',
    'SELECT b.branch_name, SUM(ep.amount_paid) AS total_collected
FROM branches b
JOIN loans l ON l.branch_id = b.branch_id
JOIN emi_payments ep ON ep.loan_id = l.loan_id
WHERE ep.payment_status = ''Paid''
GROUP BY b.branch_name
ORDER BY total_collected DESC;',
    ARRAY['branches', 'loans', 'emi_payments']
);
