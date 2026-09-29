-- =====================================================================================================
-- HSE – GOLD - observation / investigation facts, monthly lagging indicators (TRIFR), parity aggregate.
-- =====================================================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_observation
COMMENT 'HSE observations and investigations (one row each). Open = status NEW/INPROG. actionee is PII.'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'hse')
AS SELECT o.observation_id, o.classification, o.observation_type, o.incident_category, o.status,
          o.status IN ('NEW', 'INPROG') AS is_open, o.potential_risk_rank, o.actual_risk_rank,
          o.reported_date, cast(date_format(o.reported_date, 'yyyyMMdd') AS INT) AS date_key, d.financial_year,
          d.financial_quarter, d.month_start, d.month_label, o.due_date, o.closed_date,
          datediff(coalesce(o.closed_date, current_date()), o.reported_date) AS days_open,
          o.plant_area, o.description, o.actionee, p.team AS actionee_team, o.reported_by, o.is_high_potential_event,
          o.investigation_id, coalesce(i.is_privileged, false) AS is_privileged
FROM ${lochard.silver}.slv_observations o
LEFT JOIN ${lochard.gold}.dim_date d    ON cast(date_format(o.reported_date, 'yyyyMMdd') AS INT) = d.date_key
LEFT JOIN ${lochard.gold}.dim_person p  ON o.actionee = p.username
LEFT JOIN ${lochard.silver}.slv_investigations i ON o.investigation_id = i.investigation_id;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_investigation
COMMENT 'HSE investigations; is_privileged rows are legally privileged (hidden from non-investigators by ABAC)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'hse')
AS SELECT i.*, i.status IN ('NEW', 'INPROG') AS is_open, d.financial_year
FROM ${lochard.silver}.slv_investigations i
LEFT JOIN ${lochard.gold}.dim_date d ON cast(date_format(i.reported_date, 'yyyyMMdd') AS INT) = d.date_key;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.agg_hse_investigation_counts
COMMENT 'Investigation counts only (no row detail) – safe for Board / Genie One; untagged for row filters'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'hse')
AS SELECT financial_year, count(*) AS total_investigations, count_if(is_open) AS open_investigations,
          count_if(NOT is_open) AS closed_investigations
FROM ${lochard.gold}.fact_investigation GROUP BY financial_year;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_hse_monthly
COMMENT 'Monthly exposure hours, recordable injuries, TRIFR (per million hours, rolling 12 months) and HPEs'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'hse')
AS WITH hpe AS (
  SELECT month_start, count_if(is_high_potential_event) AS high_potential_events FROM ${lochard.gold}.fact_observation GROUP BY 1
), m AS (
  SELECT h.month_start, d.financial_year, h.employee_hours + h.contractor_hours AS hours_worked, h.recordable_injuries,
         h.lost_time_injuries, coalesce(hpe.high_potential_events, 0) AS high_potential_events
  FROM ${lochard.silver}.slv_hours_worked h
  LEFT JOIN hpe ON h.month_start = hpe.month_start
  LEFT JOIN ${lochard.gold}.dim_date d ON cast(date_format(h.month_start, 'yyyyMMdd') AS INT) = d.date_key
)
SELECT *, round(sum(recordable_injuries) OVER w * 1e6 / sum(hours_worked) OVER w, 2) AS trifr_rolling_12m,
          round(sum(lost_time_injuries) OVER w * 1e6 / sum(hours_worked) OVER w, 2) AS ltifr_rolling_12m
FROM m WINDOW w AS (ORDER BY month_start ROWS BETWEEN 11 PRECEDING AND CURRENT ROW);

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.agg_observations_daily
COMMENT 'Parity grain with the legacy HSE report (date x status x type x category x class x ranks x actionee)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'hse')
AS SELECT date_key, status, observation_type, incident_category, classification, potential_risk_rank, actual_risk_rank,
          actionee, count(*) AS observation_count
FROM ${lochard.gold}.fact_observation GROUP BY ALL;
