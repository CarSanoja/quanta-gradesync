import {
  ApiError,
  endpoints,
  getJson,
  getObjectUrl,
  getToken,
  postForm,
  postJson,
  readiness,
  setToken,
} from "./api.js";
import { createChrome, resolveDom } from "./console-dom.js";
import { renderJobDetail, renderJobsList, renderOptimizer } from "./views.js";
import { createReviewController } from "./console-review.js";
import { renderFleet } from "./fleet.js";
import { createIngestController } from "./ingest.js";
import { createSisController } from "./sis.js";
import { createLiveController } from "./live.js";

const dom = resolveDom();
const chrome = createChrome(dom, {
  ApiError,
  getToken,
  setToken,
  onToken: () => refreshAll(),
});
const { guard, toast } = chrome;

const state = { view: "jobs", mode: "", jobs: [], activeJobId: null, jobCache: new Map() };

function setView(view) {
  state.view = view;
  document.querySelectorAll(".rail-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("is-active", section.id === `view-${view}`);
  });
  view === "sis" ? sisController.start() : sisController.stop();
  view === "trace" ? liveController.start() : liveController.stop();
}

async function jobDetailFor(jobId) {
  if (state.jobCache.has(jobId)) {
    return state.jobCache.get(jobId);
  }
  const detail = await guard(() => getJson(endpoints.job(jobId)));
  if (detail) {
    state.jobCache.set(jobId, detail);
  }
  return detail;
}

async function selectJob(jobId) {
  state.activeJobId = jobId;
  const detail = await jobDetailFor(jobId);
  renderJobsList(dom.jobsList, state.jobs, state.activeJobId, selectJob);
  renderJobDetail(dom.jobDetail, detail, openReviewFromJob);
}

async function loadJobs() {
  const payload = await guard(() => getJson(endpoints.jobs()));
  if (!payload) {
    return;
  }
  state.jobs = payload.items;
  state.jobCache.clear();
  dom.jobsCount.textContent = `${payload.count} batch${payload.count === 1 ? "" : "es"}`;
  if (!state.jobs.some((job) => job.job_id === state.activeJobId)) {
    state.activeJobId = state.jobs.length ? state.jobs[0].job_id : null;
  }
  renderJobsList(dom.jobsList, state.jobs, state.activeJobId, selectJob);
  if (state.activeJobId) {
    await selectJob(state.activeJobId);
  } else {
    renderJobDetail(dom.jobDetail, null, openReviewFromJob);
  }
}

async function loadOptimizer() {
  const report = await guard(() => getJson(endpoints.optimizer()));
  if (!report) {
    return;
  }
  dom.cyclesCount.textContent = `${report.cycle_count} cycle${report.cycle_count === 1 ? "" : "s"}`;
  renderOptimizer(dom.optimizerVariants, dom.optimizerCycles, report);
}

async function loadFleet() {
  const report = await guard(() => getJson(endpoints.fleetRegistry()));
  if (!report) {
    return;
  }
  const count = report.summary.agent_count;
  dom.fleetCount.textContent = `${count} agent${count === 1 ? "" : "s"}`;
  renderFleet(dom.fleetSummary, dom.fleetAgents, report);
}

async function loadMode() {
  try {
    const payload = await readiness();
    state.mode = payload.mode;
    dom.modeChip.textContent = `backend: ${payload.mode} · ${payload.status}`;
    dom.modeChip.dataset.tone = payload.status === "ready" ? "ok" : "danger";
  } catch (error) {
    dom.modeChip.textContent = "backend: unreachable";
    dom.modeChip.dataset.tone = "danger";
  }
  ingestController.setMode(state.mode);
}

async function refreshAll() {
  dom.refresh.disabled = true;
  await loadMode();
  await Promise.all([loadJobs(), reviewController.load(), loadOptimizer(), loadFleet()]);
  if (state.view === "sis") {
    await sisController.load();
  }
  if (state.view === "trace") {
    await liveController.load();
  }
  dom.refresh.disabled = false;
}

const sisController = createSisController({ dom, guard, getJson, endpoints });
const liveController = createLiveController({ dom, guard, getJson, endpoints });
const ingestController = createIngestController({
  dom, toast, postForm, postJson, endpoints, guard, onAuthError: chrome.onAuthError,
});
const reviewController = createReviewController({
  dom,
  guard,
  getJson,
  postJson,
  getObjectUrl,
  endpoints,
  toast,
  setView,
  jobDetailFor,
  onDecided: async () => {
    state.jobCache.clear();
    await loadJobs();
  },
});

window.goToMissionControl = (focus) => {
  setView("trace");
  if (typeof liveController.focusLive === "function") {
    liveController.focusLive(focus || {});
  }
};
window.goToSisLedger = (jobId) => {
  sisController.focusJob(jobId);
  setView("sis");
};
window.goToJobsBatch = (jobId) => {
  setView("jobs");
  selectJob(jobId);
};

function openReviewFromJob(reviewId) {
  return reviewController.openFromJob(reviewId);
}

dom.rail.addEventListener("click", (event) => {
  const button = event.target.closest(".rail-item");
  if (button) {
    setView(button.dataset.view);
  }
});

if (dom.queueChip) {
  dom.queueChip.addEventListener("click", () => setView("review"));
}

dom.refresh.addEventListener("click", refreshAll);

async function start() {
  await loadMode();
  if (!getToken()) {
    chrome.openGate("");
    return;
  }
  await refreshAll();
}

start();
