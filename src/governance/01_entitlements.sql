-- Persona entitlements. Principal = user email or service-principal application ID (what current_user() returns).
-- Works without account groups; UDFs ALSO honour account groups named lochard_<persona> when they exist.
-- The board-portal admin page (and demo presenters) switch persona by updating this table.
CREATE TABLE IF NOT EXISTS {governance}.principal_persona (
  principal   STRING  NOT NULL COMMENT 'user email or service principal application id',
  persona     STRING  NOT NULL COMMENT 'platform_admin | data_engineer | finance | budget_holder | hse | hse_investigator | maintenance | operations | leadership | board',
  team        STRING  COMMENT 'budget_holder scope (Finance team name)',
  display     STRING  COMMENT 'friendly name',
  updated_at  TIMESTAMP
) COMMENT 'Lochard persona entitlements used by ABAC row filters and column masks';

MERGE INTO {governance}.principal_persona t
USING (SELECT * FROM VALUES
  ('{platform_admin}',                        'platform_admin',   NULL,          'Platform owner / presenter'),
  ('19db9068-7d97-4596-8fb1-f2755077c5be',    'finance',          NULL,          'sp-lochard-t-finance'),
  ('7a679121-32a4-49ab-85e9-eb6b7ba122fe',    'budget_holder',    'Maintenance', 'sp-lochard-t-budgetholder-maint'),
  ('74d672c6-b2e6-4380-bbd3-5913aec0a979',    'hse',              NULL,          'sp-lochard-t-hse'),
  ('d1227b5a-79f0-4233-98e5-b0828296f548',    'hse_investigator', NULL,          'sp-lochard-t-hse-investigator'),
  ('fa18b416-69f7-4e5d-b4ac-c3c2ab8c8d87',    'maintenance',      NULL,          'sp-lochard-t-maintenance'),
  ('2b59e3c9-7051-4f41-993b-65a49709660b',    'leadership',       NULL,          'sp-lochard-t-leadership'),
  ('9816671e-fad1-4783-8764-9af26374a3fa',    'board',            NULL,          'sp-lochard-t-board')
  AS s(principal, persona, team, display)) s
ON t.principal = s.principal AND t.persona = s.persona
WHEN NOT MATCHED THEN INSERT (principal, persona, team, display, updated_at)
  VALUES (s.principal, s.persona, s.team, s.display, current_timestamp());
