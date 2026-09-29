-- =====================================================================================================
-- Market & Iona Ops – BRONZE - AEMO nemweb MIBB reports (real, daily) + synthetic history in the same format,
-- Iona historian daily, site flows and customer nominations.
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_aemo_int091
COMMENT 'AEMO INT091 Actual EDD (effective degree days) – nemweb (source=AEMO) + synthetic history (source=SYNTHETIC)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'AEMO nemweb')
AS SELECT *, CASE WHEN _metadata.file_path LIKE '%/synthetic/%' THEN 'SYNTHETIC' ELSE 'AEMO' END AS data_source,
          _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/aemo/int091/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_aemo_int287
COMMENT 'AEMO INT287 total gas used (VIC demand, GJ/day) – nemweb + synthetic history'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'AEMO nemweb')
AS SELECT *, CASE WHEN _metadata.file_path LIKE '%/synthetic/%' THEN 'SYNTHETIC' ELSE 'AEMO' END AS data_source,
          _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/aemo/int287/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_aemo_int313
COMMENT 'AEMO INT313 allocated injections / withdrawals by site (hourly GJ) – includes Iona MIRNs'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'AEMO nemweb')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/aemo/int313/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_aemo_int037b
COMMENT 'AEMO INT037b indicative market price ($/GJ ex GST)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'AEMO nemweb')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/aemo/int037b/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_aemo_int153
COMMENT 'AEMO INT153 demand forecast (GJ by trading interval)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'AEMO nemweb')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/aemo/int153/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_iona_historian_daily
COMMENT 'Iona historian daily roll-up – injection, withdrawal, inventory, compressor availability'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Iona historian')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/ops/historian_daily/', format => 'parquet');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_iona_site_flows
COMMENT 'Iona per-site (Iona / North Paaratte / Wallaby Creek / Seamer) daily flows'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Iona historian')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/ops/site_flows/', format => 'parquet');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_nominations
COMMENT 'Customer daily nominations vs delivered (storage services)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'Nominations system')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/ops/nominations/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');
