-- Lochard board portal – scorecard schema (Lakebase / Postgres 17).
-- Applied at app start-up by server/migrations.py under a pg advisory lock; idempotent.

CREATE SCHEMA IF NOT EXISTS scorecard;

CREATE TABLE IF NOT EXISTS scorecard.fiscal_year (
  fy_code     text PRIMARY KEY CHECK (fy_code ~ '^FY[0-9]{2}$'),
  start_date  date NOT NULL,
  end_date    date NOT NULL,
  status      text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('DRAFT', 'ACTIVE', 'CLOSED'))
);

CREATE TABLE IF NOT EXISTS scorecard.pillar (
  pillar_id   serial PRIMARY KEY,
  fy_code     text NOT NULL REFERENCES scorecard.fiscal_year,
  pillar_no   int  NOT NULL,
  name        text NOT NULL,
  UNIQUE (fy_code, pillar_no)
);

CREATE TABLE IF NOT EXISTS scorecard.kpi (
  kpi_id          text PRIMARY KEY,                 -- e.g. FY27-1.1
  fy_code         text NOT NULL REFERENCES scorecard.fiscal_year,
  pillar_id       int  NOT NULL REFERENCES scorecard.pillar,
  code            text NOT NULL,                    -- 1.1
  name            text NOT NULL,
  owner_initials  text NOT NULL,                    -- DA/BN
  owner_role      text,
  owner_email     text,
  weight_pct      numeric(5,2) NOT NULL CHECK (weight_pct BETWEEN 0 AND 100),
  preamble        text,
  metric_binding  jsonb,
  sort_order      int,
  UNIQUE (fy_code, code)
);

CREATE TABLE IF NOT EXISTS scorecard.deliverable (
  deliverable_id serial PRIMARY KEY,
  kpi_id         text NOT NULL REFERENCES scorecard.kpi ON DELETE CASCADE,
  seq            int  NOT NULL,
  text           text NOT NULL,
  UNIQUE (kpi_id, seq)
);

CREATE TABLE IF NOT EXISTS scorecard.reporting_period (
  period_code    text PRIMARY KEY,                  -- FY27-M02
  fy_code        text NOT NULL REFERENCES scorecard.fiscal_year,
  month_start    date NOT NULL,
  period_end     date NOT NULL,
  board_meeting  date,
  label          text NOT NULL,
  state          text NOT NULL DEFAULT 'OPEN'
                 CHECK (state IN ('OPEN', 'OWNER_SUBMITTED', 'LLT_REVIEWED', 'BOARD_ENDORSED', 'LOCKED'))
);

CREATE TABLE IF NOT EXISTS scorecard.kpi_status_update (
  update_id            bigserial PRIMARY KEY,
  kpi_id               text NOT NULL REFERENCES scorecard.kpi,
  period_code          text NOT NULL REFERENCES scorecard.reporting_period,
  status               text NOT NULL CHECK (status IN ('ON_TRACK', 'AT_RISK', 'OFF_TRACK', 'COMPLETE')),
  owner_score          int CHECK (owner_score BETWEEN 0 AND 5),
  achievement_pct      numeric(5,1),
  commentary           text CHECK (length(commentary) <= 4000),
  ai_draft_commentary  text,
  ai_draft_accepted    boolean,
  ai_model             text,
  submitted_by         text,
  submitted_at         timestamptz NOT NULL DEFAULT now(),
  version              int NOT NULL DEFAULT 1,
  UNIQUE (kpi_id, period_code)
);

CREATE TABLE IF NOT EXISTS scorecard.board_score (
  score_id        bigserial PRIMARY KEY,
  kpi_id          text NOT NULL REFERENCES scorecard.kpi,
  period_code     text NOT NULL REFERENCES scorecard.reporting_period,
  director_email  text NOT NULL,
  director_name   text,
  score           int NOT NULL CHECK (score BETWEEN 0 AND 5),
  rationale       text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kpi_id, period_code, director_email)
);

CREATE TABLE IF NOT EXISTS scorecard.comment (
  comment_id    bigserial PRIMARY KEY,
  kpi_id        text NOT NULL REFERENCES scorecard.kpi,
  period_code   text NOT NULL REFERENCES scorecard.reporting_period,
  parent_id     bigint REFERENCES scorecard.comment,
  author_email  text NOT NULL,
  author_name   text,
  author_role   text NOT NULL,
  body          text NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
  visibility    text NOT NULL DEFAULT 'ALL' CHECK (visibility IN ('ALL', 'BOARD_ONLY', 'LLT_ONLY')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  edited_at     timestamptz,
  resolved      boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS scorecard.approval (
  approval_id     bigserial PRIMARY KEY,
  period_code     text NOT NULL REFERENCES scorecard.reporting_period,
  from_state      text NOT NULL,
  to_state        text NOT NULL,
  approver_email  text NOT NULL,
  approver_role   text,
  decision        text NOT NULL DEFAULT 'APPROVED',
  note            text,
  decided_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scorecard.audit_log (
  id           bigserial PRIMARY KEY,
  actor_email  text,
  action       text NOT NULL,
  entity       text NOT NULL,
  entity_id    text,
  before       jsonb,
  after        jsonb,
  at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scorecard.app_user_role (
  email         text PRIMARY KEY,
  role          text NOT NULL CHECK (role IN ('BOARD', 'LLT', 'KPI_OWNER', 'ADMIN', 'OBSERVER')),
  display_name  text,
  title         text,
  initials      text
);

CREATE TABLE IF NOT EXISTS scorecard.genie_conversation (
  id               bigserial PRIMARY KEY,
  user_email       text NOT NULL,
  space_id         text NOT NULL,
  conversation_id  text NOT NULL,
  message_id       text,
  question         text,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scorecard.ask_feedback (
  id               bigserial PRIMARY KEY,
  user_email       text NOT NULL,
  space_id         text,
  conversation_id  text,
  message_id       text,
  rating           smallint NOT NULL CHECK (rating IN (-1, 1)),
  comment          text,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_status_period ON scorecard.kpi_status_update (period_code);
CREATE INDEX IF NOT EXISTS ix_score_period  ON scorecard.board_score (period_code);
CREATE INDEX IF NOT EXISTS ix_comment_kpi   ON scorecard.comment (kpi_id, period_code);
CREATE INDEX IF NOT EXISTS ix_audit_entity  ON scorecard.audit_log (entity, entity_id);

-- ---------------------------------------------------------------- weights must total 100 per FY (checked at commit)
CREATE OR REPLACE FUNCTION scorecard.check_fy_weights() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE fy text; total numeric;
BEGIN
  fy := coalesce(NEW.fy_code, OLD.fy_code);
  SELECT coalesce(sum(weight_pct), 0) INTO total FROM scorecard.kpi WHERE fy_code = fy;
  IF total <> 100 AND EXISTS (SELECT 1 FROM scorecard.kpi WHERE fy_code = fy) THEN
    RAISE EXCEPTION 'KPI weights for % must total 100 (currently %)', fy, total;
  END IF;
  RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS trg_kpi_weights ON scorecard.kpi;
CREATE CONSTRAINT TRIGGER trg_kpi_weights AFTER INSERT OR UPDATE OR DELETE ON scorecard.kpi
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION scorecard.check_fy_weights();

-- ---------------------------------------------------------------- append-only audit trail
CREATE OR REPLACE FUNCTION scorecard.audit() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE key_col text := TG_ARGV[0]; rec jsonb;
BEGIN
  IF current_setting('app.seeding', true) = 'on' THEN RETURN coalesce(NEW, OLD); END IF;
  rec := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
  INSERT INTO scorecard.audit_log (actor_email, action, entity, entity_id, before, after)
  VALUES (coalesce(nullif(current_setting('app.user_email', true), ''), current_user), TG_OP, TG_TABLE_NAME,
          rec ->> key_col,
          CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
          CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END);
  RETURN coalesce(NEW, OLD);
END $$;

CREATE OR REPLACE FUNCTION scorecard.audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only'; END $$;

DROP TRIGGER IF EXISTS trg_audit_immutable ON scorecard.audit_log;
CREATE TRIGGER trg_audit_immutable BEFORE UPDATE OR DELETE ON scorecard.audit_log
  FOR EACH ROW EXECUTE FUNCTION scorecard.audit_immutable();

DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT * FROM (VALUES ('kpi', 'kpi_id'), ('kpi_status_update', 'update_id'), ('board_score', 'score_id'),
                                 ('comment', 'comment_id'), ('reporting_period', 'period_code'),
                                 ('app_user_role', 'email')) AS v(tbl, key) LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_audit ON scorecard.%I', t.tbl);
    EXECUTE format('CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON scorecard.%I '
                   'FOR EACH ROW EXECUTE FUNCTION scorecard.audit(%L)', t.tbl, t.key);
  END LOOP;
END $$;

-- ---------------------------------------------------------------- comment visibility (defence in depth; the API also filters)
ALTER TABLE scorecard.comment ENABLE ROW LEVEL SECURITY;
ALTER TABLE scorecard.comment FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS comment_read ON scorecard.comment;
CREATE POLICY comment_read ON scorecard.comment FOR SELECT USING (
  visibility = 'ALL'
  OR (visibility = 'BOARD_ONLY' AND current_setting('app.user_role', true) IN ('BOARD', 'ADMIN'))
  OR (visibility = 'LLT_ONLY'   AND current_setting('app.user_role', true) IN ('LLT', 'BOARD', 'ADMIN'))
  OR author_email = current_setting('app.user_email', true));
DROP POLICY IF EXISTS comment_insert ON scorecard.comment;
CREATE POLICY comment_insert ON scorecard.comment FOR INSERT WITH CHECK (true);
DROP POLICY IF EXISTS comment_update ON scorecard.comment;
CREATE POLICY comment_update ON scorecard.comment FOR UPDATE
  USING (author_email = current_setting('app.user_email', true) OR current_setting('app.user_role', true) = 'ADMIN');

-- ---------------------------------------------------------------- reporting views
CREATE OR REPLACE VIEW scorecard.v_period_scores AS
SELECT k.fy_code, u.period_code, k.kpi_id, k.code, k.name, k.weight_pct, u.status,
       CASE u.status WHEN 'ON_TRACK' THEN 1.0 WHEN 'COMPLETE' THEN 1.0 WHEN 'AT_RISK' THEN 0.5 ELSE 0.0 END AS status_points,
       (SELECT avg(b.score) FROM scorecard.board_score b WHERE b.kpi_id = k.kpi_id AND b.period_code = u.period_code) AS avg_board_score,
       (SELECT count(*) FROM scorecard.board_score b WHERE b.kpi_id = k.kpi_id AND b.period_code = u.period_code) AS n_scores
FROM scorecard.kpi k JOIN scorecard.kpi_status_update u ON u.kpi_id = k.kpi_id;

CREATE OR REPLACE VIEW scorecard.v_period_summary AS
SELECT fy_code, period_code,
       round(sum(weight_pct * status_points), 1)                                   AS status_index_pct,
       round(sum(weight_pct * avg_board_score / 5.0) FILTER (WHERE avg_board_score IS NOT NULL), 1) AS weighted_board_score_pct,
       count(*) FILTER (WHERE status = 'AT_RISK')                                  AS kpis_at_risk,
       count(*) FILTER (WHERE status = 'OFF_TRACK')                                AS kpis_off_track,
       count(*)                                                                    AS kpis
FROM scorecard.v_period_scores GROUP BY fy_code, period_code;

-- ---------------------------------------------------------------- privileges
-- CONNECT to this database is governed by Lakebase (only roles provisioned on the branch – admins and the app
-- service principal – can log in), so DML is granted to PUBLIC inside the database. Tighten to a dedicated role
-- (GRANT board_portal_rw TO "<app-sp-client-id>") for stricter separation.
GRANT USAGE ON SCHEMA scorecard TO PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA scorecard TO PUBLIC;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA scorecard TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA scorecard GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA scorecard GRANT USAGE, SELECT ON SEQUENCES TO PUBLIC;
REVOKE UPDATE, DELETE ON scorecard.audit_log FROM PUBLIC;
