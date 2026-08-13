-- ==========================================================
-- Populate meta.columns.business_description
-- Hand-authored (not introspectable from the catalog).
-- Safe to rerun.
-- ==========================================================

-- branches
UPDATE meta.columns mc SET business_description = 'Unique identifier for a bank branch.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'branch_id';
UPDATE meta.columns mc SET business_description = 'Display name of the branch, e.g. "Mumbai Fort Branch".'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'branch_name';
UPDATE meta.columns mc SET business_description = 'City the branch is located in.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'city';
UPDATE meta.columns mc SET business_description = 'State/province the branch is located in.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'state';
UPDATE meta.columns mc SET business_description = 'Indian Financial System Code — unique code identifying the branch for electronic fund transfers (NEFT/RTGS/IMPS).'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'ifsc_code';

-- customers
UPDATE meta.columns mc SET business_description = 'Unique identifier for a customer.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'customer_id';
UPDATE meta.columns mc SET business_description = 'Customer''s given name.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'first_name';
UPDATE meta.columns mc SET business_description = 'Customer''s family name.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'last_name';
UPDATE meta.columns mc SET business_description = 'Customer''s email address, used for correspondence.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'email';
UPDATE meta.columns mc SET business_description = 'Customer''s contact phone number.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'phone';
UPDATE meta.columns mc SET business_description = 'Customer''s date of birth, used for age/eligibility checks.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'date_of_birth';
UPDATE meta.columns mc SET business_description = 'Branch the customer is registered at. References branches.branch_id.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'branch_id';

-- loan_officers
UPDATE meta.columns mc SET business_description = 'Unique identifier for a loan officer.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loan_officers' AND mc.column_name = 'officer_id';
UPDATE meta.columns mc SET business_description = 'Full name of the loan officer.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loan_officers' AND mc.column_name = 'officer_name';
UPDATE meta.columns mc SET business_description = 'Loan officer''s work email address.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loan_officers' AND mc.column_name = 'email';
UPDATE meta.columns mc SET business_description = 'Branch the loan officer works at. References branches.branch_id.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loan_officers' AND mc.column_name = 'branch_id';

-- loans
UPDATE meta.columns mc SET business_description = 'Unique identifier for a loan account.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'loan_id';
UPDATE meta.columns mc SET business_description = 'Customer who holds this loan. References customers.customer_id.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'customer_id';
UPDATE meta.columns mc SET business_description = 'Loan officer who originated/manages this loan. References loan_officers.officer_id.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'officer_id';
UPDATE meta.columns mc SET business_description = 'Branch this loan was originated from. References branches.branch_id.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'branch_id';
UPDATE meta.columns mc SET business_description = 'Principal amount sanctioned and disbursed to the customer, in local currency.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'loan_amount';
UPDATE meta.columns mc SET business_description = 'Annual interest rate charged on the outstanding principal, as a percentage.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'interest_rate';
UPDATE meta.columns mc SET business_description = 'Agreed repayment period of the loan, in months.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'tenure_months';
UPDATE meta.columns mc SET business_description = 'Date the loan was disbursed to the customer.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'start_date';
UPDATE meta.columns mc SET business_description = 'Current lifecycle status of the loan: Active, Closed, or Defaulted.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'loan_status';

-- emi_payments
UPDATE meta.columns mc SET business_description = 'Unique identifier for an EMI payment record.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'payment_id';
UPDATE meta.columns mc SET business_description = 'Loan this payment was made against. References loans.loan_id.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'loan_id';
UPDATE meta.columns mc SET business_description = 'Date the EMI payment was due/made.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'payment_date';
UPDATE meta.columns mc SET business_description = 'Amount paid toward this EMI installment.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'amount_paid';
UPDATE meta.columns mc SET business_description = 'Status of this installment: Paid, Overdue, or Missed.'
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'payment_status';
