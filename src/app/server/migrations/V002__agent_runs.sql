-- Every agent interaction from the Agents page: which agent, which tools it called, latency and feedback.
CREATE TABLE IF NOT EXISTS scorecard.agent_run (
  run_id       bigserial PRIMARY KEY,
  user_email   text NOT NULL,
  agent        text NOT NULL,             -- supervisor | knowledge | genie:<key> | router
  question     text NOT NULL,
  tools_used   text[] NOT NULL DEFAULT '{}',
  n_steps      int,
  n_citations  int,
  latency_ms   int,
  status       text,
  answer       text,
  detail       jsonb,                     -- routing-lab arms, genie conversation ids …
  rating       smallint CHECK (rating IN (-1, 1)),
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_run_user_idx ON scorecard.agent_run (user_email, created_at DESC);
