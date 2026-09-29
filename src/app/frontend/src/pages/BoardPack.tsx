import { ReactNode, useCallback, useEffect, useState } from "react";
import { Commentary as Rec, Me } from "../api";
import Commentary from "../components/Commentary";
import PageHead from "../components/PageHead";
import { NavParams } from "../nav";
import ScorecardPage from "./Scorecard";
import { bp, BoardPeriod, day, PackData, PackMeta, SlideMeta, SlideStatus, Snapshot, STATUS_TEXT } from "../components/boardpack/api";
import { ActivityPanel, FinaliseDialog, ReadinessBar, StatusPill, VersionsPanel } from "../components/boardpack/Panels";
import {
  CoverSlide, ExecSlide, FinanceTable, Frozen, FrozenScorecard, HugsKpi, IntelSlide, Loading, MetricSlide, OwnerSlide, SlideFrame,
} from "../components/boardpack/Slides";
import "./boardpack.css";

type Slide = SlideMeta & { commentary?: Snapshot["slides"][number]["commentary"] };

const SUB: Record<string, string> = {
  KPI_OWNER: "Draft and submit the commentary for your slides – a leader approves it before it goes into the pack.",
  LLT: "Review and approve slide commentary, choose what goes in the pack, then finalise it and issue it to the Board.",
  ADMIN: "Review and approve slide commentary, choose what goes in the pack, then finalise it and issue it to the Board.",
  BOARD: "The board pack as issued by the leadership team. Score and comment on KPIs in the scorecard slide.",
  OBSERVER: "Read-only view of the approved board pack.",
};
const two = (n: number) => String(n).padStart(2, "0");

export default function BoardPackPage({ me, params }: { me: Me; params?: NavParams }) {
  const reader = me.role === "BOARD" || me.role === "OBSERVER";
  const [periods, setPeriods] = useState<BoardPeriod[] | null>(null);
  const [code, setCode] = useState<string | null>(params?.period || null);
  const [meta, setMeta] = useState<PackMeta | null>(null);
  const [data, setData] = useState<PackData | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataErr, setDataErr] = useState<string | null>(null);
  const [view, setView] = useState<{ v: number; snap: Snapshot } | null>(null);
  const [tab, setTab] = useState(params?.tab || "cover");
  const [recs, setRecs] = useState<Record<string, Rec | null>>({});
  const [err, setErr] = useState<string | null>(null);
  const [finalising, setFinalising] = useState(false);
  const [scLive, setScLive] = useState(me.role === "BOARD");

  const loadPeriods = () => bp.periods().then((d) => {
    setPeriods(d.periods);
    // a period asked for by another page (navigate("boardpack", { period })) wins when it is a board period
    setCode((c) => (c && d.periods.some((p) => p.period_code === c) ? c : d.default || d.periods[0]?.period_code || null));
  }).catch((e) => setErr(String(e)));
  useEffect(() => { loadPeriods(); }, []);
  useEffect(() => {                                        // navigated here again while the page is open
    if (params?.period && periods?.some((p) => p.period_code === params.period)) setCode(params.period);
    if (params?.tab) setTab(params.tab);
  }, [params?.period, params?.tab]);

  const loadData = (c: string, refresh = false) => {
    setLoading(true); setDataErr(null);
    bp.data(c, refresh).then(setData).catch((e) => setDataErr(String(e))).finally(() => setLoading(false));
  };
  const openVersion = async (c: string, v: number | null) => {
    if (v === null) { setView(null); if (!data || data.period.code !== c) loadData(c); return; }
    try { const r = await bp.version(c, v); if (r.snapshot) setView({ v, snap: r.snapshot }); } catch (e) { setErr(String(e)); }
  };
  const refreshMeta = () => { if (code) bp.meta(code).then(setMeta).catch((e) => setErr(String(e))); };

  useEffect(() => {
    if (!code) return;
    let alive = true;
    setMeta(null); setView(null); setErr(null); setDataErr(null); setRecs({});
    if (!reader) loadData(code);                                   // preparers always work on the live pack
    bp.meta(code).then((m) => {
      if (!alive) return;
      setMeta(m);
      if (reader) { if (m.latest) openVersion(code, m.latest.version); else loadData(code); }   // directors read the issued pack
    }).catch((e) => setErr(String(e)));
    return () => { alive = false; };
  }, [code]);

  const onRec = useCallback((key: string, r: Rec | null) => {
    setRecs((x) => ({ ...x, [key]: r }));
    if (!r) return;
    const st: SlideStatus = r.status === "APPROVED" ? "READY" : "IN_DRAFT";
    setMeta((m) => m && { ...m, slides: m.slides.map((s) => (s.key === key && s.status !== null ? { ...s, status: st, commentary_status: r.status } : s)) });
  }, []);

  const snap = view?.snap || null;
  const labels = snap?.period || meta?.period;
  const liveData = data && data.period.code === code ? data : null;
  const all: Slide[] = snap ? snap.slides : meta?.slides || [];
  const renumber = !!snap || reader;                            // issued view: only included slides, numbered in order
  const visible: Slide[] = (renumber ? all.filter((s) => s.included) : all).map((s, i) => (renumber ? { ...s, no: i + 1 } : s));
  const idx = Math.max(0, visible.findIndex((s) => s.key === tab));
  const cur = visible[idx];
  const D = snap ? snap.data : liveData?.slides;
  const perms = meta?.perms;
  const showStatus = !!perms?.sees_workflow && !snap;
  const go = (d: number) => { const n = visible[idx + d]; if (n) setTab(n.key); };

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (finalising || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.isContentEditable || document.querySelector(".drawer")) return;
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  const setSlide = async (s: Slide, body: { included?: boolean; owner?: string }) => {
    if (!code) return;
    setMeta((m) => m && { ...m, slides: m.slides.map((x) => (x.key === s.key ? { ...x, ...(body.included !== undefined ? { included: body.included } : {}),
      ...(body.owner !== undefined ? { owner: body.owner.trim() || x.default_owner } : {}) } : x)) });
    try { await bp.setSlide(code, s.key, body); refreshMeta(); } catch (e) { setErr(String(e)); refreshMeta(); }
  };
  const changeOwner = (s: Slide) => {
    const o = window.prompt(`Who prepares “${s.title}”? Leave empty to reset to ${s.default_owner}.`, s.owner);
    if (o !== null && o.trim() !== s.owner) setSlide(s, { owner: o.trim() });
  };

  const commentaryFor = (s: Slide, compact = true): ReactNode => (snap
    ? <Frozen c={s.commentary ?? null} title={s.commentary_title} />
    : reader ? <Frozen c={meta?.approved?.[s.key] ?? null} title={s.commentary_title} live />
    : <Commentary key={`${code}:${s.key}`} me={me} scope="boardpack" subject={s.key} periodKey={code!} periodLabel={labels!.label}
                  title={s.commentary_title} owner={s.owner} placeholder={s.prompt} compact={compact}
                  onChange={(r) => onRec(s.key, r)} />);

  const ownerEmpty = (s: Slide): ReactNode => {
    if (snap) return null;
    if (reader) return meta?.approved?.[s.key] ? null
      : <div className="bp-owner-empty"><b>To be prepared by the {s.owner}</b><p>This slide has not been issued yet.</p></div>;
    const r = recs[s.key];
    if (r === undefined || r?.status === "APPROVED" || (r && perms?.can_write)) return null;
    const msg = perms?.can_write && me.role === "KPI_OWNER"
      ? <>Prepare the text for this slide below and submit it for review. It goes into the pack once a leader approves it.</>
      : perms?.can_review
        ? (r?.status === "SUBMITTED" ? null : <>Waiting for the {s.owner} to prepare this slide. Leaders can also write it directly below.</>)
        : <>This slide has not been issued yet.</>;
    return msg && <div className="bp-owner-empty"><b>To be prepared by the {s.owner}</b><p>{msg}</p></div>;
  };

  const body = (s: Slide): ReactNode => {
    const d = D?.[s.key];
    const needs = !["cover", "scorecard", "risks", "decisions"].includes(s.key);
    if (needs && !d) return dataErr ? <div className="err">The figures could not be loaded: {dataErr}</div> : <Loading />;
    switch (s.key) {
      case "cover":
        return <CoverSlide labels={labels!} slides={visible} commentary={commentaryFor(s)} onGo={setTab} showStatus={showStatus}
                           stamp={snap ? <>Version {snap.version} · final<br />Finalised {day(snap.finalised.at)} by {snap.finalised.name}</>
                             : meta?.latest ? <>Latest issued: version {meta.latest.version}<br />{meta.latest.status === "SENT" ? `Sent ${day(meta.latest.sent_at)}` : `Finalised ${day(meta.latest.finalised_at)}`}</>
                               : <>Not yet finalised</>} />;
      case "exec_summary":
        return <ExecSlide d={d} labels={labels!} commentary={commentaryFor(s)} onGo={setTab} />;
      case "scorecard":
        return (
          <div className="bp-sc">
            {snap && (
              <div className="bp-sc-mode">
                <div className="seg">
                  <button className={scLive ? "on" : ""} onClick={() => setScLive(true)}>Live scorecard</button>
                  <button className={!scLive ? "on" : ""} onClick={() => setScLive(false)}>As finalised (v{snap.version})</button>
                </div>
                <span className="note">{scLive ? "Scores, comments and the endorsement workflow are live." : "The scorecard exactly as it went into the pack."}</span>
              </div>
            )}
            {snap && !scLive ? <FrozenScorecard d={snap.data.scorecard} />
              : <ScorecardPage me={me} embedded fy={labels!.fy_code} period={labels!.code} onChanged={refreshMeta} />}
            <div className="bp-sc-cm">{commentaryFor(s)}</div>
          </div>
        );
      case "market_intel":
        return <IntelSlide d={d} commentary={commentaryFor(s)} />;
      case "risks":
      case "decisions":
        return <OwnerSlide slide={s} d={d} commentary={commentaryFor(s, false)} empty={ownerEmpty(s)} signals={showStatus} />;
      case "finance":
        return <MetricSlide d={d} commentary={commentaryFor(s)} extra={<FinanceTable t={d.table} />} />;
      case "hugs":
        return <MetricSlide d={d} commentary={commentaryFor(s)} extra={<HugsKpi k={d.kpi} eac={d.eac} />} />;
      default:
        return <MetricSlide d={d} commentary={commentaryFor(s)} />;
    }
  };

  const subFor = (s: Slide): ReactNode | undefined => {
    if (!labels) return undefined;
    if (s.key === "cover") return <>{labels.fy} · {labels.state_label}</>;
    if (s.key === "scorecard") return <>{labels.label} reporting period · {labels.state_label}</>;
    if (s.key === "market_intel") return <>{D?.market_intel?.window?.label || "The last four weeks"}</>;
    if (s.kind === "owner") return <>{labels.month_long} board meeting papers</>;
    return undefined;
  };

  const latest = meta?.latest || null;
  const opening = reader && !!latest && !snap;               // directors: the issued version is loading
  const statusLine = !latest ? (reader ? "Not yet issued to the Board" : "Not yet finalised")
    : latest.status === "SENT" ? `Version ${latest.version} sent to the Board ${day(latest.sent_at)}${latest.sent_name ? ` by ${latest.sent_name}` : ""}`
      : `Version ${latest.version} finalised ${day(latest.finalised_at)}${latest.finalised_name ? ` by ${latest.finalised_name}` : ""} – not yet sent to the Board`;

  return (
    <div className="bp-page">
      <PageHead title="Board Pack" me={me}
                sub={labels ? <>{labels.month_long} board papers · {labels.fy} · {SUB[me.role] || SUB.OBSERVER}</> : SUB[me.role]}
                right={periods && (
                  <select className="bp-period" value={code || ""} onChange={(e) => setCode(e.target.value)} aria-label="Board reporting period">
                    {periods.map((p) => (
                      <option key={p.period_code} value={p.period_code}>
                        {p.label}{p.pack_status ? ` – ${p.pack_status === "SENT" ? "sent" : p.pack_status === "FINAL" ? "final" : "superseded"} v${p.version}` : ""}
                      </option>))}
                  </select>)} />
      {err && <div className="err" style={{ marginBottom: 10 }}>{err}</div>}
      {!meta || !labels ? <div className="card">{err ? "The board pack could not be loaded." : "Loading the board pack…"}</div> : (
        <>
          <div className="card bp-strip">
            <div className="bp-strip-status"><StatusPill v={latest} /><span className="note">{statusLine}</span></div>
            {showStatus && <ReadinessBar slides={meta.slides} onGo={setTab} />}
            <div className="bp-strip-actions">
              {!snap && liveData && (
                <span className="note">Figures as at {day(liveData.generated_at, true)}{" "}
                  <button className="linkish" disabled={loading} onClick={() => loadData(code!, true)}>{loading ? "Refreshing…" : "Refresh figures"}</button></span>)}
              {latest && perms?.can_download && !snap && (
                <a href={bp.pdfUrl(labels.code, latest.version)}><button>Download PDF (v{latest.version})</button></a>)}
              {perms?.can_finalise && !snap && <button className="crimson" onClick={() => setFinalising(true)}>Finalise &amp; generate PDF</button>}
            </div>
          </div>

          {snap && (
            <div className="bp-banner">
              <div>Viewing <b>version {snap.version}</b>, finalised {day(snap.finalised.at, true)} by {snap.finalised.name}
                {view && meta.versions.find((v) => v.version === view.v)?.status === "SUPERSEDED" && <> · <b>superseded</b> by a later version</>}
                <span className="note"> · figures as at {day(snap.data_as_at, true)}</span></div>
              <div className="spacer" />
              {perms?.can_download && <a href={bp.pdfUrl(labels.code, snap.version)}><button>Download PDF</button></a>}
              {!reader && <button onClick={() => openVersion(code!, null)}>Back to the live pack</button>}
            </div>
          )}
          {reader && !snap && !latest && (
            <div className="bp-banner bp-banner-soft">
              The {labels.month_long} pack has not been issued yet. You are seeing the latest figures and approved commentary
              only; the final pack will appear here once the leadership team signs it off.
            </div>
          )}

          {opening ? <div className="card"><span className="spinner" /> Opening the issued board pack…</div> : <>
          <div className="bp-tabs" role="tablist" aria-label="Slides">
            {visible.map((s) => (
              <button key={s.key} role="tab" aria-selected={s.key === cur?.key} title={`${s.no}. ${s.title}`}
                      className={`bp-tab${s.key === cur?.key ? " on" : ""}${s.included ? "" : " bp-excluded"}`} onClick={() => setTab(s.key)}>
                <span className="bp-tab-no">{two(s.no)}</span><span className="bp-tab-t">{s.short}</span>
                {showStatus && <i className={`bp-dot bp-st-${s.included ? s.status : "EXCLUDED"}`} />}
              </button>
            ))}
          </div>

          {cur && (
            <>
              <div className="bp-controls">
                <div className="bp-ctl-l">
                  {showStatus && (cur.included ? <span className={`bp-chip bp-st-${cur.status}`}>{STATUS_TEXT[cur.status || "NOT_STARTED"]}</span>
                    : <span className="bp-chip bp-st-EXCLUDED">Not in this pack</span>)}
                  <span className="note">{snap ? `As finalised in version ${snap.version}` : cur.kind === "owner" ? "Prepared by the owner" : "Built from the latest figures"}
                    {" · "}owner <b>{cur.owner}</b></span>
                  {perms?.can_curate && !snap && <button className="linkish" onClick={() => changeOwner(cur)}>Change</button>}
                </div>
                <div className="bp-ctl-r">
                  {perms?.can_curate && !snap && (
                    <label className={`bp-toggle${cur.required ? " bp-disabled" : ""}`} title={cur.required ? "The cover is always part of the pack" : undefined}>
                      <input type="checkbox" checked={cur.included} disabled={cur.required}
                             onChange={(e) => setSlide(cur, { included: e.target.checked })} /> Include in pack</label>)}
                  <button disabled={idx === 0} onClick={() => go(-1)} aria-label="Previous slide">‹ Previous</button>
                  <button disabled={idx >= visible.length - 1} onClick={() => go(1)} aria-label="Next slide">Next ›</button>
                </div>
              </div>
              <div className={cur.included ? "" : "bp-slide-excluded"}>
                <SlideFrame slide={cur} total={visible.length} labels={labels} sub={subFor(cur)}
                            footNote={snap ? `Version ${snap.version} · final` : cur.included ? undefined : "Not in this pack"}>
                  {body(cur)}
                </SlideFrame>
              </div>
            </>
          )}
          </>}

          <div className="bp-bottom">
            <VersionsPanel meta={meta} viewing={view?.v ?? null} onView={(v) => openVersion(code!, v)}
                           onSent={() => { refreshMeta(); loadPeriods(); }} />
            {perms?.can_curate && <ActivityPanel items={meta.activity} />}
          </div>
          {finalising && (
            <FinaliseDialog meta={meta} slides={meta.slides} onClose={() => setFinalising(false)} onGo={setTab}
                            onDone={() => { refreshMeta(); loadPeriods(); }} />
          )}
        </>
      )}
    </div>
  );
}
