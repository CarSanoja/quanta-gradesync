import { parseLot, prettyName } from "/teacher/assets/teacher-format.js";

const initialRoute = new URLSearchParams(window.location.search);

export function screenFor(route) {
  if (route.has("grades")) {
    return "grades";
  }
  if (route.has("needs")) {
    return "held";
  }
  if (route.has("send")) {
    return "home";
  }
  // A deep link into a batch or an exam keeps resolving on its own; a bare
  // /teacher is someone arriving to send scans, so land them there.
  return route.has("batch") || route.has("review") ? "" : "home";
}

export const state = {
  summary: null,
  records: [],
  batchRecords: [],
  screen: screenFor(initialRoute),
  following: false,
  lotCode: initialRoute.get("batch") || "",
  requestedReview: initialRoute.get("review") || "",
  lastReview: "",
  queries: {
    judgement: "",
    batch_hold: "",
    grades: initialRoute.get("grades") === "1" ? "" : initialRoute.get("grades") || "",
    open_grade: "",
    band: initialRoute.get("show") || "",
  },
  review: { group: "judgement", index: 0, editing: false, marks: null, imageUrl: null, painted: "" },
  open: { student: false, teacher: false },
  uploadDismissed: false,
  startWhenUploaded: false,
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
  if (state.review.group === "history") {
    return summary.history || [];
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
  return batchList().find((entry) => entry.lot_code === first.lot_code)
    || batchList().find((entry) => entry.job_id === first.job_id)
    || activeBatch();
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
  if (batch && batch.settled) {
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
    if (review && review.assessment) {
      return `${review.assessment} · class ${review.class_id}`;
    }
    return review ? prettyName(review.subject) : "";
  }
  const batch = screenBatch(screen);
  const lot = batch ? parseLot(batch.lot_code) : null;
  return lot ? `${lot.subject} · class ${lot.classId}` : "";
}

export function releaseImage() {
  state.review.imageUrl = null;
}
