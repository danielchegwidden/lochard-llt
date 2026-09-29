-- =====================================================================================================
-- HSE – SILVER - typed / validated observations and investigations, current version via AUTO CDC.
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_observations_validated (
  CONSTRAINT id_present          EXPECT (observation_id IS NOT NULL)                            ON VIOLATION DROP ROW,
  CONSTRAINT status_valid        EXPECT (status IN ('NEW', 'INPROG', 'CLOSED', 'CANCELLED'))   ON VIOLATION DROP ROW,
  CONSTRAINT close_after_report  EXPECT (closed_date IS NULL OR closed_date >= reported_date)  ON VIOLATION DROP ROW,
  CONSTRAINT type_known          EXPECT (observation_type IN ('HAZARD','INCIDENT','NEARMISS','SAFEACT','HAZARD_REPORT','Other')),
  CONSTRAINT rank_valid          EXPECT (actual_risk_rank IN ('HIGH','MEDIUM','LOW','Unknown')),
  CONSTRAINT closed_has_date     EXPECT (status <> 'CLOSED' OR closed_date IS NOT NULL),
  CONSTRAINT actionee_format     EXPECT (actionee RLIKE '^[A-Z]+\\.[A-Z]+_LOC$'),
  CONSTRAINT hpe_has_investigation EXPECT (NOT is_high_potential_event OR investigation_id IS NOT NULL)
)
COMMENT 'HSE observations – typed and validated'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS SELECT
  observation_id, classification, observation_type, incident_category, status,
  coalesce(nullif(potential_risk_rank, ''), 'Unknown') AS potential_risk_rank,
  coalesce(nullif(actual_risk_rank, ''), 'Unknown')    AS actual_risk_rank,
  to_date(substr(reported_date, 1, 10)) AS reported_date, to_date(substr(due_date, 1, 10)) AS due_date,
  to_date(substr(closed_date, 1, 10))   AS closed_date,
  plant_area, description, actionee, reported_by,
  lower(cast(is_high_potential_event AS STRING)) = 'true' AS is_high_potential_event,
  nullif(investigation_id, '') AS investigation_id, to_timestamp(updated_at) AS updated_at, _source_file
FROM STREAM(${lochard.bronze}.brz_observations);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_observations
COMMENT 'HSE observations – current state per observation_id (AUTO CDC SCD1)';

CREATE FLOW observations_scd1 AS AUTO CDC INTO ${lochard.silver}.slv_observations
FROM STREAM(${lochard.silver}.slv_observations_validated)
KEYS (observation_id)
SEQUENCE BY updated_at
STORED AS SCD TYPE 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_investigations (
  CONSTRAINT id_present EXPECT (investigation_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'HSE investigations – typed'
AS SELECT investigation_id, observation_id, to_date(reported_date) AS reported_date, incident_category,
          potential_risk_rank, actual_risk_rank, plant_area, title, lead_investigator, method,
          lower(is_privileged) = 'true' AS is_privileged, status, to_date(closed_date) AS closed_date,
          nullif(root_cause, '') AS root_cause, to_timestamp(updated_at) AS updated_at
FROM ${lochard.bronze}.brz_investigations
QUALIFY row_number() OVER (PARTITION BY investigation_id ORDER BY updated_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_hours_worked (
  CONSTRAINT hours_positive EXPECT (employee_hours > 0 AND contractor_hours > 0) ON VIOLATION DROP ROW
)
COMMENT 'Monthly exposure hours and injuries – typed'
AS SELECT to_date(concat(month, '-01')) AS month_start, cast(employee_hours AS INT) AS employee_hours,
          cast(contractor_hours AS INT) AS contractor_hours, cast(recordable_injuries AS INT) AS recordable_injuries,
          cast(lost_time_injuries AS INT) AS lost_time_injuries
FROM ${lochard.bronze}.brz_hours_worked;
