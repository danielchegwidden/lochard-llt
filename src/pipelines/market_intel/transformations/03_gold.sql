-- =====================================================================================================
-- Market intelligence – GOLD. One row per story (the same headline from several searches or feeds is kept once,
-- preferring the copy with the most source text), weekly aggregates and the watchlist.
-- Weeks run Monday–Sunday in Australia/Melbourne time.
-- =====================================================================================================
CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_market_intel_item
COMMENT 'Market intelligence items, enriched and de-duplicated (includes relevance 0 rows; the semantic view filters them)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'market_intel')
AS WITH x AS (
  SELECT *, to_date(from_utc_timestamp(published_ts, 'Australia/Melbourne')) AS published_date,
         left(regexp_replace(lower(title), '[^a-z0-9]', ''), 70) AS title_key,
         CASE content_depth WHEN 'full_text' THEN 2 WHEN 'summary' THEN 1 ELSE 0 END AS depth_rank
  FROM ${lochard.silver}.slv_mi_items_enriched
  WHERE enrichment_error IS NULL AND relevance IS NOT NULL
),
r AS (
  SELECT *, CAST(date_trunc('WEEK', published_date) AS DATE) AS week_start,
         row_number() OVER (PARTITION BY item_id ORDER BY _ingested_at DESC) AS rn_id
  FROM x
),
d AS (
  SELECT *, row_number() OVER (PARTITION BY week_start, title_key
                               ORDER BY depth_rank DESC, relevance DESC, published_ts) AS rn_story
  FROM r WHERE rn_id = 1
)
SELECT item_id, published_ts AS published_at, published_date, week_start, title, source_name, source_type, url,
       content_depth, summary, why_it_matters, coalesce(primary_entity, 'Market') AS primary_entity,
       coalesce(entities, array()) AS entities, entity_group, topic, signal, CAST(sentiment AS DOUBLE) AS sentiment,
       importance, relevance, left(body, 1500) AS excerpt, doc_path, _ingested_at AS ingested_at,
       length(body) AS text_length, research_summary, query AS collector_query, watch_entity, asx_code, enrich_model
FROM d WHERE rn_story = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.agg_market_intel_weekly
COMMENT 'Relevant market intelligence items per week, entity group and topic'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'market_intel')
AS SELECT week_start, entity_group, topic, count(*) AS n_items, count_if(signal = 'Threat') AS n_threats,
          count_if(signal = 'Opportunity') AS n_opportunities, avg(sentiment) AS avg_sentiment,
          max(importance) AS max_importance
FROM ${lochard.gold}.fact_market_intel_item WHERE relevance >= 1
GROUP BY week_start, entity_group, topic;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_market_entity
COMMENT 'Market intelligence watchlist (from src/market_intel/watchlist.yml, published by the collector)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'market_intel')
AS SELECT entity, entity_group, relationship, description, asx_code, website, aliases
FROM read_files('${lochard.mi}/reference/watchlist.json', format => 'json',
                schema => 'entity STRING, entity_group STRING, relationship STRING, description STRING,
                           asx_code STRING, website STRING, aliases ARRAY<STRING>');
