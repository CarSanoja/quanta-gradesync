import { clear, emptyState } from "./render.js";
import { boardActivity, boardAgents, renderBoard } from "./live-board.js";
import { renderHeader, summariseEvents } from "./live-header.js";
import { renderChains } from "./live-chain.js";
import { renderEventDetail, renderTicker } from "./live-ticker.js";
import { renderTraceDetail } from "./trace.js";

const DEFAULT_TAB = "activity";
const MAX_EVENTS = 3000;
const TERMINAL_STAGES = new Set(["completed", "failed"]);

export const FRESH = {
  events: [], after: 0, selectedSeq: null, settled: false,
  cloudTraceUrl: null, postrunJobId: null, feedErrors: 0, settledEmptyPolls: 0,
  agentFilter: null, studentFilter: null, jobDetailId: null, students: null,
};

export function isTerminal(stage) {
  return TERMINAL_STAGES.has(stage);
}

export function mergeFeed(state, payload) {
  const events = Array.isArray(payload.events) ? payload.events : [];
  state.events = events.length ? state.events.concat(events).slice(-MAX_EVENTS) : state.events;
  state.after = Number.isFinite(payload.next_after)
    ? payload.next_after
    : events.reduce((highest, event) => Math.max(highest, event.seq || 0), state.after);
  state.cloudTraceUrl = payload.cloud_trace_url || state.cloudTraceUrl;
  return events.length;
}

export function jobsSignature(jobs) {
  return (jobs || [])
    .map((job) => `${job.job_id}:${job.stage}:${job.updated_at}`)
    .join("|");
}

export function jobsChanged(state) {
  const signature = jobsSignature(state.jobs);
  const stale =
    signature !== state.jobsSignature || state.activeJobId !== state.jobsRenderedFor;
  state.jobsSignature = signature;
  return stale;
}

export function focusTab(focus) {
  if (focus.tab) {
    return focus.tab;
  }
  return focus.studentId && !focus.seq ? "chains" : DEFAULT_TAB;
}

export function applyFocus(state, focus) {
  if ("agentId" in focus) {
    state.agentFilter = focus.agentId || null;
  }
  if ("studentId" in focus) {
    state.studentFilter = focus.studentId || null;
  }
  if (focus.seq) {
    state.selectedSeq = focus.seq;
  }
  state.tab = focusTab(focus);
  return state.tab;
}

export function nextPendingFocus(state, limit) {
  const pending = state.pendingFocus;
  if (!pending) {
    return null;
  }
  if (state.jobs.some((job) => job.job_id === pending.jobId)) {
    state.pendingFocus = null;
    return pending;
  }
  state.focusPolls += 1;
  if (state.focusPolls >= limit) {
    state.pendingFocus = null;
  }
  return null;
}

export function matchesFocus(event, filters) {
  const agentFilter = (filters && filters.agentFilter) || null;
  const studentFilter = (filters && filters.studentFilter) || null;
  if (agentFilter && event.agent_id !== agentFilter) {
    return false;
  }
  return !studentFilter || event.student_id === studentFilter;
}

export function safely(target, title, action) {
  try {
    action();
  } catch (error) {
    const reason = error && error.message ? error.message : String(error);
    clear(target).append(emptyState(title, reason));
  }
}

const POSTRUN_TITLE = "Waiting for the run to settle";
const POSTRUN_HINT =
  "The persisted span tree, metrics and audit tail land here once the job finishes.";

export function resetPostrun(dom) {
  clear(dom.livePostrun).append(emptyState(POSTRUN_TITLE, POSTRUN_HINT));
}

export function createPostrunLoader({ dom, state, guard, getJson, endpoints }) {
  return async function loadPostrun() {
    const jobId = state.activeJobId;
    if (!jobId || state.postrunJobId === jobId) {
      return;
    }
    state.postrunJobId = jobId;
    const trace = await guard(() => getJson(endpoints.trace(jobId)));
    if (!trace || trace.job_id !== state.activeJobId) {
      state.postrunJobId = null;
      return;
    }
    safely(dom.livePostrun, "Post-run trace unavailable", () =>
      renderTraceDetail(dom.livePostrun, trace));
  };
}

export function renderPanes(dom, state, handlers) {
  const totals = summariseEvents(state.events);
  renderHeader(dom, state, totals);
  const meta = {
    cloudTraceUrl: state.cloudTraceUrl,
    jobId: state.activeJobId,
    students: state.students,
  };
  const selected = state.events.find((event) => event.seq === state.selectedSeq) || null;
  const board = { agentFilter: state.agentFilter, totals, onPick: handlers.onPickAgent };
  const filters = {
    agentFilter: state.agentFilter,
    studentFilter: state.studentFilter,
    onClearFilter: handlers.onClearFilter,
  };
  safely(dom.liveBoard, "Fleet board unavailable", () => renderBoard(
    dom.liveBoard, boardAgents(state.fleet, state.events),
    boardActivity(state.events, state.settled, totals.newest), board));
  safely(dom.liveTicker, "Ticker unavailable", () => renderTicker(
    dom.liveTicker, state.events, state.selectedSeq, handlers.onSelectEvent, filters));
  safely(dom.liveDetail, "Event detail unavailable", () => renderEventDetail(
    dom.liveDetail, selected, meta));
  if (state.tab === "chains") {
    safely(dom.liveChain, "Reasoning per student unavailable", () => renderChains(
      dom.liveChain, state.events, meta, handlers.onSelectStep));
  }
}

export function filterLabel(filters) {
  const agentFilter = (filters && filters.agentFilter) || "";
  const studentFilter = (filters && filters.studentFilter) || "";
  return [agentFilter, studentFilter].filter(Boolean).join(" · ");
}
