-- ==========================================================
-- Banking warehouse schema
-- Tables: branches, customers, loan_officers, loans, emi_payments
-- ==========================================================

CREATE TABLE branches (
    branch_id     SERIAL PRIMARY KEY,
    branch_name   TEXT NOT NULL,
    city          TEXT,
    state         TEXT,
    ifsc_code     TEXT
);

CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
    date_of_birth DATE,
    branch_id     INT REFERENCES branches(branch_id)
);

CREATE TABLE loan_officers (
    officer_id    SERIAL PRIMARY KEY,
    officer_name  TEXT NOT NULL,
    email         TEXT,
    branch_id     INT REFERENCES branches(branch_id)
);

CREATE TABLE loans (
    loan_id       SERIAL PRIMARY KEY,
    customer_id   INT REFERENCES customers(customer_id),
    officer_id    INT REFERENCES loan_officers(officer_id),
    branch_id     INT REFERENCES branches(branch_id),
    loan_amount   NUMERIC(12, 2) NOT NULL,
    interest_rate NUMERIC(5, 2),
    tenure_months INT,
    start_date    DATE,
    loan_status   TEXT
);

CREATE TABLE emi_payments (
    payment_id     SERIAL PRIMARY KEY,
    loan_id        INT REFERENCES loans(loan_id),
    payment_date   DATE,
    amount_paid    NUMERIC(12, 2),
    payment_status TEXT
);
