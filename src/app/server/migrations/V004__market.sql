-- Market Intelligence Hub – portal-side state (the Unity Catalog views are read-only for the portal).
--   market_item_annotation  analyst curation per item: pin, dismiss, note, importance override
--   market_synthesis        cached multi-week syntheses (LLM, generated from the weekly briefs), one per end week + horizon
-- The analyst's weekly commentary uses scorecard.commentary (scope 'market', subject 'brief', period 'W:YYYY-MM-DD').
CREATE TABLE IF NOT EXISTS scorecard.market_item_annotation (
  item_id              text PRIMARY KEY CHECK (length(item_id) BETWEEN 1 AND 80),
  week_start           date,
  pinned               boolean NOT NULL DEFAULT false,
  dismissed            boolean NOT NULL DEFAULT false,
  note                 text CHECK (note IS NULL OR length(note) <= 2000),
  note_by              text,
  note_at              timestamptz,
  importance_override  smallint CHECK (importance_override IS NULL OR importance_override BETWEEN 1 AND 5),
  updated_by           text NOT NULL,
  updated_by_name      text,
  updated_by_role      text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CHECK (NOT (pinned AND dismissed))
);
CREATE INDEX IF NOT EXISTS ix_market_annotation_week ON scorecard.market_item_annotation (week_start);

CREATE TABLE IF NOT EXISTS scorecard.market_synthesis (
  synthesis_id   bigserial PRIMARY KEY,
  end_week       date NOT NULL,
  horizon        smallint NOT NULL CHECK (horizon BETWEEN 2 AND 52),
  body           jsonb NOT NULL,
  source_sig     text,
  n_briefs       int NOT NULL DEFAULT 0,
  model          text,
  generated_by   text,
  generated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (end_week, horizon)
);

DROP TRIGGER IF EXISTS trg_audit ON scorecard.market_item_annotation;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON scorecard.market_item_annotation
  FOR EACH ROW EXECUTE FUNCTION scorecard.audit('item_id');
DROP TRIGGER IF EXISTS trg_audit ON scorecard.market_synthesis;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON scorecard.market_synthesis
  FOR EACH ROW EXECUTE FUNCTION scorecard.audit('synthesis_id');

-- Default privileges from V001 only cover objects created by that migration's role, so grant explicitly.
GRANT SELECT, INSERT, UPDATE, DELETE ON scorecard.market_item_annotation TO PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON scorecard.market_synthesis TO PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE scorecard.market_synthesis_synthesis_id_seq TO PUBLIC;
