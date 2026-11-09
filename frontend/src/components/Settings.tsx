import { useState } from "react";
import { api } from "../api";
import { loadAi, PROVIDERS, saveAi, type AiSettings } from "../llmKey";

/** AI key settings. Without a key the app still completes every check using its simple rules. */
export function Settings({ onClose }: { onClose: () => void }) {
  const saved = loadAi();
  const [a, setA] = useState<AiSettings>(saved ?? { provider: "groq", base_url: PROVIDERS[0].base_url, model: PROVIDERS[0].model, key: "", remember: false });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (p: Partial<AiSettings>) => { setA({ ...a, ...p }); setMsg(null); };
  const pick = (id: string) => { const p = PROVIDERS.find((x) => x.id === id)!; set({ provider: id, base_url: p.base_url, model: p.model }); };
  const ready = !!(a.key.trim() && a.base_url.trim() && a.model.trim());

  const test = async () => {
    saveAi({ ...a, key: a.key.trim() }); setBusy(true); setMsg(null);
    try { const r = await api.testKey(); setMsg({ ok: r.ok, text: r.ok ? "The key works." : `${r.message} Checks will use the free reader until this is fixed.` }); }
    catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    setBusy(false);
  };

  return (
    <div className="inner">
      <h1>AI key (optional)</h1>
      <p className="lead">Without a key every check still works: the app reads eligibility text with simple rules and writes the standard flag wording. A key lets an AI read harder wording and reword the flag sentences. The AI never produces a number or a trial ID.</p>
      <label className="field card"><span>Provider</span>
        <select value={a.provider} onChange={(e) => pick(e.target.value)}>{PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
      <label className="field card"><span>Provider address (https)</span>
        <input value={a.base_url} disabled={a.provider !== "custom"} placeholder="https://api.example.com/v1" onChange={(e) => set({ base_url: e.target.value })} /></label>
      <label className="field card"><span>Model</span>
        <input value={a.model} onChange={(e) => set({ model: e.target.value })} /></label>
      <label className="field card"><span>API key</span>
        <input type="password" value={a.key} autoComplete="off" placeholder="paste your key" onChange={(e) => set({ key: e.target.value })} /></label>
      <label className="card" style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
        <input type="checkbox" checked={a.remember} onChange={(e) => set({ remember: e.target.checked })} />
        <span>Remember on this device (otherwise it is forgotten when you close this tab)</span></label>
      {msg && <div className={`banner ${msg.ok ? "green" : "amber"}`} role="status">{msg.text}</div>}
      <div className="actions">
        <button className="btn" disabled={!ready || busy} onClick={test}>{busy ? "Testing…" : "Test key"}</button>
        <button className="btn primary" disabled={!ready} onClick={() => { saveAi({ ...a, key: a.key.trim() }); onClose(); }}>Save</button>
        {saved && <button className="btn" onClick={() => { saveAi(null); setA({ ...a, key: "" }); setMsg({ ok: true, text: "Key removed from this browser." }); }}>Remove key</button>}
        <button className="btn" onClick={onClose}>Close</button>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <b>How your key is used</b>
        <ul>
          <li>It is kept in this browser only (this tab, or this device if you tick Remember).</li>
          <li>It is sent over HTTPS with each check, passed to your provider, and used for that check only. The server never stores it or writes it to its logs.</li>
          <li>You pay your provider. A check makes at most 60 AI calls; the result shows how many tokens it used. Set a spend limit on the key at your provider.</li>
          <li>If the key fails, the check carries on with the free reader and says so.</li>
        </ul>
      </div>
    </div>
  );
}
