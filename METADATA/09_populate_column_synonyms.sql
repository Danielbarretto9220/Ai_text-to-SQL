-- ==========================================================
-- Populate meta.columns.business_synonyms
-- Hand-authored (not introspectable from the catalog).
-- Only columns end users are likely to refer to by an alternate
-- name get synonyms; surrogate PK/FK id columns are skipped.
-- Safe to rerun.
-- ==========================================================

-- branches
UPDATE meta.columns mc SET business_synonyms = ARRAY['branch', 'branch office', 'branch title']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'branch_name';
UPDATE meta.columns mc SET business_synonyms = ARRAY['location', 'town']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'city';
UPDATE meta.columns mc SET business_synonyms = ARRAY['province']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'state';
UPDATE meta.columns mc SET business_synonyms = ARRAY['ifsc', 'bank code', 'routing code']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'branches' AND mc.column_name = 'ifsc_code';

-- customers
UPDATE meta.columns mc SET business_synonyms = ARRAY['given name', 'forename']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'first_name';
UPDATE meta.columns mc SET business_synonyms = ARRAY['surname', 'family name']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'last_name';
UPDATE meta.columns mc SET business_synonyms = ARRAY['email address', 'email id']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'email';
UPDATE meta.columns mc SET business_synonyms = ARRAY['phone number', 'mobile', 'contact number']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'phone';
UPDATE meta.columns mc SET business_synonyms = ARRAY['dob', 'birth date', 'birthday']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'customers' AND mc.column_name = 'date_of_birth';

-- loan_officers
UPDATE meta.columns mc SET business_synonyms = ARRAY['loan officer name', 'relationship manager name', 'RM name']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loan_officers' AND mc.column_name = 'officer_name';
UPDATE meta.columns mc SET business_synonyms = ARRAY['email address', 'email id']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loan_officers' AND mc.column_name = 'email';

-- loans
UPDATE meta.columns mc SET business_synonyms = ARRAY['principal', 'principal amount', 'sanctioned amount', 'disbursed amount', 'loan value']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'loan_amount';
UPDATE meta.columns mc SET business_synonyms = ARRAY['rate of interest', 'ROI', 'interest %']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'interest_rate';
UPDATE meta.columns mc SET business_synonyms = ARRAY['loan tenure', 'duration', 'repayment period', 'term']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'tenure_months';
UPDATE meta.columns mc SET business_synonyms = ARRAY['disbursement date', 'sanction date', 'loan start date', 'origination date']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'start_date';
UPDATE meta.columns mc SET business_synonyms = ARRAY['status', 'loan state']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'loans' AND mc.column_name = 'loan_status';

-- emi_payments
UPDATE meta.columns mc SET business_synonyms = ARRAY['emi date', 'installment date']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'payment_date';
UPDATE meta.columns mc SET business_synonyms = ARRAY['emi amount', 'installment amount', 'payment amount']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'amount_paid';
UPDATE meta.columns mc SET business_synonyms = ARRAY['emi status', 'installment status']
FROM meta.tables mt WHERE mt.table_id = mc.table_id AND mt.table_name = 'emi_payments' AND mc.column_name = 'payment_status';
