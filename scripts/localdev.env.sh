# Source before running the portal locally: points the app at a throwaway Lakebase branch (default "localdev"),
# never at production.   source scripts/localdev.env.sh   [LAKEBASE_BRANCH=<branch>]
export ENDPOINT_NAME=projects/lochard-board-portal/branches/${LAKEBASE_BRANCH:-localdev}/endpoints/primary
export PGHOST=$(databricks -p "${DATABRICKS_PROFILE:-fevm-dc-demo-workspace-02}" postgres get-endpoint "$ENDPOINT_NAME" -o json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['hosts']['host'])")
