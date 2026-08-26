import { clear, el, pill } from "./render.js";

export const MAX_FEED_ERRORS = 3;

function elapsedLabel(oldest, newest, settled) {
  if (!oldest) {
    return "—";
  }
  const end = settled ? newest : Math.max(newest, Date.now());
  const seconds = Math.max(0, (end - oldest) / 1000);
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  return `${Math.floor(seconds / 60)}m ${String(Math.floor(seconds % 60)).padStart(2, "0")}s`;
}

export function summariseEvents(events) {
  const totals = { calls: 0, tokens: 0, oldest: 0, newest: 0 };
  events.forEach((event) => {
    if (event.kind === "llm_call") {
      totals.calls += 1;
      totals.tokens += (event.llm && Number(event.llm.total_tokens)) || 0;
    }
    const at = Date.parse(event.recorded_at);
    if (Number.isNaN(at)) {
      return;
    }
    totals.oldest = totals.oldest ? Math.min(totals.oldest, at) : at;
    totals.newest = Math.max(totals.newest, at);
  });
  return totals;
}

function statusLabel(state) {
  if (!state.activeJobId) {
    return "no job selected";
  }
  if (state.feedErrors >= MAX_FEED_ERRORS) {
    return "live feed unavailable";
  }
  return state.settled ? `settled · ${state.stage || "done"}` : "live";
}

export function renderHeader(dom, state, totals) {
  const job = state.jobs.find((candidate) => candidate.job_id === state.activeJobId);
  clear(dom.liveStageTrack);
  (job && job.stages ? job.stages : []).forEach((stage) => {
    dom.liveStageTrack.append(pill(`${stage.name} · ${stage.status}`, stage.status));
  });
  dom.liveElapsed.textContent = elapsedLabel(totals.oldest, totals.newest, state.settled);
  dom.liveCalls.textContent = String(totals.calls);
  dom.liveTokens.textContent = totals.tokens.toLocaleString();
  dom.liveEventsCount.textContent = String(state.events.length);
  dom.livePoll.classList.toggle("is-live", !state.settled && state.feedTimer !== null);
  dom.liveStatusText.textContent = statusLabel(state);
  dom.liveTraceLink.hidden = !state.cloudTraceUrl;
  if (state.cloudTraceUrl) {
    dom.liveTraceLink.href = state.cloudTraceUrl;
  }
}

export function wireChrome(dom, handlers) {
  dom.liveTabs.addEventListener("click", (event) => {
    const button = event.target.closest(".tab-button");
    if (!button) {
      return;
    }
    const tab = button.dataset.liveTab;
    dom.liveTabs.querySelectorAll(".tab-button").forEach((candidate) => {
      candidate.classList.toggle("is-active", candidate === button);
    });
    document.querySelectorAll(".live-tab").forEach((pane) => {
      pane.classList.toggle("is-active", pane.id === `live-tab-${tab}`);
    });
    handlers.onTab(tab);
  });
  dom.liveExport.addEventListener("click", handlers.onExport);
}

export function exportJsonl(events, jobId) {
  const lines = events.map((event) => JSON.stringify(event)).join("\n");
  const blob = new Blob([lines ? `${lines}\n` : ""], { type: "application/x-ndjson" });
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: `${jobId || "live"}-live.jsonl` });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
