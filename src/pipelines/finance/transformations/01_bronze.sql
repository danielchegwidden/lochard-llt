-- =====================================================================================================
-- Finance – BRONZE - Business Central GL entries / SITEBUD budgets / YEO reforecasts, Maximo PO lines.
-- Auto Loader (read_files) incrementally picks up each daily interface file; raw strings + file metadata.
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_gl_entries
COMMENT 'Business Central G/L Entry extracts for company Iona Ops Trust (raw, daily files)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Business Central')
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _file_ts,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/erp/gl_entries/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_budget_entries
COMMENT 'SITEBUDyy budget entries (Board-endorsed budget, monthly by cost centre / account)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Business Central')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/erp/budget/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_yeo_entries
COMMENT 'Year End Outlook (YEO) reforecast versions, monthly by cost centre / account'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Business Central')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/erp/yeo/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_po_lines
COMMENT 'Maximo purchase-order lines (site S3620) incl. Budgeted / Emergent classification'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Maximo')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/maximo/purchase_orders/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');
