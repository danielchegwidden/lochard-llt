#!/usr/bin/env bash
# One-off (account-level) governed tag policies used by the Lochard ABAC policies. Idempotent: existing keys are skipped.
set -euo pipefail
P=${DATABRICKS_PROFILE:-fevm-dc-demo-workspace-02}
create() { databricks -p "$P" tag-policies get-tag-policy "$1" >/dev/null 2>&1 && echo "exists: $1" || \
           databricks -p "$P" tag-policies create-tag-policy --json "$2" >/dev/null && echo "ok: $1"; }
create lochard_pii '{"tag_key":"lochard_pii","description":"Lochard PII classification (governed)","values":[{"name":"person_name"},{"name":"email"},{"name":"bank_details"},{"name":"business_id"},{"name":"free_text"}]}'
create lochard_rls '{"tag_key":"lochard_rls","description":"Lochard row-level security column role (governed)","values":[{"name":"team"},{"name":"hse_privilege"},{"name":"account_class"},{"name":"comment_visibility"}]}'
create lochard_domain '{"tag_key":"lochard_domain","description":"Lochard data domain (governed)","values":[{"name":"finance"},{"name":"hse"},{"name":"maintenance"},{"name":"market"},{"name":"operations"},{"name":"board"},{"name":"platform"},{"name":"ai"}]}'
create lochard_sensitivity '{"tag_key":"lochard_sensitivity","description":"Lochard information sensitivity (governed)","values":[{"name":"public"},{"name":"internal"},{"name":"confidential"},{"name":"restricted"}]}'
