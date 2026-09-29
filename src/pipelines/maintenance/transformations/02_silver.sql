-- =====================================================================================================
-- Maintenance – SILVER
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_workorders_validated (
  CONSTRAINT wonum_present     EXPECT (wonum IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT wonum_format      EXPECT (wonum RLIKE '^36[0-9]{8}$'),
  CONSTRAINT site_iona         EXPECT (site_id = 'S3620'),
  CONSTRAINT priority_bucket   EXPECT (priority_bucket IN ('P1','P2','P3','P4','P5','Unknown')),
  CONSTRAINT est_dur_positive  EXPECT (est_dur >= 0) ON VIOLATION DROP ROW
)
COMMENT 'Maximo work orders – typed and validated'
AS SELECT wonum, work_order_key, 'S3620' AS site_id, description, asset_num, plant_area, work_type, priority_bucket,
          wo_class, status, lower(cast(safety_critical AS STRING)) = 'true' AS safety_critical,
          lower(cast(pm_generated AS STRING)) = 'true' AS pm_generated, cast(est_dur AS DOUBLE) AS est_dur, lead_craft,
          to_date(substr(reported_date, 1, 10)) AS reported_date, to_date(substr(target_finish, 1, 10)) AS target_finish,
          to_date(substr(scheduled_week, 1, 10)) AS scheduled_week, to_date(substr(completed_date, 1, 10)) AS completed_date,
          to_date(substr(closed_date, 1, 10)) AS closed_date, to_date(substr(cancelled_date, 1, 10)) AS cancelled_date,
          _ingested_at AS updated_at, _source_file
FROM STREAM(${lochard.bronze}.brz_workorders);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_workorders
COMMENT 'Maximo work orders – current state per wonum (AUTO CDC SCD1)';

CREATE FLOW workorders_scd1 AS AUTO CDC INTO ${lochard.silver}.slv_workorders
FROM STREAM(${lochard.silver}.slv_workorders_validated)
KEYS (wonum)
SEQUENCE BY updated_at
STORED AS SCD TYPE 1;

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_schedule_snapshot (
  CONSTRAINT snapshot_present          EXPECT (snapshot_date IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT counts_non_negative       EXPECT (workorder_count >= 0 AND scheduled_count >= 0 AND backlog_count >= 0) ON VIOLATION DROP ROW,
  CONSTRAINT compliant_le_scheduled    EXPECT (schedule_compliant_count <= scheduled_count) ON VIOLATION FAIL UPDATE,
  CONSTRAINT compliant_plus_non        EXPECT (schedule_compliant_count + schedule_non_compliant_count <= scheduled_count),
  CONSTRAINT schedule_week_monday      EXPECT (schedule_week_date_key = 19000101 OR dayofweek(schedule_week_start) = 2),
  CONSTRAINT status_canonical          EXPECT (status_raw <> 'CLOSED'),
  CONSTRAINT est_hours_non_negative    EXPECT (coalesce(est_dur_scheduled, 0) >= 0)
)
COMMENT 'Weekly schedule snapshot – typed; literal ''null'' -> NULL; legacy CLOSED normalised to CLOSE'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS SELECT
  to_date(snapshot_date_key, 'yyyyMMdd') AS snapshot_date, cast(snapshot_date_key AS INT) AS snapshot_date_key,
  cast(schedule_week_date_key AS INT) AS schedule_week_date_key,
  CASE WHEN schedule_week_date_key <> '19000101' THEN to_date(schedule_week_date_key, 'yyyyMMdd') END AS schedule_week_start,
  priority_bucket, work_type, wo_class, status AS status_raw, CASE WHEN status = 'CLOSED' THEN 'CLOSE' ELSE status END AS status,
  lead_craft,
  cast(workorder_count AS INT) AS workorder_count, cast(scheduled_count AS INT) AS scheduled_count,
  cast(schedule_compliant_count AS INT) AS schedule_compliant_count,
  cast(schedule_non_compliant_count AS INT) AS schedule_non_compliant_count,
  cast(nullif(est_dur_scheduled, 'null') AS DOUBLE) AS est_dur_scheduled,
  cast(nullif(est_dur_compliant, 'null') AS DOUBLE) AS est_dur_compliant,
  cast(safety_critical_count AS INT) AS safety_critical_count,
  cast(overdue_safety_critical_count AS INT) AS overdue_safety_critical_count,
  cast(backlog_count AS INT) AS backlog_count, cast(nullif(backlog_est_dur, 'null') AS DOUBLE) AS backlog_est_dur,
  cast(nullif(backlog_est_int_lab_hrs, 'null') AS DOUBLE) AS backlog_est_int_lab_hrs,
  cast(nullif(backlog_est_ext_lab_hrs, 'null') AS DOUBLE) AS backlog_est_ext_lab_hrs,
  cast(nullif(backlog_act_lab_hrs, 'null') AS DOUBLE) AS backlog_act_lab_hrs,
  cast(pm_generated_count AS INT) AS pm_generated_count,
  cast(independently_raised_wo_count AS INT) AS independently_raised_wo_count,
  _source_file
FROM STREAM(${lochard.bronze}.brz_schedule_snapshot);

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_schedule_files (
  CONSTRAINT wonum_present EXPECT (wonum IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT hours_positive EXPECT (planned_hours >= 0)
)
COMMENT 'Planner schedule hours per work order and week (from Excel)'
AS SELECT to_date(cast(schedule_week AS STRING)) AS schedule_week, cast(wonum AS STRING) AS wonum, lead_craft,
          cast(planned_hours AS DOUBLE) AS planned_hours, planner, _source_file
FROM ${lochard.bronze}.brz_schedule_files;
