import {
  ApiError,
  endpoints,
  getJson,
  getObjectUrl,
  getToken,
  postJson,
  readiness,
  setToken,
} from "./api.js";
import { clear, emptyState } from "./render.js";
import {
  renderJobDetail,
  renderJobsList,
  renderOptimizer,
  renderReviewDetail,
  renderReviewList,
} from "./views.js";

const dom = {
  rail: document.getElementById("rail"),
  modeChip: document.getElementById("mode-chip"),
  queueChip: document.getElementById("queue-chip"),
  refresh: document.getElementById("refresh-button"),
  tokenButton: document.getElementById("token-button"),
  gate: document.getElementById("token-gate"),
  tokenForm: document.getElementById("token-form"),
  tokenInput: document.getElementById("token-input"),
  tokenCancel: document.getElementById("token-cancel"),
  tokenError: document.getElementById("token-error"),
  toast: document.getElementById("toast"),
  jobsList: document.getElementById("jobs-list"),
  jobsCount: document.getElementById("jobs-count"),
  jobDetail: document.getElementById("job-detail"),
  reviewList: document.getElementById("review-list"),
  reviewCount: document.getElementById("review-count"),
  reviewDetail: document.getElementById("review-detail"),
  optimizerVariants: document.getElementById("optimizer-variants"),
  optimizerCycles: document.getElementById("optimizer-cycles"),
  cyclesCount: document.getElementById("cycles-count"),
};

const state = {
  view: "jobs",
  jobs: [],
  activeJobId: null,
  jobDetail: null,
  jobCache: new Map(),
  reviews: [],
  activeReviewId: null,
  reviewContext: { item: null, criteria: [], imageUrl: null },
};

let toastTimer = null;

function toast(message, tone) {
  dom.toast.textContent = message;
  dom.toast.dataset.tone = tone || "neutral";
  dom.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    dom.toast.hidden = true;
  }, 4000);
}

function openGate(message) {
  dom.tokenError.textContent = message || "";
  dom.tokenError.hidden = !message;
  dom.tokenInput.value = getToken();
  dom.gate.hidden = false;
  dom.tokenInput.focus();
}

async function guard(action) {
  try {
    return await action();
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      openGate("The API rejected that token. Paste the deployment token to continue.");
      return null;
    }
    toast(error.message, "danger");
    return null;
  }
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".rail-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("is-active", section.id === `view-${view}`);
  });
}

function releaseImage() {
  if (state.reviewContext.imageUrl) {
    URL.revokeObjectURL(state.reviewContext.imageUrl);
  }
  state.reviewContext.imageUrl = null;
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
  state.jobDetail = await jobDetailFor(jobId);
  renderJobsList(dom.jobsList, state.jobs, state.activeJobId, selectJob);
  renderJobDetail(dom.jobDetail, state.jobDetail, openReviewFromJob);
}

async function loadJobs() {
  const payload = await guard(() => getJson(endpoints.jobs()));
  if (!payload) {
    return;
  }
  state.jobs = payload.items;
  state.jobCache.clear();
  dom.jobsCount.textContent = `${payload.count} batch${payload.count === 1 ? "" : "es"}`;
  const stillListed = state.jobs.some((job) => job.job_id === state.activeJobId);
  if (!stillListed) {
    state.activeJobId = state.jobs.length ? state.jobs[0].job_id : null;
  }
  renderJobsList(dom.jobsList, state.jobs, state.activeJobId, selectJob);
  if (state.activeJobId) {
    await selectJob(state.activeJobId);
  } else {
    renderJobDetail(dom.jobDetail, null, openReviewFromJob);
  }
}

async function selectReview(reviewId) {
  const item = state.reviews.find((candidate) => candidate.review_id === reviewId);
  releaseImage();
  state.activeReviewId = reviewId;
  state.reviewContext = { item: item || null, criteria: [], imageUrl: null };
  renderReviewList(dom.reviewList, state.reviews, state.activeReviewId, selectReview);
  renderReviewDetail(dom.reviewDetail, state.reviewContext, reviewHandlers);
  if (!item) {
    return;
  }
  const detail = await jobDetailFor(item.job_id);
  const student = detail
    ? detail.students.find((candidate) => candidate.student_id === item.student_id)
    : null;
  state.reviewContext.criteria = student ? student.criteria : [];
  if (item.document_paths.length) {
    try {
      state.reviewContext.imageUrl = await getObjectUrl(endpoints.pageImage(reviewId, 0));
    } catch (error) {
      state.reviewContext.imageUrl = null;
    }
  }
  if (state.activeReviewId === reviewId) {
    renderReviewDetail(dom.reviewDetail, state.reviewContext, reviewHandlers);
  }
}

async function loadReviews() {
  const payload = await guard(() => getJson(endpoints.pending()));
  if (!payload) {
    return;
  }
  state.reviews = payload.items;
  dom.reviewCount.textContent = `${payload.count} item${payload.count === 1 ? "" : "s"}`;
  dom.queueChip.textContent = `queue: ${payload.count} pending`;
  dom.queueChip.dataset.tone = payload.count ? "warn" : "ok";
  const stillPending = state.reviews.some((item) => item.review_id === state.activeReviewId);
  const nextId = stillPending
    ? state.activeReviewId
    : state.reviews.length
      ? state.reviews[0].review_id
      : null;
  renderReviewList(dom.reviewList, state.reviews, nextId, selectReview);
  if (nextId) {
    await selectReview(nextId);
  } else {
    releaseImage();
    state.activeReviewId = null;
    state.reviewContext = { item: null, criteria: [], imageUrl: null };
    clear(dom.reviewDetail).append(
      emptyState("Queue is clear", "Nothing is waiting for a teacher decision.")
    );
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

async function decide(reviewId, endpoint, verb) {
  const decided = await guard(() => postJson(endpoint(reviewId)));
  if (!decided) {
    return;
  }
  toast(`${decided.student_id} ${verb}.`, "neutral");
  state.jobCache.clear();
  await Promise.all([loadReviews(), loadJobs()]);
}

const reviewHandlers = {
  onApprove: (reviewId) => decide(reviewId, endpoints.approve, "approved and written to the SIS"),
  onDismiss: (reviewId) => decide(reviewId, endpoints.dismiss, "dismissed without a SIS write"),
};

async function openReviewFromJob(reviewId) {
  setView("review");
  const pending = state.reviews.some((item) => item.review_id === reviewId);
  if (!pending) {
    await loadReviews();
  }
  if (state.reviews.some((item) => item.review_id === reviewId)) {
    await selectReview(reviewId);
  } else {
    toast("That record is no longer pending review.", "neutral");
  }
}

async function loadMode() {
  try {
    const payload = await readiness();
    dom.modeChip.textContent = `backend: ${payload.mode} · ${payload.status}`;
    dom.modeChip.dataset.tone = payload.status === "ready" ? "ok" : "danger";
  } catch (error) {
    dom.modeChip.textContent = "backend: unreachable";
    dom.modeChip.dataset.tone = "danger";
  }
}

async function refreshAll() {
  dom.refresh.disabled = true;
  await loadMode();
  await Promise.all([loadJobs(), loadReviews(), loadOptimizer()]);
  dom.refresh.disabled = false;
}

dom.rail.addEventListener("click", (event) => {
  const button = event.target.closest(".rail-item");
  if (button) {
    setView(button.dataset.view);
  }
});

dom.refresh.addEventListener("click", refreshAll);
dom.tokenButton.addEventListener("click", () => openGate(""));
dom.tokenCancel.addEventListener("click", () => {
  dom.gate.hidden = true;
});

dom.tokenForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = dom.tokenInput.value.trim();
  if (!value) {
    dom.tokenError.textContent = "A bearer token is required.";
    dom.tokenError.hidden = false;
    return;
  }
  setToken(value);
  dom.gate.hidden = true;
  await refreshAll();
});

async function start() {
  await loadMode();
  if (!getToken()) {
    openGate("");
    return;
  }
  await refreshAll();
}

start();
