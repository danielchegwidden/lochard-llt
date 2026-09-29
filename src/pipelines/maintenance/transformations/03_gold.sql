-- =====================================================================================================
-- Maintenance – GOLD
-- =====================================================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_workorder_schedule_weekly
COMMENT 'Weekly Maximo schedule snapshot (PBI grain). Use is_latest_snapshot for current KPIs; schedule_week_start for the 13-week trend.'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'maintenance')
AS SELECT s.*, s.status NOT IN ('CLOSE', 'COMP', 'CAN', 'CLOSED', 'SRCAN') AS is_open,
          s.snapshot_date = max(s.snapshot_date) OVER () AS is_latest_snapshot
FROM ${lochard.silver}.slv_schedule_snapshot s;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_workorder
COMMENT 'Maximo work orders (current state) with asset, planner hours and overdue flags'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'maintenance')
AS SELECT w.wonum, w.work_order_key, w.description, w.asset_num, a.asset_description, w.plant_area, w.work_type,
          w.priority_bucket, w.wo_class, w.status, w.status NOT IN ('CLOSE', 'COMP', 'CAN', 'CLOSED', 'SRCAN') AS is_open,
          w.safety_critical, w.pm_generated, w.lead_craft, w.est_dur, f.planned_hours, w.reported_date, w.target_finish,
          w.scheduled_week, w.completed_date, w.closed_date, w.cancelled_date,
          w.safety_critical AND w.target_finish < current_date() AND w.status NOT IN ('CLOSE','COMP','CAN','CLOSED','SRCAN') AS is_overdue_safety_critical,
          datediff(coalesce(w.completed_date, current_date()), w.reported_date) AS age_days
FROM ${lochard.silver}.slv_workorders w
LEFT JOIN ${lochard.gold}.dim_asset a ON w.asset_num = a.asset_num
LEFT JOIN ${lochard.silver}.slv_schedule_files f ON w.wonum = f.wonum AND w.scheduled_week = f.schedule_week;
