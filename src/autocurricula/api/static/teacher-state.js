import { parseLot, prettyName } from "/teacher/assets/teacher-format.js";

export const state = {
  summary: null,
  records: [],
  batchRecords: [],
  screen: "",
  following: false,
  lotCode: new URLSearchParams(window.location.search).get("batch") || "",
  queries: { judgement: "", batch_hold: "", grades: "", open_grade: "" },
  review: { group: "judgement", index: 0, editing: false, marks: null, imageUrl: null, painted: "" },
  open: { student: false, teacher: false },
  uploadDismissed: false,
  failed: false,
  polls: 0,
};

state.following = Boolean(state.lotCode);

export function batchList() {
  return state.summary ? state.summary.batches : [];
}

export function namedBatch() {
  if (!state.lotCode) {
    return null;
  }
  return batchList().find((entry) => entry.lot_code === state.lotCode) || null;
}

export function activeBatch() {
  return namedBatch() || batchList()[0] || null;
}

export function reviewQueue() {
  const summary = state.summary;
  if (!summary) {
    return [];
  }
  const group = state.review.group === "batch_hold" ? summary.batch_hold : summary.judgement;
  return group.items;
}

export function currentReview() {
  const queue = reviewQueue();
  if (!queue.length) {
    return null;
  }
  return queue[Math.min(state.review.index, queue.length - 1)];
}

export function heldBatch() {
  const summary = state.summary;
  const first = summary && summary.waiting.length ? summary.waiting[0] : null;
  if (!first) {
    return activeBatch();
  }
  return batchList().find((entry) => entry.job_id === first.job_id) || activeBatch();
}

export function screenBatch(screen) {
  return screen === "held" ? heldBatch() : activeBatch();
}

export function followJob(jobId) {
  const batch = batchList().find((entry) => entry.job_id === jobId);
  if (batch) {
    state.lotCode = batch.lot_code;
  }
  state.following = true;
}

export function defaultScreen() {
  const summary = state.summary;
  if (!summary) {
    return "home";
  }
  const named = namedBatch();
  if (named && !named.settled) {
    return "grading";
  }
  if (summary.waiting_count > 0) {
    return "held";
  }
  const batch = activeBatch();
  if (batch && batch.settled && state.following) {
    return "settled";
  }
  return "home";
}

export function currentScreen() {
  if (state.screen === "review" && !currentReview()) {
    state.screen = "";
  }
  return state.screen || defaultScreen();
}

export function contextLine(screen) {
  if (screen === "review") {
    const review = currentReview();
    const batch = batchList().find((entry) => review && entry.job_id === review.job_id);
    const named = batch ? parseLot(batch.lot_code) : null;
    if (named) {
      return `${named.subject} · class ${named.classId}`;
    }
    return review ? prettyName(review.subject) : "";
  }
  const batch = screenBatch(screen);
  const lot = batch ? parseLot(batch.lot_code) : null;
  return lot ? `${lot.subject} · class ${lot.classId}` : "";
}

export function releaseImage() {
  if (state.review.imageUrl) {
    URL.revokeObjectURL(state.review.imageUrl);
    state.review.imageUrl = null;
  }
}
