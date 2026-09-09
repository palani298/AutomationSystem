import { useEffect, useMemo, useState } from "react";

type Page = "runs" | "artifacts" | "operator" | "stability";

type Artifact = {
  id: string;
  slug: string;
  name: string;
  description: string;
  status: string;
  version: number;
  inputs: { name: string }[];
  outputs: { name: string }[];
  steps: { id: string; action: string; description: string }[];
};

type CatalogItem = {
  slug: string;
  name: string;
  live_version: number | null;
  live_id: string | null;
  pending_count: number;
  versions: Artifact[];
};

type Run = {
  id: string;
  kind: string;
  status: string;
  goal: string;
  artifact_id?: string;
  workflow_id?: string;
  outputs: Record<string, string>;
  result: Record<string, unknown>;
  created_at: string;
};

const DEFAULT_GOAL = "look up member 12345 and read their current savings balance";

export function App() {
  const [page, setPage] = useState<Page>("runs");
  const [activeRun, setActiveRun] = useState<string>("");
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [pending, setPending] = useState<Artifact[]>([]);
  const [flash, setFlash] = useState("");

  useEffect(() => {
    fetch("/api/catalog").then((r) => r.json()).then((data) => {
      setCatalog(data.catalog || []);
      setPending(data.pending || []);
    }).catch(() => undefined);
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/admin`);
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.catalog) setCatalog(data.catalog);
      if (data.pending) setPending(data.pending);
      if (data.type === "approval_needed") {
        setFlash(`v${data.artifact.version} of ${data.artifact.slug} needs approval`);
        setPage("artifacts");
      }
      if (data.type === "approved") {
        setFlash(`${data.mcp_tool} MCP tool now serves v${data.mcp_live_version}`);
      }
    };
    return () => ws.close();
  }, []);

  const pendingCount = pending.length;

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <h1>Capability Forge</h1>
          <p>Discover once. Replay as a typed tool. Escalate the live session when stuck.</p>
        </div>
        <nav>
          {(["runs", "artifacts", "operator", "stability"] as Page[]).map((id) => (
            <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
              {id[0].toUpperCase() + id.slice(1)}
              {id === "artifacts" && pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
            </button>
          ))}
        </nav>
        <p className="meta">Corebank proxy on /corebank · Temporal signals for handoff</p>
      </aside>
      <main className="main">
        {flash && <div className="banner">{flash}</div>}
        {page === "runs" && <RunsPage onWatch={(id) => { setActiveRun(id); setPage("operator"); }} />}
        {page === "artifacts" && (
          <ArtifactsPage catalog={catalog} onRefresh={(c, p) => { setCatalog(c); setPending(p); }} />
        )}
        {page === "operator" && <OperatorPage runId={activeRun} onRunId={setActiveRun} />}
        {page === "stability" && <StabilityPage />}
      </main>
    </div>
  );
}

function RunsPage({ onWatch }: { onWatch: (id: string) => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [error, setError] = useState("");

  async function refresh() {
    const data = await fetch("/api/runs").then((r) => r.json());
    setRuns(data);
  }
  useEffect(() => { refresh(); const t = setInterval(refresh, 2500); return () => clearInterval(t); }, []);

  async function discover() {
    setError("");
    const res = await fetch("/api/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal }),
    });
    const data = await res.json();
    if (!res.ok) { setError(data.detail || "discover failed"); return; }
    onWatch(data.run_id);
  }

  return (
    <section>
      <div className="row">
        <div>
          <h2>Runs</h2>
          <p className="lede">Start an LLM discovery against the live Corebank workbench, or inspect prior Temporal-backed runs.</p>
        </div>
      </div>
      <form className="stack card" onSubmit={(e) => { e.preventDefault(); discover(); }}>
        <label htmlFor="goal">Goal</label>
        <textarea id="goal" rows={3} value={goal} onChange={(e) => setGoal(e.target.value)} />
        <div className="actions">
          <button className="primary" type="submit">Start discovery</button>
          <a className="ghost" href="/corebank/" target="_blank" rel="noreferrer" style={{ padding: "8px 12px", textDecoration: "none" }}>Open Corebank</a>
        </div>
        {error && <p className="err">{error}</p>}
      </form>
      <div className="cards" style={{ marginTop: 16 }}>
        {runs.map((run) => (
          <article className="card" key={run.id}>
            <h3>{run.kind} · {run.goal || run.artifact_id}</h3>
            <div className="meta">{run.id}</div>
            <p><Status status={run.status} /></p>
            <div className="actions">
              <button className="ghost" onClick={() => onWatch(run.id)}>Operator console</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ArtifactsPage({
  catalog,
  onRefresh,
}: {
  catalog: CatalogItem[];
  onRefresh: (catalog: CatalogItem[], pending: Artifact[]) => void;
}) {
  const [memberId, setMemberId] = useState("12345");
  const [error, setError] = useState("");

  async function refresh() {
    const data = await fetch("/api/catalog").then((r) => r.json());
    onRefresh(data.catalog || [], data.pending || []);
  }

  async function approve(id: string) {
    await fetch(`/api/artifacts/${id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "approved" }),
    });
    refresh();
  }

  async function replay(id: string) {
    setError("");
    const res = await fetch("/api/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artifact_id: id, params: { member_id: memberId } }),
    });
    const data = await res.json();
    if (!res.ok) setError(data.detail || "replay failed");
  }

  return (
    <section>
      <div className="row">
        <div>
          <h2>Artifacts</h2>
          <p className="lede">
            Same capability slug, incrementing versions. Drafts wait for a human.
            MCP always binds the latest approved version.
          </p>
        </div>
        <label>
          Replay member id
          <input value={memberId} onChange={(e) => setMemberId(e.target.value)} />
        </label>
      </div>
      {error && <p className="err">{error}</p>}
      <div className="cards">
        {catalog.map((item) => (
          <article className="card" key={item.slug}>
            <h3>{item.name}</h3>
            <div className="meta">
              MCP tool <b>{item.slug}</b>
              {item.live_version != null ? ` · live v${item.live_version}` : " · not in MCP yet"}
            </div>
            <ul className="versions">
              {item.versions.map((artifact) => (
                <li key={artifact.id}>
                  <div>
                    <Status status={artifact.status} /> v{artifact.version}
                    {item.live_id === artifact.id ? " · MCP live" : ""}
                    <div className="meta">{artifact.id}</div>
                  </div>
                  <div className="actions">
                    {artifact.status !== "approved" && (
                      <button className="primary" onClick={() => approve(artifact.id)}>Approve</button>
                    )}
                    <button className="ghost" onClick={() => replay(artifact.id)}>Replay</button>
                  </div>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function OperatorPage({ runId, onRunId }: { runId: string; onRunId: (id: string) => void }) {
  const [shot, setShot] = useState("");
  const [meta, setMeta] = useState({ url: "", controller: "", stuck_reason: "" });
  const [note, setNote] = useState("Resuming after manual correction");

  useEffect(() => {
    if (!runId) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/runs/${runId}`);
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setShot(data.screenshot || "");
      setMeta({ url: data.url || "", controller: data.controller || "", stuck_reason: data.stuck_reason || "" });
    };
    return () => ws.close();
  }, [runId]);

  async function resume() {
    if (!runId) return;
    await fetch(`/api/runs/${runId}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
  }

  return (
    <section>
      <div className="row">
        <div>
          <h2>Operator console</h2>
          <p className="lede">Same live Playwright session. Drive the headed Chromium window, then hand control back with Resume. Temporal waits on that signal.</p>
        </div>
      </div>
      <div className="stack card" style={{ marginBottom: 16 }}>
        <label>Run id</label>
        <input value={runId} onChange={(e) => onRunId(e.target.value)} placeholder="Paste a run id" />
      </div>
      <div className="live">
        <div className="screen">
          {shot ? <img src={`data:image/png;base64,${shot}`} alt="Live session" /> : <p style={{ color: "#aaa", padding: 16 }}>No live session yet.</p>}
        </div>
        <div className="card">
          <p><Status status={meta.controller || "none"} /></p>
          <p className="meta">{meta.url}</p>
          {meta.stuck_reason && <p className="err">{meta.stuck_reason}</p>}
          <div className="stack">
            <label>Handoff note</label>
            <textarea rows={4} value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="primary" onClick={resume}>Resume automation</button>
          </div>
        </div>
      </div>
    </section>
  );
}

function StabilityPage() {
  const [data, setData] = useState<{ events: unknown[]; outcomes: { artifact_id: string; kind: string; n: number }[] }>({ events: [], outcomes: [] });
  useEffect(() => {
    fetch("/api/analytics/stability").then((r) => r.json()).then(setData);
  }, []);
  const rows = useMemo(() => data.outcomes || [], [data]);
  return (
    <section>
      <h2>Stability</h2>
      <p className="lede">DuckDB reads replay result JSON in-process — no warehouse, no extra service. This is the stretch-goal flakiness signal.</p>
      <div className="card">
        <table>
          <thead><tr><th>Artifact</th><th>Outcome</th><th>N</th></tr></thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}><td>{row.artifact_id}</td><td>{row.kind}</td><td>{row.n}</td></tr>
            ))}
            {!rows.length && <tr><td colSpan={3}>No replay results yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Status({ status }: { status: string }) {
  const cls = status.includes("succeed") || status === "approved" || status === "agent" || status === "ok"
    ? "ok"
    : status.includes("wait") || status === "human" || status === "draft"
      ? "wait"
      : status.includes("fail") || status === "none"
        ? "bad"
        : "";
  return <span className={`pill ${cls}`}>{status}</span>;
}
