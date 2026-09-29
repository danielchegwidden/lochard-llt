-- Governance UDFs (lochard_governance). Referenced by the ABAC policies in 04_policies.sql.

CREATE OR REPLACE FUNCTION {governance}.has_persona(p STRING)
RETURNS BOOLEAN
COMMENT 'TRUE when the current principal holds persona p (entitlement table or account group lochard_<p>)'
RETURN EXISTS (SELECT 1 FROM {governance}.principal_persona e WHERE e.principal = current_user() AND e.persona = p)
    OR is_account_group_member(concat('lochard_', p));

CREATE OR REPLACE FUNCTION {governance}.mask_person(v STRING)
RETURNS STRING
COMMENT 'PII: people names / usernames – visible to HSE, HSE investigators and platform admins; otherwise a stable pseudonym'
RETURN CASE WHEN v IS NULL THEN NULL
            WHEN {governance}.has_persona('hse') OR {governance}.has_persona('hse_investigator')
              OR {governance}.has_persona('platform_admin') THEN v
            ELSE concat('PERSON-', substr(sha2(v, 256), 1, 8)) END;

CREATE OR REPLACE FUNCTION {governance}.mask_bank(v STRING)
RETURNS STRING
COMMENT 'PII: vendor bank details / ABN – Finance and platform admins only'
RETURN CASE WHEN v IS NULL THEN NULL
            WHEN {governance}.has_persona('finance') OR {governance}.has_persona('platform_admin') THEN v
            ELSE concat('***', right(v, 3)) END;

CREATE OR REPLACE FUNCTION {governance}.mask_gl_text(txt STRING, account_class STRING)
RETURNS STRING
COMMENT 'Confidential GL descriptions (Legal, Employee Costs) – Finance / Leadership only'
RETURN CASE WHEN account_class IN ('Legal', 'Employee Costs')
             AND NOT ({governance}.has_persona('finance') OR {governance}.has_persona('leadership')
                      OR {governance}.has_persona('platform_admin'))
            THEN concat('[restricted – ', account_class, ']') ELSE txt END;

CREATE OR REPLACE FUNCTION {governance}.rf_team(p_team STRING)
RETURNS BOOLEAN
COMMENT 'Finance RLS: Finance, Leadership, Board and admins see all teams; budget holders see only their mapped team'
RETURN {governance}.has_persona('finance') OR {governance}.has_persona('leadership') OR {governance}.has_persona('board')
    OR {governance}.has_persona('platform_admin')
    OR EXISTS (SELECT 1 FROM {governance}.principal_persona e
               WHERE e.principal = current_user() AND e.persona = 'budget_holder' AND e.team = p_team);

CREATE OR REPLACE FUNCTION {governance}.rf_hse_privilege(p_priv BOOLEAN)
RETURNS BOOLEAN
COMMENT 'HSE RLS: legally privileged investigation rows only for HSE investigators and admins'
RETURN NOT coalesce(p_priv, false) OR {governance}.has_persona('hse_investigator') OR {governance}.has_persona('platform_admin');

CREATE OR REPLACE FUNCTION {governance}.rf_comment_visibility(p_vis STRING)
RETURNS BOOLEAN
COMMENT 'Board portal comments: ALL visible to all; LLT_ONLY to LLT + Board; BOARD_ONLY to the Board (and admins)'
RETURN p_vis = 'ALL'
    OR (p_vis = 'LLT_ONLY' AND ({governance}.has_persona('leadership') OR {governance}.has_persona('board')))
    OR {governance}.has_persona('board') OR {governance}.has_persona('platform_admin');
