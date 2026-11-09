// The live progress stream from the API. (The demo build swaps this file for src/demo/source.ts.)
export const openEvents = (runId: string): EventSource => new EventSource(`${import.meta.env.VITE_API_URL ?? ""}/api/runs/${runId}/events`);
