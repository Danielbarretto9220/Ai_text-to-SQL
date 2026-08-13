-- ============================================
-- SAMPLE QUERIES
-- Reference queries against the banking warehouse schema.
-- Useful as manual sanity checks and as few-shot examples
-- for the text-to-SQL retrieval layer.
-- ============================================

-- 1. All active loans with customer and branch names
SELECT
    l.loan_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    b.branch_name,
    l.loan_amount,
    l.interest_rate,
    l.loan_status
FROM loans l
JOIN customers c ON c.customer_id = l.customer_id
JOIN branches b ON b.branch_id = l.branch_id
WHERE l.loan_status = 'Active'
ORDER BY l.loan_amount DESC;

-- 2. Total loan amount disbursed per branch
SELECT
    b.branch_name,
    COUNT(l.loan_id) AS total_loans,
    SUM(l.loan_amount) AS total_disbursed
FROM branches b
LEFT JOIN loans l ON l.branch_id = b.branch_id
GROUP BY b.branch_name
ORDER BY total_disbursed DESC;

-- 3. Loan officers ranked by number of loans managed
SELECT
    lo.officer_name,
    b.branch_name,
    COUNT(l.loan_id) AS loans_managed
FROM loan_officers lo
JOIN branches b ON b.branch_id = lo.branch_id
LEFT JOIN loans l ON l.officer_id = lo.officer_id
GROUP BY lo.officer_name, b.branch_name
ORDER BY loans_managed DESC;

-- 4. Customers with overdue or missed EMI payments
SELECT DISTINCT
    c.first_name || ' ' || c.last_name AS customer_name,
    l.loan_id,
    ep.payment_date,
    ep.payment_status
FROM emi_payments ep
JOIN loans l ON l.loan_id = ep.loan_id
JOIN customers c ON c.customer_id = l.customer_id
WHERE ep.payment_status IN ('Overdue', 'Missed')
ORDER BY ep.payment_date;

-- 5. Defaulted loans with total EMI collected so far
SELECT
    l.loan_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    l.loan_amount,
    COALESCE(SUM(ep.amount_paid) FILTER (WHERE ep.payment_status = 'Paid'), 0) AS total_paid
FROM loans l
JOIN customers c ON c.customer_id = l.customer_id
LEFT JOIN emi_payments ep ON ep.loan_id = l.loan_id
WHERE l.loan_status = 'Defaulted'
GROUP BY l.loan_id, c.first_name, c.last_name, l.loan_amount
ORDER BY total_paid ASC;

-- 6. Average interest rate by loan tenure
SELECT
    tenure_months,
    ROUND(AVG(interest_rate), 2) AS avg_interest_rate,
    COUNT(*) AS num_loans
FROM loans
GROUP BY tenure_months
ORDER BY tenure_months;

-- 7. Customers with more than one loan
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    COUNT(l.loan_id) AS num_loans,
    SUM(l.loan_amount) AS total_borrowed
FROM customers c
JOIN loans l ON l.customer_id = c.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name
HAVING COUNT(l.loan_id) > 1
ORDER BY num_loans DESC;

-- 8. EMI collection summary by month
SELECT
    DATE_TRUNC('month', payment_date)::DATE AS payment_month,
    COUNT(*) AS num_payments,
    SUM(amount_paid) FILTER (WHERE payment_status = 'Paid') AS total_collected
FROM emi_payments
GROUP BY DATE_TRUNC('month', payment_date)
ORDER BY payment_month;
