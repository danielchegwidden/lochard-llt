-- =====================================================================================================
-- Documents – BRONZE. Binary documents (HSE incident reports, supplier invoices, maintenance procedures / OEM
-- manuals, board papers) landed in the documents volume. Each file is ingested once (Auto Loader).
-- =====================================================================================================
CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_documents
COMMENT 'Unstructured documents (binary) for AI Functions processing'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Document stores')
AS SELECT path, modificationTime AS modified_at, length AS size_bytes, content,
          regexp_extract(path, '/documents/([^/]+)/', 1) AS doc_family,
          regexp_extract(path, '([^/]+)$', 1) AS file_name, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.documents}/', format => 'binaryFile',
                       pathGlobFilter => '*.{pdf,docx}');
