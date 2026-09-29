-- =====================================================================================================
-- Documents – GOLD. Human-review queue for HSE classification, invoice three-way match, knowledge chunks.
-- =====================================================================================================
CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.hse_incident_report_review
COMMENT 'AI-extracted incident reports vs the logged observation; needs_review when AI category / severity disagree (human-in-the-loop)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'hse')
AS SELECT r.report_no AS observation_id, o.reported_date, o.observation_type, o.plant_area,
          o.incident_category AS logged_category, r.ai_incident_category,
          o.potential_risk_rank AS logged_potential_risk, r.ai_potential_risk_rank,
          r.extracted.injury AS ai_injury, r.extracted.suspected_cause AS ai_suspected_cause, r.ai_summary,
          (r.ai_incident_category <> o.incident_category
            OR (o.potential_risk_rank <> 'Unknown' AND r.ai_potential_risk_rank <> o.potential_risk_rank)) AS needs_review,
          o.potential_risk_rank = 'Unknown' AND r.ai_potential_risk_rank IS NOT NULL AS ai_fills_unknown_rank,
          r.path AS source_document
FROM ${lochard.silver}.slv_incident_reports_extracted r
LEFT JOIN ${lochard.gold}.fact_observation o ON r.report_no = o.observation_id;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.invoice_three_way_match
COMMENT 'Supplier invoices (AI-extracted) matched to GL postings (PPI) and vendor master; exceptions when amounts differ > 2% or $50'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'finance')
AS WITH gl AS (
  SELECT external_document_no, max(vendor_name) AS gl_vendor, max(cost_centre_key) AS cost_centre_key,
         max(team) AS team, sum(amount) AS gl_amount, max(posting_date) AS posting_date
  FROM ${lochard.gold}.fact_gl_transaction WHERE document_type = 'PPI' GROUP BY external_document_no
)
SELECT i.invoice_number, i.vendor_name AS invoice_vendor, i.abn, i.invoice_date, i.subtotal_amount, i.gst_amount,
       i.total_amount, gl.gl_vendor, gl.cost_centre_key, gl.team, gl.gl_amount, gl.posting_date,
       i.subtotal_amount - gl.gl_amount AS amount_difference,
       CASE WHEN gl.gl_amount IS NULL THEN 'NO_GL_MATCH'
            WHEN abs(i.subtotal_amount - gl.gl_amount) > greatest(50, abs(gl.gl_amount) * 0.02) THEN 'AMOUNT_MISMATCH'
            WHEN abs(i.gst_amount - i.subtotal_amount * 0.1) > 1 THEN 'GST_CHECK'
            ELSE 'MATCHED' END AS match_status,
       i.path AS source_document
FROM ${lochard.silver}.slv_invoices_extracted i
LEFT JOIN gl ON i.invoice_number = gl.external_document_no;

CREATE OR REFRESH STREAMING TABLE ${lochard.gold}.knowledge_chunks
COMMENT 'Retrieval chunks (procedures, OEM manuals, board papers) – Vector Search delta-sync source'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'ai', 'delta.enableChangeDataFeed' = 'true')
AS SELECT concat(file_name, '#', lpad(cast(chunk_seq AS STRING), 4, '0')) AS chunk_id, doc_family, file_name,
          path AS source_path, chunk_seq, chunk_text
FROM STREAM(${lochard.silver}.slv_knowledge_chunks)
WHERE length(chunk_text) > 40;
