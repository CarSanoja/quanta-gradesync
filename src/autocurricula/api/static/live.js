import { clear, emptyState } from "./render.js";
import { boardActivity, boardAgents, renderBoard } from "./live-board.js";
import {
  MAX_FEED_ERRORS,
  exportJsonl,
  renderHeader,
  summariseEvents,
  wireChrome,
} from "./live-header.js";
import { renderChains } from "./live-chain.js";
import { renderEventDetail, renderTicker } from "./live-ticker.js";
import { renderTraceDetail, renderTraceJobs } from "./trace.js";

const JOBS_POLL_MS = 2500;
const FEED_POLL_MS = 1500;
const MAX_EVENTS = 3000;
const SETTLED_EMPTY_POLLS = 2;
const TERMINAL_STAGES = new Set(["completed", "failed"]);

const FRESH = {
  events: [], after: 0, selectedSeq: null, settled: false,
  cloudTraceUrl: null, postrunJobId: null, feedErrors: 0, settledEmptyPolls: 0,
};

export function createLiveController({ dom, guard, getJson, endpoints }) {
  const state = {
    ...FRESH,
    jobs: [], activeJobId: null, stage: "", tab: "activity",
    fleet: null, jobsTimer: null, feedTimer: null,
  };

  function safely(target, title, action) {
    try {
      action();
    } catch (error) {
      const reason = error && error.message ? error.message : String(error);
      clear(target).append(emptyState(title, reason));
    }
  }

  function renderAll() {
    const totals = summariseEvents(state.events);
    renderHeader(dom, state, totals);
    const meta = { cloudTraceUrl: state.cloudTraceUrl, jobId: state.activeJobId };
    const selected = state.events.find((event) => event.seq === state.selectedSeq) || null;
    const agents = boardAgents(state.fleet, state.events);
    const activity = boardActivity(state.events, state.settled, totals.newest);
    safely(dom.liveBoard, "Fleet board unavailable", () =>
      renderBoard(dom.liveBoard, agents, activity));
    safely(dom.liveTicker, "Ticker unavailable", () =>
      renderTicker(dom.liveTicker, state.events, state.selectedSeq, selectEvent));
    safely(dom.liveDetail, "Event detail unavailable", () =>
      renderEventDetail(dom.liveDetail, selected, meta));
    if (state.tab === "chains") {
      safely(dom.liveChain, "Reasoning chains unavailable", () =>
        renderChains(dom.liveChain, state.events, meta));
    }
  }

  function stopFeed() {
    window.clearInterval(state.feedTimer);
    state.feedTimer = null;
  }

  function startFeed() {
    stopFeed();
    if (state.activeJobId) {
      state.feedTimer = window.setInterval(pollFeed, FEED_POLL_MS);
      pollFeed();
    }
  }

  async function loadPostrun() {
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
  }

  function syncStage() {
    const job = state.jobs.find((candidate) => candidate.job_id === state.activeJobId);
    state.stage = job ? job.stage : "";
    if (!state.settled && job && TERMINAL_STAGES.has(job.stage)) {
      state.settled = true;
    }
    if (state.settled) {
      loadPostrun();
    }
  }

  async function pollFeed() {
    const jobId = state.activeJobId;
    if (!jobId) {
      return;
    }
    const payload = await guard(() => getJson(endpoints.live(jobId, state.after)));
    if (state.activeJobId !== jobId) {
      return;
    }
    if (!payload) {
      state.feedErrors += 1;
      if (state.feedErrors >= MAX_FEED_ERRORS) {
        stopFeed();
      }
      renderAll();
      return;
    }
    state.feedErrors = 0;
    const events = Array.isArray(payload.events) ? payload.events : [];
    state.events = events.length ? state.events.concat(events).slice(-MAX_EVENTS) : state.events;
    state.after = Number.isFinite(payload.next_after)
      ? payload.next_after
      : events.reduce((highest, event) => Math.max(highest, event.seq || 0), state.after);
    state.cloudTraceUrl = payload.cloud_trace_url || state.cloudTraceUrl;
    state.settled = state.settled || payload.settled === true || TERMINAL_STAGES.has(payload.stage);
    if (state.settled) {
      loadPostrun();
      state.settledEmptyPolls = events.length ? 0 : state.settledEmptyPolls + 1;
      if (state.settledEmptyPolls >= SETTLED_EMPTY_POLLS) {
        stopFeed();
      }
    }
    renderAll();
  }

  function selectJob(jobId) {
    Object.assign(state, FRESH, { events: [], activeJobId: jobId });
    clear(dom.livePostrun).append(emptyState(
      "Waiting for the run to settle",
      "The persisted span tree, metrics and audit tail land here once the job finishes."
    ));
    renderTraceJobs(dom.liveJobs, state.jobs, jobId, selectJob);
    syncStage();
    renderAll();
    startFeed();
  }

  function selectEvent(seq) {
    state.selectedSeq = seq;
    renderAll();
  }

  async function loadFleet() {
    if (state.fleet) {
      return;
    }
    const report = await guard(() => getJson(endpoints.fleetRegistry()));
    state.fleet = report && Array.isArray(report.agents) ? report.agents : null;
  }

  async function pollJobs() {
    const payload = await guard(() => getJson(endpoints.jobs()));
    if (!payload) {
      return;
    }
    state.jobs = payload.items || [];
    if (!state.activeJobId && state.jobs.length) {
      selectJob(state.jobs[0].job_id);
      return;
    }
    renderTraceJobs(dom.liveJobs, state.jobs, state.activeJobId, selectJob);
    syncStage();
    renderAll();
  }

  async function load() {
    await loadFleet();
    await pollJobs();
  }

  function start() {
    window.clearInterval(state.jobsTimer);
    state.jobsTimer = window.setInterval(pollJobs, JOBS_POLL_MS);
    load();
    if (state.activeJobId && state.feedTimer === null && !state.settled) {
      startFeed();
    }
  }

  function stop() {
    window.clearInterval(state.jobsTimer);
    state.jobsTimer = null;
    stopFeed();
    dom.livePoll.classList.remove("is-live");
  }

  wireChrome(dom, {
    onTab: (tab) => {
      state.tab = tab;
      renderAll();
    },
    onExport: () => exportJsonl(state.events, state.activeJobId),
  });

  return { start, stop, load };
}
