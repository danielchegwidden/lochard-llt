-- Board pack: per-period slide settings, finalised versions and their frozen content.
--   board_pack_slide    include-in-pack toggle and owner per board reporting period and slide (audited)
--   board_pack          one row per finalised version: who / when / readiness / override reason / sent to the Board (audited)
--   board_pack_content  the frozen snapshot (slide data + approved commentary) and the PDF for each version. Insert-only;
--                       its SHA-256 hashes are recorded on board_pack, so the audit trail proves what was issued without
--                       copying the PDF into audit_log.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS scorecard.board_pack_slide (
  period_code  text NOT NULL REFERENCES scorecard.reporting_period,
  slide_key    text NOT NULL CHECK (slide_key ~ '^[a-z_]{2,40}$'),
  slide_id     text GENERATED ALWAYS AS (period_code || ':' || slide_key) STORED,
  included     boolean NOT NULL DEFAULT true,
  owner        text CHECK (length(owner) <= 80),
  updated_by   text,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (period_code, slide_key)
);

CREATE TABLE IF NOT EXISTS scorecard.board_pack (
  board_pack_id    bigserial PRIMARY KEY,
  period_code      text NOT NULL REFERENCES scorecard.reporting_period,
  version          int  NOT NULL CHECK (version >= 1),
  status           text NOT NULL DEFAULT 'FINAL' CHECK (status IN ('FINAL', 'SENT', 'SUPERSEDED')),
  slides_included  text[] NOT NULL,
  slides_ready     int  NOT NULL,
  slides_total     int  NOT NULL,
  not_ready        jsonb NOT NULL DEFAULT '[]'::jsonb,
  override_reason  text CHECK (length(override_reason) <= 2000),
  finalised_by     text NOT NULL,
  finalised_name   text,
  finalised_role   text,
  finalised_at     timestamptz NOT NULL DEFAULT now(),
  sent_by          text,
  sent_name        text,
  sent_at          timestamptz,
  superseded_at    timestamptz,
  pdf_sha256       text NOT NULL,
  pdf_bytes        int  NOT NULL,
  pdf_pages        int,
  snapshot_sha256  text NOT NULL,
  UNIQUE (period_code, version)
);

CREATE TABLE IF NOT EXISTS scorecard.board_pack_content (
  board_pack_id  bigint PRIMARY KEY REFERENCES scorecard.board_pack,
  snapshot       jsonb NOT NULL,
  pdf            bytea NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- a finalised version is frozen
-- Only the delivery fields (status, sent_*, superseded_at) may change after finalisation; versions are never deleted.
CREATE OR REPLACE FUNCTION scorecard.board_pack_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'finalised board pack % v% cannot be deleted', OLD.period_code, OLD.version;
  END IF;
  IF (NEW.board_pack_id, NEW.period_code, NEW.version, NEW.slides_included, NEW.slides_ready, NEW.slides_total,
      NEW.not_ready, NEW.override_reason, NEW.finalised_by, NEW.finalised_name, NEW.finalised_role, NEW.finalised_at,
      NEW.pdf_sha256, NEW.pdf_bytes, NEW.pdf_pages, NEW.snapshot_sha256)
     IS DISTINCT FROM
     (OLD.board_pack_id, OLD.period_code, OLD.version, OLD.slides_included, OLD.slides_ready, OLD.slides_total,
      OLD.not_ready, OLD.override_reason, OLD.finalised_by, OLD.finalised_name, OLD.finalised_role, OLD.finalised_at,
      OLD.pdf_sha256, OLD.pdf_bytes, OLD.pdf_pages, OLD.snapshot_sha256) THEN
    RAISE EXCEPTION 'finalised board pack % v% is frozen', OLD.period_code, OLD.version;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_board_pack_guard ON scorecard.board_pack;
CREATE TRIGGER trg_board_pack_guard BEFORE UPDATE OR DELETE ON scorecard.board_pack
  FOR EACH ROW EXECUTE FUNCTION scorecard.board_pack_guard();

CREATE OR REPLACE FUNCTION scorecard.board_pack_content_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'finalised board pack content is immutable'; END $$;

DROP TRIGGER IF EXISTS trg_board_pack_content_frozen ON scorecard.board_pack_content;
CREATE TRIGGER trg_board_pack_content_frozen BEFORE UPDATE OR DELETE ON scorecard.board_pack_content
  FOR EACH ROW EXECUTE FUNCTION scorecard.board_pack_content_frozen();

-- ---------------------------------------------------------------- append-only audit (same trigger as the scorecard)
DROP TRIGGER IF EXISTS trg_audit ON scorecard.board_pack;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON scorecard.board_pack
  FOR EACH ROW EXECUTE FUNCTION scorecard.audit('board_pack_id');

DROP TRIGGER IF EXISTS trg_audit ON scorecard.board_pack_slide;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON scorecard.board_pack_slide
  FOR EACH ROW EXECUTE FUNCTION scorecard.audit('slide_id');

-- ---------------------------------------------------------------- privileges
-- Default privileges from V001 only cover objects created by that migration's role, so grant explicitly.
GRANT SELECT, INSERT, UPDATE, DELETE ON scorecard.board_pack_slide TO PUBLIC;
GRANT SELECT, INSERT, UPDATE ON scorecard.board_pack TO PUBLIC;
GRANT SELECT, INSERT ON scorecard.board_pack_content TO PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE scorecard.board_pack_board_pack_id_seq TO PUBLIC;
-- Versions are never deleted and content never changes (the triggers above enforce it as well).
REVOKE DELETE ON scorecard.board_pack FROM PUBLIC;
REVOKE UPDATE, DELETE ON scorecard.board_pack_content FROM PUBLIC;
