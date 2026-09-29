import { useEffect, useState } from "react";
import { api, Me, setViewAs } from "./api";
import { NavParams, PageKey, ROLE_BLURB, ROLE_LABEL } from "./nav";
import InsightsPage from "./pages/Insights";
import MarketPage from "./pages/Market";
import BoardPackPage from "./pages/BoardPack";
import AgentsPage from "./pages/Agents";
import DashboardsPage from "./pages/Dashboards";
import GovernancePage from "./pages/Governance";
import AboutPage from "./pages/About";
import AskPopup from "./components/AskPopup";

const LOGO = "https://www.lochardenergy.com.au/wp-content/uploads/2020/09/LE_Logo-reworked.svg";
const SECTIONS: { title: string; pages: [PageKey, string, string][] }[] = [
  { title: "Leadership", pages: [["insights", "Leadership Insights", "↗"], ["market", "Market Intelligence", "◉"],
                                 ["boardpack", "Board Pack", "▦"]] },
  { title: "Explore", pages: [["agents", "Agents", "✦"], ["dashboards", "Dashboards", "◫"]] },
  { title: "Platform", pages: [["governance", "AI & Governance", "⛨"], ["about", "Architecture", "⌬"]] },
];
const KEYS = SECTIONS.flatMap((s) => s.pages.map((p) => p[0]));
const LENS = ["LLT", "KPI_OWNER", "BOARD", "ADMIN"];

function initialPage(): PageKey {
  try {
    const p = localStorage.getItem("page");
    if (p === "scorecard") return "boardpack";
    return (KEYS as string[]).includes(p || "") ? (p as PageKey) : "insights";
  } catch { return "insights"; }
}

export default function App() {
  const [page, setPage] = useState<PageKey>(initialPage);
  const [params, setParams] = useState<NavParams>({});
  const [me, setMe] = useState<Me | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lens, setLens] = useState(0);            // bumps when the role lens changes so pages reload their data
  const refreshMe = () => api.me().then(setMe).catch((e) => setErr(String(e)));
  useEffect(() => { refreshMe(); }, []);
  useEffect(() => { try { localStorage.setItem("page", page); } catch { /* private mode */ } }, [page]);
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent<{ page: PageKey; params?: NavParams }>).detail;
      setParams(d.params || {}); setPage(d.page); window.scrollTo({ top: 0 });
    };
    window.addEventListener("lochard:navigate", h);
    return () => window.removeEventListener("lochard:navigate", h);
  }, []);
  const go = (k: PageKey) => { setParams({}); setPage(k); };
  const switchLens = async (role: string) => {
    setViewAs(me && role === me.real_role ? "" : role);
    await refreshMe(); setLens((n) => n + 1);
  };

  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand"><img src={LOGO} alt="Lochard Energy" /><div>Leadership<br />Portal</div></div>
        {SECTIONS.map((s) => (
          <div key={s.title} className="nav-sec">
            <div className="nav-sec-title">{s.title}</div>
            {s.pages.map(([k, label, icon]) => (
              <button key={k} className={page === k ? "active" : ""} onClick={() => go(k)}><span className="ni">{icon}</span>{label}</button>
            ))}
          </div>
        ))}
        <div className="who">
          {me ? (<>
            <div><b>{me.name}</b></div>
            <div className="who-email">{me.email}</div>
            {me.can_view_as ? (
              <label className="lens">Viewing as
                <select value={me.role} onChange={(e) => switchLens(e.target.value)}>
                  {LENS.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}{r === me.real_role ? " (you)" : ""}</option>)}
                </select>
              </label>
            ) : <div style={{ marginTop: 6 }}>Role <span className="pill-role">{ROLE_LABEL[me.role] || me.role}</span></div>}
            <div className="lens-blurb">{ROLE_BLURB[me.role]}</div>
          </>) : err ? <span>{err}</span> : "Signing in…"}
        </div>
      </nav>
      <main key={lens}>
        {!me ? <div className="card">{err ? <div className="err">{err}</div> : "Loading…"}</div> : (
          <>
            {page === "insights" && <InsightsPage me={me} />}
            {page === "market" && <MarketPage me={me} params={params} />}
            {page === "boardpack" && <BoardPackPage me={me} params={params} />}
            {page === "agents" && <AgentsPage me={me} />}
            {page === "dashboards" && <DashboardsPage initial={params.dashboard} />}
            {page === "governance" && <GovernancePage me={me} onPersonaChange={refreshMe} />}
            {page === "about" && <AboutPage section={params.section} />}
          </>
        )}
      </main>
      {me && <AskPopup hidden={page === "agents"} page={page} />}
    </div>
  );
}
