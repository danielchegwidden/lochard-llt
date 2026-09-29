"""Lakebase (board portal OLTP) -> Delta gold. Copies the board scorecard so Genie / Genie One / dashboards can trend
statuses, board scores and commentary alongside operational data. Runs nightly and when a period is locked.
Connects as the ETL service principal (Postgres role with bypassrls) using a short-lived OAuth credential."""
import argparse

import pandas as pd
import psycopg
from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

QUERIES = {
    "fact_board_scorecard": """
      SELECT k.kpi_id, k.fy_code, p.name AS pillar, p.pillar_no, k.code AS kpi_code, k.name AS kpi_name, k.owner_initials,
             k.owner_role, k.weight_pct::float AS weight_pct, rp.period_code, rp.label AS period_label, rp.month_start,
             rp.state AS period_state, u.status, u.owner_score, u.commentary, u.ai_draft_accepted, u.submitted_at,
             CASE u.status WHEN 'ON_TRACK' THEN 1.0 WHEN 'COMPLETE' THEN 1.0 WHEN 'AT_RISK' THEN 0.5 ELSE 0.0 END AS status_points,
             bs.avg_board_score, bs.n_directors, bs.min_board_score, bs.max_board_score,
             coalesce(c.n_comments, 0) AS n_comments
      FROM scorecard.kpi k
      JOIN scorecard.pillar p ON p.pillar_id = k.pillar_id
      JOIN scorecard.reporting_period rp ON rp.fy_code = k.fy_code
      LEFT JOIN scorecard.kpi_status_update u ON u.kpi_id = k.kpi_id AND u.period_code = rp.period_code
      LEFT JOIN (SELECT kpi_id, period_code, avg(score)::float AS avg_board_score, count(*) AS n_directors,
                        min(score) AS min_board_score, max(score) AS max_board_score
                 FROM scorecard.board_score GROUP BY 1, 2) bs ON bs.kpi_id = k.kpi_id AND bs.period_code = rp.period_code
      LEFT JOIN (SELECT kpi_id, period_code, count(*) AS n_comments FROM scorecard.comment GROUP BY 1, 2) c
             ON c.kpi_id = k.kpi_id AND c.period_code = rp.period_code""",
    "fact_board_comment": """
      SELECT comment_id, kpi_id, period_code, author_role, visibility, body, created_at, resolved
      FROM scorecard.comment""",
    "fact_board_period": """
      SELECT period_code, fy_code, label, month_start, state, board_meeting FROM scorecard.reporting_period""",
}
# Tables created by later portal migrations: skipped (not failed) until the app has applied them.
OPTIONAL = {
    "fact_leadership_commentary": """
      SELECT commentary_id, scope, subject, period_key, body, author_role, ai_assisted, submitted_at, reviewed_at,
             updated_at, version
      FROM scorecard.commentary WHERE status = 'APPROVED'""",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--endpoint", default="projects/lochard-board-portal/branches/production/endpoints/primary")
    ap.add_argument("--database", default="board_portal")
    a, _ = ap.parse_known_args()
    w = WorkspaceClient()
    ep = w.postgres.get_endpoint(name=a.endpoint)
    host = ep.status.hosts.host
    cred = w.postgres.generate_database_credential(endpoint=a.endpoint)
    user = w.current_user.me().user_name
    spark = SparkSession.builder.getOrCreate()
    with psycopg.connect(host=host, dbname=a.database, user=user, password=cred.token, sslmode="require",
                         autocommit=True) as conn:
        for tbl, sql in {**QUERIES, **OPTIONAL}.items():
            try:
                cur = conn.execute(sql)
            except psycopg.errors.UndefinedTable:
                if tbl in OPTIONAL:
                    print(f"{tbl}: source table not created yet – skipped")
                    continue
                raise
            cols = [d.name for d in cur.description]
            pdf = pd.DataFrame(cur.fetchall(), columns=cols)
            if pdf.empty and tbl in OPTIONAL:
                print(f"{tbl}: no rows yet – skipped")
                continue
            for c in pdf.columns:
                if pdf[c].dtype == object:
                    pdf[c] = pdf[c].astype("string")
            target = f"{a.catalog}.{a.prefix}gold.{tbl}"
            spark.createDataFrame(pdf).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(target)
            print(f"{target}: {len(pdf)} rows")
    spark.sql(f"COMMENT ON TABLE {a.catalog}.{a.prefix}gold.fact_board_scorecard IS 'Board scorecard by KPI x period "
              "(synced from the Lakebase board portal): status, weights, owner / board scores, commentary'")


if __name__ == "__main__":
    main()
