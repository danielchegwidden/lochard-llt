-- Market intelligence – the contract read by the Market Intelligence Hub, the AI/BI dashboard and Genie
-- (docs/market_intelligence.md). Items come from the lochard-market-intel pipeline; briefs from the analyst agent.

CREATE TABLE IF NOT EXISTS {ai}.market_intel_brief (
  week_start DATE, week_end DATE, headline STRING, summary_md STRING, developments_json STRING, implications_json STRING,
  watchlist_json STRING, actions_json STRING, sentiment_json STRING, n_items INT, n_sources INT, model STRING,
  tools_used ARRAY<STRING>, trace_id STRING, agent_steps INT, generated_at TIMESTAMP)
COMMENT 'Weekly market intelligence brief written by the Market Intelligence Analyst agent';

CREATE OR REPLACE VIEW {semantic}.v_market_intel_items
COMMENT 'Market intelligence items about Lochard, customers, competitors, suppliers, regulators and the gas market – one row per relevant story, AI-classified from public sources'
AS SELECT item_id, published_at, published_date, week_start, title, source_name, source_type, url, content_depth,
          summary, why_it_matters, primary_entity, entities, entity_group, topic, signal, sentiment, importance,
          relevance, excerpt, doc_path, ingested_at
FROM {gold}.fact_market_intel_item
WHERE relevance >= 1;

CREATE OR REPLACE VIEW {semantic}.v_market_intel_briefs
COMMENT 'Weekly market intelligence brief (one row per Monday-start week) written by the Market Intelligence Analyst agent'
AS SELECT week_start, week_end, headline, summary_md, developments_json, implications_json, watchlist_json,
          actions_json, sentiment_json, n_items, n_sources, model, tools_used, trace_id, generated_at
FROM {ai}.market_intel_brief;

CREATE OR REPLACE VIEW {semantic}.v_market_intel_weekly
COMMENT 'Relevant market intelligence items per week, entity group and topic, with threats, opportunities and sentiment'
AS SELECT week_start, entity_group, topic, n_items, n_threats, n_opportunities, avg_sentiment, max_importance
FROM {gold}.agg_market_intel_weekly;

CREATE OR REPLACE VIEW {semantic}.v_market_intel_entities
COMMENT 'Market intelligence watchlist: the companies, bodies and governments tracked and their relationship to Lochard'
AS SELECT entity, entity_group, relationship, description, asx_code, website
FROM {gold}.dim_market_entity;
