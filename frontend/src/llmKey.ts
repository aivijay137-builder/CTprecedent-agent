// The visitor's own AI key. Lives in the browser only: sessionStorage by default (gone when the tab closes),
// localStorage only if "Remember on this device" is ticked. It is sent as headers with each request and never kept by the server.
export interface AiSettings { provider: string; base_url: string; model: string; key: string; remember: boolean }

export const PROVIDERS = [
  { id: "groq", label: "Groq", base_url: "https://api.groq.com/openai/v1", model: "openai/gpt-oss-120b" },
  { id: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { id: "custom", label: "Other (OpenAI-compatible address)", base_url: "", model: "" },
];
const K = "ctp-ai";

export function loadAi(): AiSettings | null {
  for (const s of [sessionStorage, localStorage]) {
    try { const v = s.getItem(K); if (v) return JSON.parse(v) as AiSettings; } catch { /* storage blocked: act as if nothing is saved */ }
  }
  return null;
}
export function saveAi(a: AiSettings | null) {
  try { sessionStorage.removeItem(K); localStorage.removeItem(K); } catch { /* ignore */ }
  if (!a) return;
  try { (a.remember ? localStorage : sessionStorage).setItem(K, JSON.stringify(a)); } catch { /* ignore */ }
}
export function aiHeaders(): Record<string, string> {
  const a = loadAi();
  return a?.key && a.base_url && a.model ? { "X-LLM-Key": a.key, "X-LLM-Base-URL": a.base_url, "X-LLM-Model": a.model } : {};
}
