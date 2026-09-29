-- Commentary written by managers / analysts and reviewed by leaders. One current text per scope + subject + period;
-- the audit trigger keeps every version. Used by Leadership Insights (scope 'insights', subject = domain,
-- period 'M:YYYY-MM'), the Market Intelligence Hub ('market', 'brief', 'W:YYYY-MM-DD') and the board pack
-- ('boardpack', slide key, board period code).
CREATE TABLE IF NOT EXISTS scorecard.commentary (
  commentary_id   bigserial PRIMARY KEY,
  scope           text NOT NULL CHECK (scope IN ('insights', 'market', 'boardpack')),
  subject         text NOT NULL,
  period_key      text NOT NULL,
  body            text NOT NULL CHECK (length(body) <= 8000),
  status          text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'RETURNED')),
  author_email    text NOT NULL,
  author_name     text,
  author_role     text,
  ai_assisted     boolean NOT NULL DEFAULT false,
  ai_model        text,
  submitted_at    timestamptz,
  reviewer_email  text,
  reviewer_name   text,
  review_note     text,
  reviewed_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  version         int NOT NULL DEFAULT 1,
  UNIQUE (scope, subject, period_key)
);
CREATE INDEX IF NOT EXISTS ix_commentary_period ON scorecard.commentary (scope, period_key);

DROP TRIGGER IF EXISTS trg_audit ON scorecard.commentary;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON scorecard.commentary
  FOR EACH ROW EXECUTE FUNCTION scorecard.audit('commentary_id');

-- Default privileges from V001 only cover objects created by that migration's role, so grant explicitly.
GRANT SELECT, INSERT, UPDATE, DELETE ON scorecard.commentary TO PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE scorecard.commentary_commentary_id_seq TO PUBLIC;
