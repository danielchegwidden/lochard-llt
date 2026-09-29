-- Board scorecard (synced from the Lakebase board portal) – consumer views + KPI metric view.
CREATE OR REPLACE VIEW {semantic}.v_board_scorecard
COMMENT 'Board scorecard by KPI and reporting period: pillar, weight, status (On Track / At Risk / Off Track / Complete), owner and board scores, commentary'
AS SELECT * FROM {gold}.fact_board_scorecard;

CREATE OR REPLACE VIEW {semantic}.v_board_comments
COMMENT 'Board / LLT commentary on scorecard KPIs (visibility enforced by ABAC: BOARD_ONLY comments only for the Board)'
AS SELECT * FROM {gold}.fact_board_comment;

CREATE OR REPLACE VIEW {semantic}.mv_board
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
comment: "Board scorecard KPIs. Status index = weight-averaged status points (On Track / Complete 100%, At Risk 50%, Off Track 0%). Board score = weight-averaged director score (0-5) as %."
source: {gold}.fact_board_scorecard
filter: source.status IS NOT NULL
fields:
  - {name: fy_code, expr: source.fy_code}
  - {name: period_code, expr: source.period_code}
  - {name: period_label, expr: source.period_label}
  - {name: month_start, expr: source.month_start}
  - {name: pillar, expr: source.pillar}
  - {name: kpi_code, expr: source.kpi_code}
  - {name: kpi_name, expr: source.kpi_name}
  - {name: status, expr: source.status}
measures:
  - {name: status_index, expr: "SUM(source.weight_pct * source.status_points) / NULLIF(SUM(source.weight_pct), 0)", comment: "Weighted scorecard status index (0-1)"}
  - {name: weighted_board_score, expr: "SUM(source.weight_pct * source.avg_board_score / 5) / NULLIF(SUM(CASE WHEN source.avg_board_score IS NOT NULL THEN source.weight_pct END), 0)", comment: "Weighted director score as a share of 5"}
  - {name: kpis_at_risk, expr: "COUNT(1) FILTER (WHERE source.status IN ('AT_RISK', 'OFF_TRACK'))"}
  - {name: total_weight, expr: SUM(source.weight_pct)}
$$;
