-- ============================================
-- INSERT BRANCHES (6)
-- ============================================

INSERT INTO branches
(branch_name, city, state, ifsc_code)
VALUES
('Mumbai Fort Branch','Mumbai','Maharashtra','UNBK0001001'),
('Delhi Connaught Place Branch','Delhi','Delhi','UNBK0001002'),
('Bengaluru MG Road Branch','Bengaluru','Karnataka','UNBK0001003'),
('Chennai T Nagar Branch','Chennai','Tamil Nadu','UNBK0001004'),
('Pune Camp Branch','Pune','Maharashtra','UNBK0001005'),

('Hyderabad Banjara Hills Branch','Hyderabad','Telangana','UNBK0001006');

-- ============================================
-- INSERT CUSTOMERS (40)
-- ============================================

INSERT INTO customers
(first_name, last_name, email, phone, date_of_birth, branch_id)
VALUES
('Aarav','Sharma','aarav.sharma1@example.com','9786579303','1972-01-24',1),
('Vivaan','Verma','vivaan.verma2@example.com','9395310485','1980-04-05',2),
('Aditya','Gupta','aditya.gupta3@example.com','9890779946','1971-11-24',3),
('Vihaan','Patel','vihaan.patel4@example.com','9685582861','1970-10-14',4),
('Arjun','Reddy','arjun.reddy5@example.com','9134126396','1966-02-07',5),

('Sai','Iyer','sai.iyer6@example.com','9349817734','1997-10-01',6),
('Reyansh','Nair','reyansh.nair7@example.com','9702632297','1977-12-21',1),
('Krishna','Menon','krishna.menon8@example.com','9853041955','1999-07-08',2),
('Ishaan','Rao','ishaan.rao9@example.com','9582334538','2002-05-26',3),
('Rohan','Kulkarni','rohan.kulkarni10@example.com','9106977991','1975-12-14',4),

('Ananya','Joshi','ananya.joshi11@example.com','9465341213','1982-03-07',5),
('Diya','Mehta','diya.mehta12@example.com','9919795579','1986-02-03',6),
('Isha','Chopra','isha.chopra13@example.com','9507943839','1971-06-28',1),
('Kavya','Malhotra','kavya.malhotra14@example.com','9469319644','1981-01-24',2),
('Meera','Bose','meera.bose15@example.com','9593303705','1999-02-13',3),

('Priya','Banerjee','priya.banerjee16@example.com','9184611066','2000-05-27',4),
('Riya','Pillai','riya.pillai17@example.com','9774996843','1988-10-07',5),
('Saanvi','Naidu','saanvi.naidu18@example.com','9856528252','1969-01-22',6),
('Tanvi','Desai','tanvi.desai19@example.com','9344703907','1983-02-28',1),
('Zoya','Kapoor','zoya.kapoor20@example.com','9349957310','1971-07-09',2),

('Rahul','Sharma','rahul.sharma21@example.com','9586845604','1988-03-12',3),
('Karan','Verma','karan.verma22@example.com','9481469012','1978-11-09',4),
('Nikhil','Gupta','nikhil.gupta23@example.com','9853573823','1969-10-21',5),
('Varun','Patel','varun.patel24@example.com','9283758720','1999-12-08',6),
('Siddharth','Reddy','siddharth.reddy25@example.com','9275452091','1994-07-09',1),

('Aditi','Iyer','aditi.iyer26@example.com','9787194506','2000-04-22',2),
('Neha','Nair','neha.nair27@example.com','9448195935','1968-04-27',3),
('Pooja','Menon','pooja.menon28@example.com','9134467368','1985-07-09',4),
('Sneha','Rao','sneha.rao29@example.com','9171069472','1978-10-23',5),
('Divya','Kulkarni','divya.kulkarni30@example.com','9437882805','1978-11-16',6),

('Amit','Joshi','amit.joshi31@example.com','9524806516','1994-03-09',1),
('Suresh','Mehta','suresh.mehta32@example.com','9249926919','1980-12-18',2),
('Ramesh','Chopra','ramesh.chopra33@example.com','9678722458','1981-12-19',3),
('Manoj','Malhotra','manoj.malhotra34@example.com','9560027313','2002-07-12',4),
('Deepak','Bose','deepak.bose35@example.com','9335493870','1973-09-16',5),

('Anjali','Banerjee','anjali.banerjee36@example.com','9197613238','1968-02-05',6),
('Kiran','Pillai','kiran.pillai37@example.com','9773715057','1975-11-14',1),
('Lakshmi','Naidu','lakshmi.naidu38@example.com','9740389325','1969-07-13',2),
('Radha','Desai','radha.desai39@example.com','9739830322','1994-09-09',3),
('Sunita','Kapoor','sunita.kapoor40@example.com','9694021782','1965-11-24',4);
