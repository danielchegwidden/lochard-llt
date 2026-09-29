-- Platform observability views (lochard_platform): data quality, pipeline runs, AI usage & cost, access audit.
-- Feeds the Data Quality, AI Cost & Quality and Governance dashboards.

CREATE OR REPLACE VIEW {platform}.v_pipeline_expectations
COMMENT 'Expectation results per pipeline update and dataset (from the pipeline event logs)'
AS WITH ev AS (
  SELECT 'shared' AS pipeline, * FROM {platform}.event_log_shared UNION ALL
  SELECT 'finance', * FROM {platform}.event_log_finance UNION ALL
  SELECT 'hse', * FROM {platform}.event_log_hse UNION ALL
  SELECT 'maintenance', * FROM {platform}.event_log_maintenance UNION ALL
  SELECT 'market_ops', * FROM {platform}.event_log_market_ops UNION ALL
  SELECT 'documents', * FROM {platform}.event_log_documents
), x AS (
  SELECT pipeline, timestamp, origin.update_id AS update_id, origin.flow_name AS flow_name,
         explode(from_json(details:flow_progress.data_quality.expectations::string,
                 'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e,
         details:flow_progress.data_quality.dropped_records::bigint AS dropped_records
  FROM ev WHERE event_type = 'flow_progress' AND details:flow_progress.data_quality.expectations IS NOT NULL
)
SELECT pipeline, timestamp, update_id, split_part(e.dataset, '.', 2) AS layer, split_part(e.dataset, '.', 3) AS table_name,
       e.name AS expectation, e.passed_records, e.failed_records,
       e.failed_records / nullif(e.passed_records + e.failed_records, 0) AS failure_rate, dropped_records
FROM x;

CREATE OR REPLACE VIEW {platform}.v_pipeline_updates
COMMENT 'Pipeline update outcomes and durations'
AS WITH ev AS (
  SELECT 'shared' AS pipeline, * FROM {platform}.event_log_shared UNION ALL
  SELECT 'finance', * FROM {platform}.event_log_finance UNION ALL
  SELECT 'hse', * FROM {platform}.event_log_hse UNION ALL
  SELECT 'maintenance', * FROM {platform}.event_log_maintenance UNION ALL
  SELECT 'market_ops', * FROM {platform}.event_log_market_ops UNION ALL
  SELECT 'documents', * FROM {platform}.event_log_documents
)
SELECT pipeline, origin.update_id AS update_id, min(timestamp) AS started_at, max(timestamp) AS ended_at,
       timestampdiff(SECOND, min(timestamp), max(timestamp)) AS duration_s,
       max_by(details:update_progress.state::string, timestamp) FILTER (WHERE event_type = 'update_progress') AS final_state,
       count_if(level = 'ERROR') AS error_events
FROM ev GROUP BY pipeline, origin.update_id;

CREATE OR REPLACE VIEW {platform}.v_table_freshness
COMMENT 'Latest business date per domain vs freshness SLA (reads ungoverned silver so it can run on Lakehouse//RT)'
AS SELECT 'finance (GL)' AS table_name, max(posting_date) AS latest_business_date, 3 AS sla_days FROM {silver}.slv_gl_entries
UNION ALL SELECT 'hse (observations)', max(reported_date), 2 FROM {silver}.slv_observations
UNION ALL SELECT 'maintenance (schedule snapshot)', max(snapshot_date), 8 FROM {silver}.slv_schedule_snapshot
UNION ALL SELECT 'market (AEMO INT287)', max(gas_date), 2 FROM {silver}.slv_vic_demand_daily
UNION ALL SELECT 'operations (Iona historian)', max(gas_date), 2 FROM {silver}.slv_iona_ops_daily;

CREATE OR REPLACE VIEW {platform}.v_ai_usage
COMMENT 'Unity AI Gateway usage for Lochard model services (tokens, latency, routing, requester, request tags)'
AS SELECT event_time, date(event_time) AS usage_date, service_name, split_part(service_name, '.', 3) AS model_service,
          destination_name, destination_model, requester, requester_type, status_code, latency_ms, time_to_first_byte_ms,
          input_tokens, output_tokens, total_tokens, request_tags, request_tags['arm'] AS experiment_arm,
          request_tags['app'] AS app, size(routing_information.attempts) AS attempts,
          exists(routing_information.attempts, a -> a.action <> 'INITIAL_ATTEMPT') AS used_fallback,
          element_at(routing_information.attempts, -1).destination AS routed_destination
FROM system.ai_gateway.usage
WHERE workspace_id = '{workspace_id}' AND service_name LIKE '{catalog}.%ai.%';

CREATE OR REPLACE VIEW {platform}.v_ai_token_prices
COMMENT 'Indicative pay-per-token list prices (USD per 1M tokens) used to estimate AI cost per request; replace with contracted rates'
AS SELECT * FROM VALUES
  ('claude-opus-5-5', 15.0, 75.0), ('claude-sonnet-5', 3.0, 15.0), ('claude-haiku-4-5', 1.0, 5.0),
  ('gpt-6-sol', 10.0, 40.0), ('gpt-5-5', 1.25, 10.0), ('gemini-3-8-flash', 0.3, 2.5), ('gpt-oss-120b', 0.15, 0.6),
  ('qwen35-122b-a10b', 0.2, 0.8)
AS t(model_key, usd_per_m_input, usd_per_m_output);

CREATE OR REPLACE VIEW {platform}.v_ai_cost
COMMENT 'Estimated AI spend per request = tokens x indicative list price'
AS SELECT u.*, p.model_key,
          coalesce(u.input_tokens, 0) / 1e6 * p.usd_per_m_input + coalesce(u.output_tokens, 0) / 1e6 * p.usd_per_m_output AS est_cost_usd
FROM {platform}.v_ai_usage u
LEFT JOIN {platform}.v_ai_token_prices p ON lower(coalesce(u.destination_model, u.destination_name)) LIKE concat('%', p.model_key, '%');

CREATE OR REPLACE VIEW {platform}.v_serverless_spend
COMMENT 'Serverless DBU spend for the Lochard platform by product (system.billing.usage x list prices)'
AS SELECT u.usage_date, u.billing_origin_product AS product, u.sku_name, u.usage_metadata.job_id AS job_id,
          u.usage_metadata.dlt_pipeline_id AS pipeline_id, u.usage_metadata.endpoint_name AS endpoint_name,
          u.usage_quantity AS dbus, u.usage_quantity * lp.pricing.effective_list.default AS est_cost_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices lp ON u.sku_name = lp.sku_name AND u.usage_start_time >= lp.price_start_time
  AND (lp.price_end_time IS NULL OR u.usage_start_time < lp.price_end_time)
WHERE u.workspace_id = '{workspace_id}' AND u.usage_date >= DATE'2026-09-01';

CREATE OR REPLACE VIEW {platform}.v_access_audit
COMMENT 'Audit trail of Unity Catalog / Genie / dashboard / model serving activity touching Lochard assets'
AS SELECT event_time, date(event_time) AS event_date, user_identity.email AS principal, service_name, action_name,
          coalesce(request_params['full_name_arg'], request_params['table_full_name'], request_params['name'],
                   request_params['space_id'], request_params['dashboard_id']) AS object_name,
          response.status_code AS status_code
FROM system.access.audit
WHERE workspace_id = '{workspace_id}' AND event_date >= DATE'2026-09-20'
  AND service_name IN ('unityCatalog', 'aibiGenie', 'dashboards', 'serving', 'apps', 'databrickssql')
  AND (to_json(request_params) ILIKE '%lochard%' OR service_name IN ('aibiGenie', 'dashboards', 'apps'));

CREATE OR REPLACE VIEW {platform}.v_governance_policies
COMMENT 'ABAC policies and governed tags applied to lochard_gold (policy coverage)'
AS SELECT c.schema_name, c.table_name, c.column_name, c.tag_name, c.tag_value
FROM {catalog}.information_schema.column_tags c WHERE c.schema_name LIKE '%gold' AND c.tag_name LIKE 'lochard_%';

CREATE OR REPLACE VIEW {platform}.v_ai_cost_experiment
COMMENT 'Cost vs quality experiment results (question x arm): quality 1-5 (LLM judge), tokens, latency, estimated cost'
AS SELECT run_id, run_at, qid, category, question, arm, model_service, routed_label, served_model, input_tokens,
          output_tokens, total_tokens, latency_ms, est_cost_usd, quality_score, judge_reason, answer
FROM {ai}.model_cost_experiment;

CREATE OR REPLACE VIEW {platform}.v_ai_cost_frontier
COMMENT 'Per-arm averages for the latest experiment run: quality vs cost per 100 answers'
AS WITH latest AS (SELECT max_by(run_id, run_at) AS run_id FROM {ai}.model_cost_experiment)
SELECT arm, count(*) AS answers, avg(quality_score) AS avg_quality, sum(est_cost_usd) / count(*) * 100 AS cost_per_100_answers_usd,
       avg(latency_ms) AS avg_latency_ms, avg(total_tokens) AS avg_tokens
FROM {ai}.model_cost_experiment WHERE run_id = (SELECT run_id FROM latest) GROUP BY arm;
