-- ==========================================================
-- Populate meta.business_glossary
-- Curated banking domain terms for the loans warehouse schema
-- (branches, customers, loan_officers, loans, emi_payments).
-- Not introspectable from the catalog — hand-authored.
-- Safe to rerun.
-- ==========================================================

TRUNCATE TABLE meta.business_glossary RESTART IDENTITY;

INSERT INTO meta.business_glossary
(
    term,
    definition,
    maps_to_tables,
    maps_to_columns,
    synonyms
)
VALUES
(
    'EMI',
    'Equated Monthly Installment — the fixed periodic payment a customer makes toward repaying a loan, covering both principal and interest.',
    ARRAY['emi_payments'],
    ARRAY['emi_payments.amount_paid', 'emi_payments.payment_date'],
    ARRAY['installment', 'monthly installment', 'monthly payment']
),
(
    'Loan Officer',
    'The bank employee responsible for originating, underwriting, or managing a customer''s loan.',
    ARRAY['loan_officers'],
    ARRAY['loan_officers.officer_name', 'loans.officer_id'],
    ARRAY['relationship manager', 'RM', 'account officer', 'loan manager']
),
(
    'Branch',
    'A physical bank location that customers are registered to and where loans are originated.',
    ARRAY['branches'],
    ARRAY['branches.branch_name', 'branches.city', 'branches.state'],
    ARRAY['bank branch', 'branch office']
),
(
    'IFSC Code',
    'Indian Financial System Code — the unique alphanumeric code identifying a specific bank branch for electronic fund transfers.',
    ARRAY['branches'],
    ARRAY['branches.ifsc_code'],
    ARRAY['bank code', 'branch code', 'routing code']
),
(
    'Loan Status',
    'The current lifecycle state of a loan (e.g. active, closed, defaulted).',
    ARRAY['loans'],
    ARRAY['loans.loan_status'],
    ARRAY['loan state', 'application status']
),
(
    'Interest Rate',
    'The annual percentage rate charged on the outstanding loan principal.',
    ARRAY['loans'],
    ARRAY['loans.interest_rate'],
    ARRAY['rate of interest', 'ROI']
),
(
    'Tenure',
    'The agreed repayment period of a loan, expressed in months.',
    ARRAY['loans'],
    ARRAY['loans.tenure_months'],
    ARRAY['loan term', 'duration', 'repayment period']
),
(
    'Loan Amount',
    'The principal sum sanctioned and disbursed to the customer at loan origination.',
    ARRAY['loans'],
    ARRAY['loans.loan_amount'],
    ARRAY['principal', 'principal amount', 'sanctioned amount', 'disbursed amount']
),
(
    'Customer',
    'An individual who holds one or more loans with the bank.',
    ARRAY['customers'],
    ARRAY['customers.first_name', 'customers.last_name', 'customers.email', 'customers.phone'],
    ARRAY['borrower', 'account holder', 'client']
),
(
    'Payment Status',
    'The state of an individual EMI payment (e.g. paid, pending, overdue).',
    ARRAY['emi_payments'],
    ARRAY['emi_payments.payment_status'],
    ARRAY['payment state', 'installment status']
),
(
    'Disbursement Date',
    'The date a loan was sanctioned and its first funds released to the customer.',
    ARRAY['loans'],
    ARRAY['loans.start_date'],
    ARRAY['loan start date', 'sanction date', 'origination date']
),
(
    'NPA',
    'Non-Performing Asset — a loan on which the customer has fallen sufficiently behind on EMI payments that it is treated as in default.',
    ARRAY['loans', 'emi_payments'],
    ARRAY['loans.loan_status', 'emi_payments.payment_status'],
    ARRAY['non-performing asset', 'defaulted loan', 'bad loan']
);
