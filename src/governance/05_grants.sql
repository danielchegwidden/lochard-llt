-- RBAC: consumers read the semantic layer; domain personas also read their gold domain; nobody but ETL/admins
-- reads bronze / silver. (Principals are the persona test service principals; swap for account groups in prod.)
GRANT SELECT ON TABLE {governance}.principal_persona TO `account users`;
GRANT USE CATALOG ON CATALOG {catalog} TO `19db9068-7d97-4596-8fb1-f2755077c5be`;
GRANT USE CATALOG ON CATALOG {catalog} TO `7a679121-32a4-49ab-85e9-eb6b7ba122fe`;
GRANT USE CATALOG ON CATALOG {catalog} TO `74d672c6-b2e6-4380-bbd3-5913aec0a979`;
GRANT USE CATALOG ON CATALOG {catalog} TO `d1227b5a-79f0-4233-98e5-b0828296f548`;
GRANT USE CATALOG ON CATALOG {catalog} TO `fa18b416-69f7-4e5d-b4ac-c3c2ab8c8d87`;
GRANT USE CATALOG ON CATALOG {catalog} TO `2b59e3c9-7051-4f41-993b-65a49709660b`;
GRANT USE CATALOG ON CATALOG {catalog} TO `9816671e-fad1-4783-8764-9af26374a3fa`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {semantic} TO `19db9068-7d97-4596-8fb1-f2755077c5be`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {semantic} TO `7a679121-32a4-49ab-85e9-eb6b7ba122fe`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {semantic} TO `74d672c6-b2e6-4380-bbd3-5913aec0a979`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {semantic} TO `d1227b5a-79f0-4233-98e5-b0828296f548`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {semantic} TO `fa18b416-69f7-4e5d-b4ac-c3c2ab8c8d87`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {semantic} TO `2b59e3c9-7051-4f41-993b-65a49709660b`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {semantic} TO `9816671e-fad1-4783-8764-9af26374a3fa`;
GRANT USE SCHEMA ON SCHEMA {governance} TO `account users`;
GRANT USE SCHEMA ON SCHEMA {gold} TO `19db9068-7d97-4596-8fb1-f2755077c5be`;
GRANT SELECT ON TABLE {gold}.fact_gl_transaction TO `19db9068-7d97-4596-8fb1-f2755077c5be`;
GRANT SELECT ON TABLE {gold}.fact_finance_monthly TO `19db9068-7d97-4596-8fb1-f2755077c5be`;
GRANT SELECT ON TABLE {gold}.fact_po_line TO `19db9068-7d97-4596-8fb1-f2755077c5be`;
GRANT SELECT ON TABLE {gold}.dim_vendor TO `19db9068-7d97-4596-8fb1-f2755077c5be`;
GRANT USE SCHEMA ON SCHEMA {gold} TO `74d672c6-b2e6-4380-bbd3-5913aec0a979`;
GRANT SELECT ON TABLE {gold}.fact_observation TO `74d672c6-b2e6-4380-bbd3-5913aec0a979`;
GRANT SELECT ON TABLE {gold}.fact_investigation TO `74d672c6-b2e6-4380-bbd3-5913aec0a979`;
GRANT USE SCHEMA ON SCHEMA {gold} TO `d1227b5a-79f0-4233-98e5-b0828296f548`;
GRANT SELECT ON TABLE {gold}.fact_observation TO `d1227b5a-79f0-4233-98e5-b0828296f548`;
GRANT SELECT ON TABLE {gold}.fact_investigation TO `d1227b5a-79f0-4233-98e5-b0828296f548`;
GRANT USE SCHEMA ON SCHEMA {gold} TO `fa18b416-69f7-4e5d-b4ac-c3c2ab8c8d87`;
GRANT SELECT ON TABLE {gold}.fact_workorder TO `fa18b416-69f7-4e5d-b4ac-c3c2ab8c8d87`;
GRANT SELECT ON TABLE {gold}.fact_workorder_schedule_weekly TO `fa18b416-69f7-4e5d-b4ac-c3c2ab8c8d87`
;
-- Board portal app service principal: model services (AI drafting) + semantic reads for SP-path features.
GRANT USE CATALOG ON CATALOG {catalog} TO `9ddae195-908a-4746-9e2b-e73405898a9f`;
GRANT USE SCHEMA ON SCHEMA {ai} TO `9ddae195-908a-4746-9e2b-e73405898a9f`;
GRANT USE SCHEMA, SELECT ON SCHEMA {semantic} TO `9ddae195-908a-4746-9e2b-e73405898a9f`;
-- Everyone who can reach the app / agents may invoke the governed model services (EXECUTE is granted per service).
GRANT USE SCHEMA ON SCHEMA {ai} TO `account users`
