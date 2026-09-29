-- =====================================================================================================
-- Documents – SILVER. ai_parse_document -> text; ai_extract / ai_classify / ai_summarize for structure.
-- Streaming tables, so every document is parsed and billed exactly once.
-- (variant_get is used instead of the colon path syntax on purpose.)
-- =====================================================================================================
CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_documents_parsed (
  CONSTRAINT parsed_ok EXPECT (parse_error IS NULL),
  CONSTRAINT has_text  EXPECT (length(doc_text) > 50)
)
COMMENT 'Parsed documents (ai_parse_document) with concatenated text per document'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS WITH p AS (
  SELECT path, doc_family, file_name, modified_at, ai_parse_document(content) AS parsed
  FROM STREAM(${lochard.bronze}.brz_documents)
)
SELECT path, doc_family, file_name, modified_at, parsed,
       concat_ws('\n', transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'),
                                 e -> variant_get(e, '$.content', 'STRING')))      AS doc_text,
       size(variant_get(parsed, '$.document.pages', 'ARRAY<VARIANT>'))             AS page_count,
       variant_get(parsed, '$.error_status', 'STRING')                              AS parse_error
FROM p;

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_incident_reports_extracted (
  CONSTRAINT report_no_present EXPECT (report_no IS NOT NULL)
)
COMMENT 'HSE incident / near-miss reports – AI-extracted fields and AI-suggested category / potential severity'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS SELECT path, file_name, regexp_extract(file_name, '(OBS-[0-9]+)', 1) AS report_no,
          ai_extract(doc_text, array('date_of_event', 'plant_area', 'event_type', 'injury', 'suspected_cause',
                                     'immediate_actions')) AS extracted,
          ai_classify(doc_text, array('GENERAL SAFETY', 'PROCESS SAFETY', 'PRODUCTION', 'ENVIRONMENTAL', 'Other')) AS ai_incident_category,
          ai_classify(doc_text, array('HIGH', 'MEDIUM', 'LOW')) AS ai_potential_risk_rank,
          ai_summarize(doc_text, 40) AS ai_summary, doc_text
FROM STREAM(${lochard.silver}.slv_documents_parsed)
WHERE doc_family = 'hse_incident_reports';

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_invoices_extracted (
  CONSTRAINT invoice_no_present EXPECT (invoice_number IS NOT NULL),
  CONSTRAINT totals_reconcile   EXPECT (abs(total_amount - (subtotal_amount + gst_amount)) <= 0.05)
)
COMMENT 'Supplier tax invoices – AI-extracted header fields (vendor, ABN, invoice no, subtotal, GST, total)'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS WITH x AS (
  SELECT path, file_name, doc_text,
         ai_extract(doc_text, array('vendor_name', 'abn', 'invoice_number', 'invoice_date', 'subtotal', 'gst', 'total')) AS f
  FROM STREAM(${lochard.silver}.slv_documents_parsed)
  WHERE doc_family = 'invoices'
)
SELECT path, file_name, f.vendor_name, f.abn, f.invoice_number, try_to_date(f.invoice_date) AS invoice_date,
       try_cast(regexp_replace(f.subtotal, '[^0-9.-]', '') AS DECIMAL(18,2)) AS subtotal_amount,
       try_cast(regexp_replace(f.gst, '[^0-9.-]', '') AS DECIMAL(18,2))      AS gst_amount,
       try_cast(regexp_replace(f.total, '[^0-9.-]', '') AS DECIMAL(18,2))    AS total_amount,
       f AS extracted
FROM x;

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_knowledge_chunks
COMMENT 'Maintenance procedures, OEM manuals and board papers split into retrieval chunks'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS SELECT path, doc_family, file_name, posexplode(
         transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'),
                   e -> variant_get(e, '$.content', 'STRING'))) AS (chunk_seq, chunk_text)
FROM STREAM(${lochard.silver}.slv_documents_parsed)
WHERE doc_family IN ('maintenance_procedures', 'board_papers');
