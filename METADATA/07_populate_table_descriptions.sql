-- ==========================================================
-- Populate meta.tables.business_description
-- Hand-authored (not introspectable from the catalog).
-- Safe to rerun.
-- ==========================================================

UPDATE meta.tables SET business_description =
    'Physical bank branch locations. Customers and loan officers are registered to a branch, and loans are originated from one. Each branch has a unique IFSC code used for electronic fund transfers.'
WHERE table_name = 'branches';

UPDATE meta.tables SET business_description =
    'Individuals who hold one or more loan accounts with the bank. Stores personal and contact details and the home branch each customer is registered at.'
WHERE table_name = 'customers';

UPDATE meta.tables SET business_description =
    'Bank staff who originate, underwrite, and manage customer loans. Each officer is attached to a single branch and may manage multiple loans.'
WHERE table_name = 'loan_officers';

UPDATE meta.tables SET business_description =
    'Loan accounts issued to customers. Captures the principal amount, interest rate, repayment tenure, disbursement date, and current lifecycle status (Active, Closed, Defaulted) of each loan.'
WHERE table_name = 'loans';

UPDATE meta.tables SET business_description =
    'Individual EMI (Equated Monthly Installment) payment records made by customers against their loans. Tracks the payment date, amount paid, and the status of each installment (Paid, Overdue, Missed).'
WHERE table_name = 'emi_payments';
