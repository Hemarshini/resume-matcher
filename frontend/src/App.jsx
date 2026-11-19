import { useEffect, useMemo, useRef, useState } from "react";

const API = "https://hemarshini-fitrank-api.hf.space";
const PARTS = [
  ["skills", "Skills", "var(--c-skills)"],
  ["semantic", "Semantic fit", "var(--c-sem)"],
  ["experience", "Experience", "var(--c-exp)"],
  ["education", "Education", "var(--c-edu)"],
];
const yrs = (y) => (y == null ? "–" : `${y % 1 ? y.toFixed(1) : y} yr${y === 1 ? "" : "s"}`);
const tone = (s) => (s >= 80 ? "t4" : s >= 65 ? "t3" : s >= 45 ? "t2" : "t1");

const DEFAULT_W = { skills: 40, semantic: 30, experience: 20, education: 10 };
const verdictOf = (s) => (s >= 80 ? "Strong match" : s >= 65 ? "Good match" : s >= 45 ? "Partial match" : "Weak match");
/* Re-weights a candidate client-side from the server's per-component scores (components absent from the JD stay dropped). */
function rescore(c, w) {
  const act = PARTS.reduce((a, [k]) => a + (c.breakdown[k].score == null ? 0 : w[k]), 0) || 1;
  let total = 0; const breakdown = {};
  for (const [k] of PARTS) {
    const sc = c.breakdown[k].score, eff = sc == null ? 0 : w[k] / act, pts = (sc ?? 0) * eff;
    total += pts; breakdown[k] = { score: sc, weight: +(eff * 100).toFixed(1), points: +pts.toFixed(1) };
  }
  total = +total.toFixed(1);
  return { ...c, score: total, verdict: verdictOf(total), breakdown };
}

async function call(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

/* ---------- small building blocks ---------- */
function Ring({ value, size = 132 }) {
  const r = size / 2 - 9, c = 2 * Math.PI * r;
  return (
    <svg className={`ring ${tone(value)}`} width={size} height={size} role="img" aria-label={`Match ${value} percent`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="ring-bg" />
      <circle cx={size / 2} cy={size / 2} r={r} className="ring-fg" strokeDasharray={`${(c * value) / 100} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" dy=".1em" textAnchor="middle" className="ring-num">{Math.round(value)}</text>
      <text x="50%" y="66%" textAnchor="middle" className="ring-sub">out of 100</text>
    </svg>
  );
}

/* The signature element: one bar whose segments are the points each component contributed. */
function PointsBar({ breakdown, tall }) {
  return (
    <div className={`pbar ${tall ? "tall" : ""}`} title="Points contributed by each component">
      {PARTS.map(([k, label, color]) => (
        <span key={k} style={{ width: `${breakdown[k].points}%`, background: color }} title={`${label}: ${breakdown[k].points} pts`} />
      ))}
    </div>
  );
}

const Chip = ({ children, kind = "" }) => <span className={`chip ${kind}`}>{children}</span>;

/* ---------- input panels ---------- */
function Inputs({ onRun, onDemo, busy }) {
  const [jd, setJd] = useState("");
  const [jdFile, setJdFile] = useState(null);
  const [files, setFiles] = useState([]);
  const [over, setOver] = useState(false);
  const [blind, setBlind] = useState(false);
  const [notice, setNotice] = useState("");
  const jdRef = useRef(), resRef = useRef();

  const addFiles = (list) => {
    const all = [...list];
    const ok = all.filter((f) => /\.(pdf|docx)$/i.test(f.name));
    const bad = all.filter((f) => !ok.includes(f)).map((f) => f.name);
    const fresh = ok.filter((f) => !files.some((q) => q.name === f.name && q.size === f.size));
    const dup = ok.length - fresh.length;
    setNotice([bad.length && `Not added (only PDF and DOCX are supported): ${bad.join(", ")}.`, dup && `${dup} duplicate file${dup > 1 ? "s" : ""} skipped.`].filter(Boolean).join(" "));
    setFiles((p) => [...p, ...fresh]);
  };
  const words = jd.trim() ? jd.trim().split(/\s+/).length : 0;
  const ready = (words >= 25 || jdFile) && files.length > 0;

  return (
    <section className="inputs">
      <div className="panel">
        <h2>Job description</h2>
        <textarea value={jd} onChange={(e) => setJd(e.target.value)} disabled={!!jdFile}
          placeholder="Paste the full job description. Mark nice-to-haves under a “Preferred” heading and they count for less." />
        <div className="row">
          <input ref={jdRef} type="file" accept=".pdf,.docx,.txt" hidden onChange={(e) => setJdFile(e.target.files[0] || null)} />
          {jdFile ? (
            <span className="filechip">{jdFile.name}<button aria-label="Remove file" onClick={() => setJdFile(null)}>×</button></span>
          ) : (
            <button className="link" onClick={() => jdRef.current.click()}>Upload a PDF, DOCX or TXT instead</button>
          )}
          <span className={words && words < 25 ? "gap" : "muted"}>{words ? (words < 25 ? `${words} words. Add at least 25` : `${words} words`) : ""}</span>
        </div>
      </div>

      <div className="panel">
        <h2>Resumes <span className="count">{files.length}</span></h2>
        <div className={`drop ${over ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); }}
          onClick={() => resRef.current.click()} role="button" tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && resRef.current.click()}>
          <input ref={resRef} type="file" multiple accept=".pdf,.docx" hidden onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          <strong>Drop PDF or DOCX resumes here</strong>
          <span className="muted">or click to browse. Add 10 or more in one batch.</span>
        </div>
        {notice && <p className="alert" role="alert">{notice}</p>}
        {files.length > 0 && (
          <ul className="files">
            {files.map((f, i) => (
              <li key={f.name + i}><span>{f.name}</span>
                <button aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}>×</button></li>
            ))}
          </ul>
        )}
      </div>

      <div className="actions">
        <button className="primary" disabled={!ready || busy} onClick={() => onRun(jd, jdFile, files, blind)}>
          {busy ? "Analysing resumes…" : `Rank ${files.length || ""} candidate${files.length === 1 ? "" : "s"}`}
        </button>
        <button className="ghost" disabled={busy} onClick={() => onDemo(blind)}>Try with sample data</button>
        <label className="blind"><input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} /> Blind screening <span className="muted">hides names, contact details and gendered words before scoring</span></label>
      </div>
    </section>
  );
}

/* ---------- results ---------- */
function JdSummary({ jd, model }) {
  return (
    <section className="panel jd">
      <div className="jd-head">
        <div><h2>{jd.title}</h2><p className="muted">Requirements extracted from the job description</p></div>
        <div className="facts">
          <div><b>{jd.min_years ? `${jd.min_years}+ yrs` : "–"}</b><span>experience</span></div>
          <div><b>{jd.education_label || "–"}</b><span>education</span></div>
          <div><b>{model}</b><span>embedding model</span></div>
        </div>
      </div>
      <div className="chips"><span className="lbl">Required</span>{jd.required_skills.map((s) => <Chip key={s} kind="req">{s}{jd.core_skills?.includes(s) && " ★"}</Chip>)}{jd.core_skills?.length > 0 && <span className="muted small">★ core skill, counts extra</span>}</div>
      {jd.preferred_skills.length > 0 && (
        <div className="chips"><span className="lbl">Preferred</span>{jd.preferred_skills.map((s) => <Chip key={s}>{s}</Chip>)}</div>
      )}
    </section>
  );
}

function Weights({ w, setW }) {
  const changed = PARTS.some(([k]) => w[k] !== DEFAULT_W[k]);
  return (
    <section className="panel weights">
      <div><h2>Scoring weights</h2><p className="muted small">Set what matters for this role. Candidates are re-ranked instantly.</p></div>
      {PARTS.map(([k, l, c]) => (
        <label key={k}><span><i style={{ background: c }} />{l} <b>{w[k]}</b></span>
          <input type="range" min="0" max="100" step="5" value={w[k]} onChange={(e) => setW({ ...w, [k]: +e.target.value })} /></label>
      ))}
      {changed && <button className="ghost" onClick={() => setW(DEFAULT_W)}>Reset</button>}
    </section>
  );
}

function Validation({ onClose }) {
  const [d, setD] = useState(null), [err, setErr] = useState("");
  useEffect(() => { call(`${API}/evaluate`).then(setD).catch((e) => setErr(e.message)); }, []);
  const pct = (x) => `${Math.round(x * 100)}%`;
  return (
    <div className="overlay center" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Validation report">
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        <h2>Does the scoring rank like a recruiter?</h2>
        {err && <div className="alert">{err}</div>}
        {!d && !err && <p className="muted">Running the evaluation…</p>}
        {d && (<>
          <p className="muted">Tested on {d.n_resumes} synthetic resumes with recruiter-style relevance labels, including a keyword stuffer and a candidate who paraphrases. Embedding model: <b>{d.model}</b>.</p>
          <table className="vtable">
            <thead><tr><th>Method</th><th>NDCG@5</th><th>Spearman</th><th>Pairwise</th></tr></thead>
            <tbody>{d.methods.map((m) => (
              <tr key={m.method} className={m.method.startsWith("Hybrid") ? "hl" : ""}>
                <td>{m.method}</td><td>{m.ndcg5.toFixed(2)}</td><td>{m.spearman.toFixed(2)}</td>
                <td><div className="mini"><u style={{ width: pct(m.pairwise) }} /></div>{pct(m.pairwise)}</td></tr>))}</tbody>
          </table>
          <h3>Weight tuning, checked on held-out data</h3>
          <p>Default weights {Object.values(d.tuning.default_weights).map((v) => Math.round(v * 100)).join("/")} vs weights fitted by grid search ({Object.entries(d.tuning.tuned_weights).map(([k, v]) => `${k} ${Math.round(v * 100)}`).join(", ")}). Fitted on one half of the resumes and scored on the other half (2-fold): Spearman {d.tuning.held_out_default.spearman.toFixed(2)} default vs {d.tuning.held_out_tuned.spearman.toFixed(2)} tuned.</p>
          <p className="muted small">With only {d.n_resumes} labelled resumes, tuning is a method demonstration, not a claim. With real recruiter data the same code would produce trustworthy weights, so the defaults stay as a prior.</p>
          <h3>Fairness check</h3>
          <p>Each resume was re-scored with {d.fairness.names_tested} different names. Largest score change: <b>{d.fairness.max_score_change_standard} pts</b> in standard mode, <b>{d.fairness.max_score_change_blind} pts</b> with blind screening on.</p>
        </>)}
      </div>
    </div>
  );
}

function Table({ data, onOpen }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("rank");
  const [min, setMin] = useState(0);
  const rows = useMemo(() => {
    const f = data.candidates.filter((c) => c.score >= min && (c.name + c.title + c.skills.join(" ")).toLowerCase().includes(q.toLowerCase()));
    const key = { rank: (c) => c.rank, exp: (c) => -c.years, name: (c) => c.name }[sort];
    return [...f].sort((a, b) => (key(a) > key(b) ? 1 : -1));
  }, [data, q, sort, min]);

  const exportCsv = () => {
    const head = ["Rank", "Candidate", "Experience (yrs)", "Match %", "Matched skills", "Missing required skills"];
    const body = data.candidates.map((c) => [c.rank, c.name, c.years, c.score,
      c.skills_match.matched.map((m) => m.skill).join("; "), c.skills_match.missing.filter((m) => m.required).map((m) => m.skill).join("; ")]);
    const csv = [head, ...body].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: "ranking.csv" });
    a.click();
  };

  return (
    <section className="panel table-panel">
      <div className="toolbar">
        <h2>Ranking <span className="count">{rows.length}</span></h2>
        <input className="search" placeholder="Search name, title or skill" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="slider">Min match {min}%<input type="range" min="0" max="90" step="5" value={min} onChange={(e) => setMin(+e.target.value)} /></label>
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by">
          <option value="rank">Sort: best match</option><option value="exp">Sort: experience</option><option value="name">Sort: name</option>
        </select>
        <button className="ghost" onClick={exportCsv}>Export CSV</button>
      </div>
      <div className="legend">{PARTS.map(([k, l, c]) => <span key={k}><i style={{ background: c }} />{l}</span>)}<span className="muted">Each bar shows where the points came from.</span></div>
      <div className="scroll">
        <table>
          <thead><tr><th>#</th><th>Candidate</th><th>Experience</th><th className="w-match">Match %</th><th>Matched skills</th><th>Gaps</th></tr></thead>
          <tbody>
            {rows.map((c) => {
              const miss = c.skills_match.missing.filter((m) => m.required).length;
              const m = c.skills_match.matched;
              return (
                <tr key={c.id} tabIndex={0} onClick={() => onOpen(c.id)} onKeyDown={(e) => e.key === "Enter" && onOpen(c.id)}>
                  <td className="rank">{c.rank}</td>
                  <td><b>{c.name}</b><div className="muted">{c.title || c.filename}</div></td>
                  <td>{yrs(c.years)}</td>
                  <td><div className="match"><span className={`pct ${tone(c.score)}`}>{Math.round(c.score)}%</span><PointsBar breakdown={c.breakdown} /></div></td>
                  <td><div className="chips tight">{m.slice(0, 4).map((x) => <Chip key={x.skill} kind="ok">{x.skill}</Chip>)}{m.length > 4 && <span className="muted">+{m.length - 4}</span>}{!m.length && <span className="muted">None</span>}</div></td>
                  <td>{miss ? <span className="gap">{miss} required missing</span> : <span className="muted">None</span>}</td>
                </tr>
              );
            })}
            {!rows.length && <tr><td colSpan="6" className="empty">No candidates match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ---------- candidate drawer ---------- */
function Drawer({ c, sid, onClose }) {
  const [showText, setShowText] = useState(false);
  const [sum, setSum] = useState(null), [sumBusy, setSumBusy] = useState(false);
  const writeSummary = async () => {
    setSumBusy(true);
    try { setSum(await call(`${API}/sessions/${sid}/candidates/${c.id}/summary`, { method: "POST" })); }
    catch (e) { setSum({ text: e.message, source: "error" }); } finally { setSumBusy(false); }
  };
  const sm = c.skills_match, ex = c.experience;
  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Analysis of ${c.name}`}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        <header className="d-head">
          <Ring value={c.score} />
          <div>
            <p className={`verdict ${tone(c.score)}`}>{c.verdict} · rank {c.rank}</p>
            <h2>{c.name}</h2>
            <p className="muted">{c.title}</p>
            <p className="contact">{[c.email, c.phone].filter(Boolean).join("  ·  ")}</p>
          </div>
        </header>

        <div className="summary">
          {sum ? (<><p>{sum.text}</p><small>Written by {sum.source}, from the scored facts only.</small></>)
            : <button className="ghost" disabled={sumBusy} onClick={writeSummary}>{sumBusy ? "Writing…" : "Write recruiter summary"}</button>}
        </div>

        <h3>How the score was built</h3>
        <PointsBar breakdown={c.breakdown} tall />
        <div className="parts">
          {PARTS.map(([k, label, color]) => {
            const b = c.breakdown[k];
            return (
              <div key={k} className={b.score == null ? "off" : ""}>
                <i style={{ background: color }} /><span>{label}</span>
                <b>{b.score == null ? "n/a" : `${b.score.toFixed(0)}/100`}</b>
                <em>{b.score == null ? "not in JD" : `${b.weight}% weight → ${b.points} pts`}</em>
              </div>
            );
          })}
        </div>

        <h3>Why this score</h3>
        <ul className="reasons">{c.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>

        <h3>Skills</h3>
        <div className="skillgrid">
          <div><h4>Matched ({sm.matched.length})</h4><div className="chips">{sm.matched.map((m) => <Chip key={m.skill} kind={m.verified === false ? "ok weak" : "ok"}>{m.skill}{!m.required && " (pref.)"}{m.verified === false && " · listed only"}</Chip>)}{!sm.matched.length && <span className="muted">None</span>}</div></div>
          {sm.partial.length > 0 && <div><h4>Related ({sm.partial.length})</h4><div className="chips">{sm.partial.map((m) => <Chip key={m.skill} kind="part">{m.skill} ← {m.via}</Chip>)}</div></div>}
          <div><h4>Missing ({sm.missing.length})</h4><div className="chips">{sm.missing.map((m) => <Chip key={m.skill} kind="miss">{m.skill}{!m.required && " (pref.)"}</Chip>)}{!sm.missing.length && <span className="muted">Nothing missing</span>}</div></div>
          {sm.extra.length > 0 && <div><h4>Also has</h4><div className="chips">{sm.extra.map((s) => <Chip key={s}>{s}</Chip>)}</div></div>}
        </div>

        {c.what_if?.length > 0 && (<>
          <h3>Fastest ways to improve fit</h3>
          <div className="whatif">{c.what_if.map((w) => <div key={w.skill}><span>{w.skill}{!w.required && " (pref.)"}</span><b>+{w.gain} pts</b></div>)}</div>
          <p className="muted small">Points each gap would add if the skill were demonstrated in work history (default weights).</p>
        </>)}

        <h3>Experience comparison</h3>
        {ex.required ? (
          <div className="cmp">
            <div><span>Relevant</span><div className="track"><u style={{ width: `${Math.min(100, (ex.relevant / Math.max(ex.relevant, ex.required)) * 100)}%` }} /></div><b>{yrs(ex.relevant)}</b></div>
            <div><span>Required</span><div className="track"><u className="req" style={{ width: `${Math.min(100, (ex.required / Math.max(ex.relevant, ex.required)) * 100)}%` }} /></div><b>{yrs(ex.required)}</b></div>
          </div>
        ) : <p className="muted">The job description does not state a minimum.</p>}
        <p className="muted small">{yrs(ex.candidate)} in total (from {c.years_source}), counted as {yrs(ex.relevant ?? ex.candidate)} relevant to this role. Education: {c.education_match.candidate || "not found"}{c.education_match.required ? ` (needs ${c.education_match.required})` : ""}.</p>

        {c.semantic.evidence.length > 0 && (<>
          <h3>Strongest evidence</h3>
          {c.semantic.evidence.map((e, i) => (
            <div className="evid" key={i}><p><span>JD</span>{e.jd}</p><p><span>Resume</span>{e.resume}</p><small>similarity {e.similarity}</small></div>
          ))}
          {c.semantic.gap && <div className="evid weak"><p><span>Least covered</span>{c.semantic.gap.jd}</p><small>best similarity {c.semantic.gap.similarity}</small></div>}
        </>)}

        <h3>Extracted information</h3>
        <dl className="info">
          <dt>Current title</dt><dd>{c.title || "–"}</dd>
          <dt>Experience</dt><dd>{yrs(c.years)}</dd>
          <dt>Education</dt><dd>{c.education.length ? c.education.join("; ") : "–"}</dd>
          <dt>Skills found</dt><dd>{c.skills.join(", ") || "–"}</dd>
          <dt>Source file</dt><dd>{c.filename}</dd>
        </dl>
        <button className="link" onClick={() => setShowText(!showText)}>{showText ? "Hide" : "Show"} parsed resume text</button>
        {showText && <pre className="raw">{c.text}</pre>}
      </aside>
    </div>
  );
}

/* ---------- app ---------- */
export default function App() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [weights, setWeights] = useState(DEFAULT_W);
  const [showVal, setShowVal] = useState(false);
  const ranked = useMemo(() => (data ? data.candidates.map((c) => rescore(c, weights)).sort((a, b) => b.score - a.score).map((c, i) => ({ ...c, rank: i + 1 })) : []), [data, weights]);
  const drawer = detail && { ...rescore(detail, weights), rank: ranked.find((x) => x.id === detail.id)?.rank };

  const run = async (fn) => {
    setBusy(true); setError("");
    try { setData(await fn()); window.scrollTo({ top: 0 }); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const analyse = (jd, jdFile, files, blind) => run(() => {
    const fd = new FormData();
    fd.append("jd_text", jd);
    fd.append("blind", blind);
    if (jdFile) fd.append("jd_file", jdFile);
    files.forEach((f) => fd.append("resumes", f));
    return call(`${API}/analyze`, { method: "POST", body: fd });
  });
  const open = async (id) => setDetail(await call(`${API}/sessions/${data.session_id}/candidates/${id}`));

  return (
    <div className="app">
      <header className="top">
        <div className="brand"><span className="mark" />FitRank</div>
        <div className="row"><button className="ghost" onClick={() => setShowVal(true)}>Validation</button>
          {data && <button className="ghost" onClick={() => setData(null)}>New analysis</button>}</div>
      </header>
      <main>
        {!data && (
          <div className="hero">
            <h1>Rank candidates by how well they actually fit the role.</h1>
            <p>Paste a job description, add resumes, and get an explainable score for every candidate: skills, meaning, experience and education.</p>
          </div>
        )}
        {error && <div className="alert" role="alert">{error}</div>}
        {!data ? <Inputs onRun={analyse} onDemo={(b) => run(() => call(`${API}/demo?blind=${b}`, { method: "POST" }))} busy={busy} /> : (
          <>
            {data.blind && <div className="banner">Blind screening is on: names, contact details and gendered words were removed before scoring.</div>}
            {data.jd.warnings?.map((w) => <div className="alert" key={w}>{w}</div>)}
            <JdSummary jd={data.jd} model={data.model} />
            <Weights w={weights} setW={setWeights} />
            {data.errors.length > 0 && <div className="alert">Could not read: {data.errors.map((e) => `${e.filename} (${e.error})`).join("; ")}</div>}
            <Table data={{ ...data, candidates: ranked }} onOpen={open} />
          </>
        )}
      </main>
      {drawer && <Drawer key={drawer.id} c={drawer} sid={data.session_id} onClose={() => setDetail(null)} />}
      {showVal && <Validation onClose={() => setShowVal(false)} />}
    </div>
  );
}
