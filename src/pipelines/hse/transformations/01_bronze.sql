-- =====================================================================================================
-- HSE – BRONZE - HSE system observation / incident feed (JSON), investigations, monthly exposure hours.
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_observations
COMMENT 'HSE system observations feed (hazards, incidents, near misses, safe acts, investigations) – raw JSON'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'HSE system')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/hse/observations/', format => 'json',
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_investigations
COMMENT 'HSE investigations (ICAM / 5 Whys) incl. legal-privilege flag – raw'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'HSE system')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/hse/investigations/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_hours_worked
COMMENT 'Monthly exposure hours and recordable / lost-time injuries (payroll + contractor timesheets) – raw'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'HSE system')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/hse/hours_worked/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');

CREATE OR REFRESH STREAMING TABLE ${lochard.bronze}.brz_observations_legacy_summary
COMMENT 'Legacy aggregated observations report as supplied in Sample Data.xlsx (actionees pseudonymised)'
TBLPROPERTIES ('lochard.layer' = 'bronze', 'lochard.source' = 'HSE system (legacy report)')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${lochard.landing}/hse/legacy_summary/', format => 'csv', header => true, escape => '"', multiLine => true,
                       inferColumnTypes => false, rescuedDataColumn => '_rescued_data');
