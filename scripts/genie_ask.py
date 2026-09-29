#!/usr/bin/env python3
"""Ask a Genie Agent (space) a question via the Conversation API and print SQL + result rows.
usage: scripts/genie_ask.py <space_id> "question" [--profile p]"""
import json, subprocess, sys, time
P = "fevm-dc-demo-workspace-02"


def api(method, path, body=None):
    cmd = ["databricks", "-p", P, "api", method, path] + (["--json", json.dumps(body)] if body else [])
    out = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(out.stdout or "{}") if out.stdout.strip().startswith("{") else {"_raw": out.stdout + out.stderr}


def ask(space, q):
    r = api("post", f"/api/2.0/genie/spaces/{space}/start-conversation", {"content": q})
    conv, msg = r["conversation_id"], r["message_id"]
    for _ in range(90):
        m = api("get", f"/api/2.0/genie/spaces/{space}/conversations/{conv}/messages/{msg}")
        if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(3)
    print("status:", m.get("status"))
    for att in m.get("attachments", []) or []:
        if att.get("text"):
            print("text:", att["text"].get("content", "")[:800])
        if att.get("query"):
            print("sql:", att["query"].get("query", "")[:1200])
            res = api("get", f"/api/2.0/genie/spaces/{space}/conversations/{conv}/messages/{msg}/attachments/{att['attachment_id']}/query-result")
            rows = res.get("statement_response", {}).get("result", {}).get("data_array", [])
            cols = [c["name"] for c in res.get("statement_response", {}).get("manifest", {}).get("schema", {}).get("columns", [])]
            print("cols:", cols)
            for row in rows[:12]:
                print("  ", row)
    return m


if __name__ == "__main__":
    ask(sys.argv[1], sys.argv[2])
