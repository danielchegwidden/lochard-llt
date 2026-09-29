-- ABAC policies on lochard_gold. Every policy EXCEPTs the ETL identity so pipelines always read full data.
CREATE OR REPLACE POLICY lochard_mask_person ON SCHEMA {gold}
COMMENT 'Mask person names / usernames outside HSE'
COLUMN MASK {governance}.mask_person
TO `account users` EXCEPT `{etl_sp}`
FOR TABLES
MATCH COLUMNS has_tag_value('lochard_pii', 'person_name') AS c ON COLUMN c;

CREATE OR REPLACE POLICY lochard_mask_email ON SCHEMA {gold}
COMMENT 'Mask email addresses outside HSE'
COLUMN MASK {governance}.mask_person
TO `account users` EXCEPT `{etl_sp}`
FOR TABLES
MATCH COLUMNS has_tag_value('lochard_pii', 'email') AS c ON COLUMN c;

CREATE OR REPLACE POLICY lochard_mask_bank ON SCHEMA {gold}
COMMENT 'Vendor bank details and ABN visible to Finance only'
COLUMN MASK {governance}.mask_bank
TO `account users` EXCEPT `{etl_sp}`
FOR TABLES
MATCH COLUMNS has_tag_value('lochard_pii', 'bank_details') OR has_tag_value('lochard_pii', 'business_id') AS c ON COLUMN c;

CREATE OR REPLACE POLICY lochard_mask_gl_text ON SCHEMA {gold}
COMMENT 'Legal / Employee Costs GL and PO descriptions restricted to Finance and Leadership'
COLUMN MASK {governance}.mask_gl_text
TO `account users` EXCEPT `{etl_sp}`
FOR TABLES
WHEN has_tag_value('lochard_domain', 'finance')
MATCH COLUMNS has_tag_value('lochard_pii', 'free_text') AS txt, has_tag_value('lochard_rls', 'account_class') AS ac
ON COLUMN txt USING COLUMNS (ac);

CREATE OR REPLACE POLICY lochard_rf_finance_team ON SCHEMA {gold}
COMMENT 'Budget holders see only their own team; Finance / LLT / Board see all'
ROW FILTER {governance}.rf_team
TO `account users` EXCEPT `{etl_sp}`
FOR TABLES
WHEN has_tag_value('lochard_domain', 'finance')
MATCH COLUMNS has_tag_value('lochard_rls', 'team') AS t USING COLUMNS (t);

CREATE OR REPLACE POLICY lochard_rf_hse_privilege ON SCHEMA {gold}
COMMENT 'Legally privileged HSE investigation rows only for HSE investigators'
ROW FILTER {governance}.rf_hse_privilege
TO `account users` EXCEPT `{etl_sp}`
FOR TABLES
WHEN has_tag_value('lochard_domain', 'hse')
MATCH COLUMNS has_tag_value('lochard_rls', 'hse_privilege') AS p USING COLUMNS (p);

CREATE OR REPLACE POLICY lochard_rf_comment_visibility ON SCHEMA {gold}
COMMENT 'Board-only / LLT-only scorecard commentary'
ROW FILTER {governance}.rf_comment_visibility
TO `account users` EXCEPT `{etl_sp}`
FOR TABLES
WHEN has_tag_value('lochard_domain', 'board')
MATCH COLUMNS has_tag_value('lochard_rls', 'comment_visibility') AS v USING COLUMNS (v);
