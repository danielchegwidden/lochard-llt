-- =====================================================================================================
-- Maintenance – BRONZE - Maximo work orders (JSON), weekly schedule snapshot report (CSV, the PBI grain) and the
-- planners' weekly schedule-hours spreadsheets (Excel – the "files outside the system").
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_workorders
COMMENT 'Maximo work orders, site S3620 – raw JSON'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Maximo')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/maximo/workorders/', format => 'json',
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_schedule_snapshot
COMMENT 'Maximo weekly schedule snapshot report (scheduled_workorders) – raw CSV, one file per Tuesday snapshot'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Maximo')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/maximo/schedule_snapshot/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_schedule_files
COMMENT 'Planner weekly schedule spreadsheets (xlsx) with planned hours per work order'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Planner spreadsheets')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/maximo/schedule_files/', format => 'excel', headerRows => 1,
                       schemaEvolutionMode => 'none');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_schedule_snapshot_legacy_sample
COMMENT 'Sample scheduled_workorders rows supplied by Lochard (Sample Data.xlsx), kept verbatim'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Maximo (sample)')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/maximo/legacy_sample/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');
