#!/usr/bin/env bash
# Lakehouse//RT warehouse (warehouse_type REALTIME is not yet in the bundle / CLI enum, so it's created via the REST API).
set -euo pipefail
P=${DATABRICKS_PROFILE:-fevm-dc-demo-workspace-02}
if databricks -p "$P" warehouses list -o json | python3 -c "import json,sys; sys.exit(0 if any(w['name']=='lochard-rt-wh' for w in json.load(sys.stdin)) else 1)"; then
  echo "lochard-rt-wh exists"; exit 0; fi
databricks -p "$P" api post /api/2.0/sql/warehouses --json '{"name":"lochard-rt-wh","warehouse_type":"REALTIME",
  "enable_serverless_compute":true,"cluster_size":"Small","auto_stop_mins":10,"min_num_clusters":1,"max_num_clusters":2,
  "tags":{"custom_tags":[{"key":"project","value":"lochard"},{"key":"use_case","value":"dashboards_realtime"}]}}'
