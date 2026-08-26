import { renderTraceJobs } from "./trace.js";
import { createStudentLoader } from "./live-students.js";
import { MAX_FEED_ERRORS, activateTab, exportJsonl, wireChrome } from "./live-header.js";
import {
  FRESH, applyFocus, createPostrunLoader, isTerminal, jobsChanged, mergeFeed,
  nextPendingFocus, renderPanes, resetPostrun,
} from "./live-focus.js";

const JOBS_POLL_MS = 2500;
const FEED_POLL_MS = 1500;
const SETTLED_EMPTY_POLLS = 2;
const MAX_FOCUS_POLLS = 10;

export function createLiveController({ dom, guard, getJson, endpoints }) {
  const state = {
    ...FRESH,
    jobs: [], activeJobId: null, stage: "", tab: "activity",
    fleet: null, jobsTimer: null, feedTimer: null,
    jobsSignature: "", jobsRenderedFor: null, pendingFocus: null, focusPolls: 0,
  };

  const handlers = {
    onSelectEvent: (seq) => {
      state.selectedSeq = seq;
      renderAll();
    },
    onPickAgent: (agentId) =>
      focusLive({ agentId: state.agentFilter === agentId ? null : agentId, tab: "activity" }),
    onSelectStep: (seq) => focusLive({ seq, tab: "activity" }),
    onFocusStudent: (studentId) => focusLive({ studentId, tab: "activity" }),
    onClearFilter: () => focusLive({ agentId: null, studentId: null }),
  };

  function renderAll() {
    renderPanes(dom, state, handlers);
  }

  const loadStudents = createStudentLoader({
    state, guard, getJson, endpoints, onLoaded: () => renderAll(),
  });
  const loadPostrun = createPostrunLoader({ dom, state, guard, getJson, endpoints });

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

  function settle() {
    if (state.settled) {
      return;
    }
    state.settled = true;
    state.jobDetailId = null;
    loadStudents();
  }

  function syncStage() {
    const job = state.jobs.find((candidate) => candidate.job_id === state.activeJobId);
    state.stage = job ? job.stage : "";
    if (job && isTerminal(job.stage)) {
      settle();
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
    const arrived = mergeFeed(state, payload);
    if (payload.settled === true || isTerminal(payload.stage)) {
      settle();
    }
    if (state.settled) {
      loadPostrun();
      state.settledEmptyPolls = arrived ? 0 : state.settledEmptyPolls + 1;
      if (state.settledEmptyPolls >= SETTLED_EMPTY_POLLS) {
        stopFeed();
      }
    }
    renderAll();
  }

  function selectJob(jobId, keepFocus) {
    const kept = keepFocus === true
      ? { agentFilter: state.agentFilter, studentFilter: state.studentFilter }
      : {};
    Object.assign(state, FRESH, { events: [], activeJobId: jobId }, kept);
    resetPostrun(dom);
    state.jobsRenderedFor = jobId;
    renderTraceJobs(dom.liveJobs, state.jobs, jobId, selectJob);
    syncStage();
    loadStudents();
    renderAll();
    startFeed();
  }

  function focusLive(focus) {
    const request = focus || {};
    if (request.jobId && request.jobId !== state.activeJobId) {
      if (!state.jobs.some((job) => job.job_id === request.jobId)) {
        state.pendingFocus = request;
        state.focusPolls = 0;
        return;
      }
      selectJob(request.jobId);
    }
    applyFocus(state, request);
    activateTab(dom, state.tab);
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
    const stale = jobsChanged(state);
    const pending = nextPendingFocus(state, MAX_FOCUS_POLLS);
    if (pending) {
      focusLive(pending);
      return;
    }
    if (!state.activeJobId && state.jobs.length) {
      selectJob(state.jobs[0].job_id, true);
      return;
    }
    if (!stale) {
      return;
    }
    state.jobsRenderedFor = state.activeJobId;
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

  resetPostrun(dom);
  wireChrome(dom, {
    onTab: (tab) => {
      state.tab = tab;
      renderAll();
    },
    onExport: () => exportJsonl(state.events, state.activeJobId),
  });

  return { start, stop, load, focusLive };
}
