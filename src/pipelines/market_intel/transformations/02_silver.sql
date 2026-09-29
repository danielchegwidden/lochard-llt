-- =====================================================================================================
-- Market intelligence – SILVER.
--   slv_mi_documents_parsed  ai_parse_document -> text for every landed PDF (parsed and billed once)
--   slv_mi_items_enriched    each item joined to its parsed document, then classified by ai_query with a JSON
--                            schema: relevance, entities, entity group, topic, signal, sentiment, importance,
--                            summary and why it matters for Lochard (enriched and billed once – streaming table)
-- The watchlist in the prompt mirrors src/market_intel/watchlist.yml; keep the two in step.
-- =====================================================================================================
CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_mi_documents_parsed (
  CONSTRAINT parsed_ok EXPECT (parse_error IS NULL),
  CONSTRAINT has_text  EXPECT (length(doc_text) > 100)
)
COMMENT 'ASX announcement PDFs parsed with ai_parse_document'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS WITH p AS (
  SELECT path, ai_parse_document(content) AS parsed FROM STREAM(${lochard.bronze}.brz_mi_documents)
)
SELECT regexp_replace(path, '^dbfs:', '') AS path,
       concat_ws('\n', transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'),
                                 e -> variant_get(e, '$.content', 'STRING')))  AS doc_text,
       size(variant_get(parsed, '$.document.pages', 'ARRAY<VARIANT>'))         AS page_count,
       variant_get(parsed, '$.error_status', 'STRING')                          AS parse_error
FROM p;

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_mi_items_enriched (
  CONSTRAINT has_title   EXPECT (title IS NOT NULL AND length(title) > 5) ON VIOLATION DROP ROW,
  CONSTRAINT has_date    EXPECT (published_ts IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT enriched_ok EXPECT (enrichment_error IS NULL),
  CONSTRAINT valid_group EXPECT (entity_group IN ('Lochard', 'Customer', 'Competitor', 'Upstream supplier',
                                  'Regulator & market body', 'Government & policy', 'Industry & market'))
)
COMMENT 'Market intelligence items with document text and AI classification (one row per landed item)'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS WITH i AS (
  SELECT b.*, to_timestamp(b.published_at) AS published_ts,
         coalesce(nullif(trim(d.doc_text), ''), b.text, b.title) AS body, d.page_count,
         CASE WHEN d.doc_text IS NOT NULL AND length(d.doc_text) > 100 THEN 'full_text' ELSE b.content_depth END AS depth
  FROM STREAM(${lochard.bronze}.brz_mi_items) b
  LEFT JOIN ${lochard.silver}.slv_mi_documents_parsed d ON d.path = b.doc_path
),
e AS (
  SELECT i.*, ai_query('${lochard.enrich_model}', concat(
'You are a market intelligence analyst for Lochard Energy, owner and operator of the Iona underground gas storage facility near Port Campbell, Victoria (east coast Australian gas market). Lochard is delivering the Heytesbury Underground Gas Storage (HUGS) project and plans a further Iona expansion. Iona earns more when winter supply is tight and storage is valued; new LNG import terminals and other storage compete for winter peak supply; pipeline capacity (APA South West Pipeline) limits growth.

Watchlist (canonical name – group): Lochard Energy – Lochard; AGL Energy, Snowy Hydro, EnergyAustralia, Origin Energy, Alinta Energy – Customer; APA Group, Squadron Energy, Viva Energy, Vopak, GB Energy – Competitor; Beach Energy, Amplitude Energy, Esso Australia, Woodside Energy, Santos, ConocoPhillips – Upstream supplier; AEMO, AER, AEMC, ACCC – Regulator & market body; Victorian Government, Australian Government – Government & policy.

Classify the item below.
- relevance: 0 = not about Australian gas/energy markets or the watchlist (e.g. overseas politics, sport, unrelated companies, generic share-price chatter); 1 = general energy context; 2 = relevant to east coast gas, storage, LNG or a watchlist entity; 3 = directly affects Lochard, Iona/HUGS, Victorian gas supply or storage, or a customer/competitor''s gas or storage plans.
- entities: canonical watchlist names that the item is about (empty list if none). primary_entity: the main one, or "Market" if none.
- entity_group: the group of primary_entity; "Industry & market" when primary_entity is "Market".
- topic, signal (from Lochard''s perspective: Opportunity or Threat when the item plausibly changes Lochard''s revenue, costs, competition or approvals; Watch only for a specific development that could become one; otherwise Neutral), sentiment (-1 very negative .. 1 very positive for Lochard''s interests), importance (1 minor .. 5 board-level for Lochard; 4-5 only for decisions, approvals, contracts, results or projects, not for commentary, interviews or opinion pieces).
- summary: one or two factual sentences using only the item text. why_it_matters: one short sentence (at most 30 words) on the implication for Lochard (empty when relevance is 0). Australian English. Never invent facts or numbers.

ITEM
Source: ', coalesce(source_name, ''), ' (', coalesce(source_type, ''), ')
Published: ', coalesce(published_at, ''), '
Title: ', coalesce(title, ''), '
Text: ', left(coalesce(body, title), 6000)),
    responseFormat => '{"type": "json_schema", "json_schema": {"name": "market_item", "strict": true, "schema": {
      "type": "object", "additionalProperties": false,
      "required": ["relevance", "entities", "primary_entity", "entity_group", "topic", "signal", "sentiment", "importance", "summary", "why_it_matters"],
      "properties": {
        "relevance": {"type": "integer", "enum": [0, 1, 2, 3]},
        "entities": {"type": "array", "items": {"type": "string"}},
        "primary_entity": {"type": "string"},
        "entity_group": {"type": "string", "enum": ["Lochard", "Customer", "Competitor", "Upstream supplier", "Regulator & market body", "Government & policy", "Industry & market"]},
        "topic": {"type": "string", "enum": ["Gas storage", "Supply & demand", "Prices & contracts", "Policy & regulation", "Projects & investment", "Corporate & M&A", "Operations & safety", "Energy transition"]},
        "signal": {"type": "string", "enum": ["Opportunity", "Threat", "Watch", "Neutral"]},
        "sentiment": {"type": "number"},
        "importance": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "summary": {"type": "string"},
        "why_it_matters": {"type": "string"}}}}}',
    failOnError => false) AS ai
  FROM i
),
x AS (
  SELECT e.*, from_json(ai.result, 'relevance INT, entities ARRAY<STRING>, primary_entity STRING, entity_group STRING,
                                    topic STRING, signal STRING, sentiment DOUBLE, importance INT, summary STRING,
                                    why_it_matters STRING') AS c,
         ai.errorMessage AS enrichment_error
  FROM e
)
SELECT item_id, source_type, source_name, title, url, published_ts, depth AS content_depth, body, page_count,
       research_summary, query, watch_entity, doc_path, asx_code, price_sensitive,
       c.relevance, c.entities, c.primary_entity, c.entity_group, c.topic, c.signal,
       greatest(-1.0, least(1.0, c.sentiment)) AS sentiment, c.importance, c.summary, c.why_it_matters,
       enrichment_error, '${lochard.enrich_model}' AS enrich_model, _ingested_at
FROM x;
