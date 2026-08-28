import { paintLiveBadge } from "/console/assets/console-sections.js";
import { clear, el, pill } from "./render.js";
import { classifyEvent, isFailure } from "./live-kinds.js";

export const MAX_FEED_ERRORS = 3;

const TAB_CAPTIONS = {
  activity: "Every agent, every model call and every screen, in the order they happened.",
  chains:
    "One card per student: the armor screen, the grading call, the evidence check, and where the grade landed.",
  postrun:
    "The span tree persisted to the audit store after the job finished - what ran, how long it took, and what was written.",
};

const TRACE_NOTE =
  "Needs Google Cloud access. Without it, the Post-run trace tab shows the same spans in-product.";

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
  const totals = { calls: 0, tokens: 0, oldest: 0, newest: 0, students: 0, flagged: 0 };
  const students = new Set();
  events.forEach((event) => {
    if (event.kind === "llm_call") {
      totals.calls += 1;
      totals.tokens += (event.llm && Number(event.llm.total_tokens)) || 0;
    }
    if (event.student_id) {
      students.add(event.student_id);
    }
    if (isFailure(event, classifyEvent(event))) {
      totals.flagged += 1;
    }
    const at = Date.parse(event.recorded_at);
    if (Number.isNaN(at)) {
      return;
    }
    totals.oldest = totals.oldest ? Math.min(totals.oldest, at) : at;
    totals.newest = Math.max(totals.newest, at);
  });
  totals.students = students.size;
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

function writeStat(id, value, tone) {
  const node = document.getElementById(id);
  if (!node) {
    return;
  }
  node.textContent = String(value);
  const tile = node.closest(".stat");
  if (!tile) {
    return;
  }
  if (tone) {
    tile.dataset.tone = tone;
  } else {
    delete tile.dataset.tone;
  }
}

function writeTraceNote(visible) {
  const note = document.getElementById("live-trace-note");
  if (!note) {
    return;
  }
  note.textContent = TRACE_NOTE;
  note.hidden = !visible;
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
  writeStat("live-students", totals.students, null);
  writeStat("live-flagged", totals.flagged, totals.flagged ? "danger" : null);
  const running = !state.settled && state.feedTimer !== null;
  dom.livePoll.classList.toggle("is-live", running);
  paintLiveBadge(running);
  dom.liveStatusText.textContent = statusLabel(state);
  dom.liveExport.disabled = !state.events.length;
  dom.liveTraceLink.hidden = !state.cloudTraceUrl;
  writeTraceNote(Boolean(state.cloudTraceUrl));
  if (state.cloudTraceUrl) {
    dom.liveTraceLink.href = state.cloudTraceUrl;
  }
}

export function activateTab(dom, tab) {
  const target = tab || "activity";
  dom.liveTabs.querySelectorAll(".tab-button").forEach((candidate) => {
    candidate.classList.toggle("is-active", candidate.dataset.liveTab === target);
  });
  document.querySelectorAll(".live-tab").forEach((pane) => {
    pane.classList.toggle("is-active", pane.id === `live-tab-${target}`);
  });
  const caption = document.getElementById("live-tab-caption");
  if (caption) {
    caption.textContent = TAB_CAPTIONS[target] || "";
  }
  return target;
}

export function wireChrome(dom, handlers) {
  dom.liveTabs.addEventListener("click", (event) => {
    const button = event.target.closest(".tab-button");
    if (!button) {
      return;
    }
    handlers.onTab(activateTab(dom, button.dataset.liveTab));
  });
  dom.liveExport.addEventListener("click", handlers.onExport);
  activateTab(dom, "activity");
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
