-- =====================================================================================================
-- Shared master data – BRONZE. Raw CDC extracts from Business Central (cost centres, accounts, projects,
-- vendors), Maximo (assets) and the HSE people directory. Everything lands as string; typing happens in silver.
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_cost_centres
COMMENT 'Business Central cost-centre master CDC extracts (raw)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Business Central')
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _file_ts,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/erp/cost_centres/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_accounts
COMMENT 'Business Central chart of accounts (raw)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Business Central')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/erp/accounts/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_projects
COMMENT 'Business Central job / project master (raw)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Business Central')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/erp/projects/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_vendors
COMMENT 'Business Central vendor master incl. ABN and bank details (raw, PII)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Business Central')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/erp/vendors/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_people
COMMENT 'HSE system people directory (raw, PII)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'HSE system')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/hse/people/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_assets
COMMENT 'Maximo asset register – Iona site S3620 (raw)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Maximo')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/maximo/assets/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');
