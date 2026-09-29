-- =====================================================================================================
-- Market intelligence – BRONZE. The collector job lands one JSON object per item (news, web research, ASX
-- announcements, Lochard newsroom) and the ASX announcement PDFs. Auto Loader picks up each file once.
-- =====================================================================================================
CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_mi_items
COMMENT 'Market intelligence items as landed by the collector (one row per item and collection run)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Public market sources')
AS SELECT item_id, source_type, source_name, title, url, published_at, content_depth, text, research_summary,
          query, watch_entity, doc_path, asx_code, document_key, price_sensitive, collected_at,
          _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.mi}/items/', format => 'json',
                       schemaHints => 'item_id STRING, source_type STRING, source_name STRING, title STRING, url STRING,
                                       published_at STRING, content_depth STRING, text STRING, research_summary STRING,
                                       query STRING, watch_entity STRING, doc_path STRING, asx_code STRING,
                                       document_key STRING, price_sensitive BOOLEAN, collected_at STRING');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_mi_documents
COMMENT 'Market intelligence source documents (ASX announcement PDFs), binary'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'ASX announcements')
AS SELECT path, modificationTime AS modified_at, length AS size_bytes, content, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.mi}/documents/', format => 'binaryFile', pathGlobFilter => '*.pdf');
