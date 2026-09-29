#!/usr/bin/env bash
# Agent Bricks objects (Beta CLI – not yet bundle resources). Re-runnable: skips objects that already exist.
#   Knowledge Assistant "Iona Knowledge"  – documents volume folders (procedures / OEM manuals, board papers)
#   Supervisor Agent "Lochard Leadership Analyst" – tools: 4 Genie Agents + Iona Knowledge (+ forecaster UC function)
# Genie space ids come from `databricks bundle summary -t prod -o json`.
set -euo pipefail
P=${DATABRICKS_PROFILE:-fevm-dc-demo-workspace-02}
CAT=${CATALOG:-dc_demo_workspace_02_catalog}; PREFIX=${PREFIX:-lochard_}
DOCS=/Volumes/$CAT/${PREFIX}landing/documents
summary=$(databricks bundle summary -t prod -o json)
sid() { echo "$summary" | python3 -c "import json,sys; print(json.load(sys.stdin)['resources']['genie_spaces']['$1']['id'])"; }

KA=$(databricks -p $P knowledge-assistants list-knowledge-assistants -o json | python3 -c "import json,sys; d=json.load(sys.stdin); d=d if isinstance(d,list) else d.get('knowledge_assistants',[]); print(next((k['name'] for k in d if k['display_name']=='Iona Knowledge'),''))")
if [ -z "$KA" ]; then
  KA=$(databricks -p $P knowledge-assistants create-knowledge-assistant "Iona Knowledge" \
    "Answers questions about Iona maintenance procedures, OEM manuals, isolation / permit standards and board reports, with citations." \
    --instructions "Answer only from the documents, cite the document id, never invent torque values or pressures, never name individuals." \
    -o json | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
  for f in maintenance_procedures board_papers; do
    databricks -p $P knowledge-assistants create-knowledge-source "$KA" --json \
      "{\"display_name\":\"$f\",\"description\":\"Lochard $f\",\"source_type\":\"files\",\"files\":{\"path\":\"$DOCS/$f/\"}}" >/dev/null
  done
fi
echo "KA: $KA"

SA=$(databricks -p $P supervisor-agents list-supervisor-agents -o json | python3 -c "import json,sys; d=json.load(sys.stdin); d=d if isinstance(d,list) else d.get('supervisor_agents',[]); print(next((k['name'] for k in d if k['display_name']=='Lochard Leadership Analyst'),''))")
if [ -z "$SA" ]; then
  SA=$(databricks -p $P supervisor-agents create-supervisor-agent "Lochard Leadership Analyst" \
    --description "Leadership / board Q&A across Finance, HSE, Maintenance, Gas Market & Iona Ops and Iona documents." \
    --instructions "Route to the right specialist, combine into a concise board-ready answer with period, units and source; never name individuals." \
    -o json | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
  for t in finance_genie hse_genie maintenance_genie market_ops_genie; do
    databricks -p $P supervisor-agents create-tool "$SA" "$t" --json \
      "{\"tool_type\":\"genie_space\",\"description\":\"Lochard $t\",\"genie_space\":{\"id\":\"$(sid $t)\"}}" >/dev/null
  done
  databricks -p $P supervisor-agents create-tool "$SA" iona_knowledge --json \
    "{\"tool_type\":\"knowledge_assistant\",\"description\":\"Iona documents\",\"knowledge_assistant\":{\"knowledge_assistant_id\":\"${KA##*/}\"}}" >/dev/null
fi
echo "Supervisor: $SA"
