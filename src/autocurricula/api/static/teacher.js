import { getToken } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";
import {
  askRelease, decide, loadBatchRecords, loadRecords, loadSummary, setupActions,
} from "/teacher/assets/teacher-actions.js";
import {
  askCollision, openGate, openZoom, setupDialogs, showAlert, toast, veilKeydown,
} from "/teacher/assets/teacher-dialogs.js";
import { paintDock } from "/teacher/assets/teacher-dock.js";
import { slugify } from "/teacher/assets/teacher-filenames.js";
import { paintRail, paintResume, setupRail } from "/teacher/assets/teacher-rail.js";
import { readAddress, syncAddress } from "/teacher/assets/teacher-routing.js";
import { examCount, plural } from "/teacher/assets/teacher-format.js";
import {
  bumped, decisionButtons, releaseReviewImages, renderReview,
} from "/teacher/assets/teacher-review.js";
import { screenBuilders } from "/teacher/assets/teacher-screens.js";
import {
  activeBatch, contextLine, currentReview, currentScreen, progressSignature, releaseImage,
  reviewQueue, screenBatch, state,
} from "/teacher/assets/teacher-state.js";
import {
  answerPair, renameRow, retryFailed, runQueue, setLotField, setupUploads, stageFiles,
  uploadState, uploads,
} from "/teacher/assets/teacher-upload.js";

const POLL_MS = 6000;
// Polls without any change, not polls in total. A batch can take ten minutes —
// one measured on 2026-08-28 took 640 seconds — and counting total polls made
// the page give up at six, telling her updates had paused while grading was
// still running. As long as a count moves, keep watching.
const IDLE_POLLS_BEFORE_PAUSE = 30;
const builders = screenBuilders();
const screenHost = document.getElementById("screen");
const contextHost = document.getElementById("context-line");
const dockHost = document.getElementById("upload-dock");

let pollTimer = null;
let fileInput = null;
let gradeSearchTimer = null;
let lastWaitingCount = 0;

function openBatch(lotCode) {
  state.lotCode = lotCode;
  state.following = true;
  state.screen = "";
  state.polls = 0;
  syncAddress(true);
  refreshAll();
}

async function openGrade(studentId) {
  state.queries.grades = studentId;
  state.queries.open_grade = studentId;
  state.screen = "grades";
  syncAddress(true);
  await loadRecords(studentId);
  render();
}

function captureFocus() {
  const node = document.activeElement;
  if (!node || !node.id || !screenHost.contains(node)) {
    return null;
  }
  return { id: node.id, spot: typeof node.selectionStart === "number" ? node.selectionStart : null };
}

function restoreFocus(mark) {
  const node = mark ? document.getElementById(mark.id) : null;
  if (!node) {
    return;
  }
  node.focus({ preventScroll: true });
  if (mark.spot !== null && typeof node.setSelectionRange === "function") {
    try {
      node.setSelectionRange(mark.spot, mark.spot);
    } catch (error) {
      node.blur();
      node.focus({ preventScroll: true });
    }
  }
}

function acceptFiles(fileList) {
  state.uploadDismissed = false;
  stageFiles(fileList);
}

function startReview(group, reviewId) {
  const key = group || (state.summary && state.summary.judgement.count ? "judgement" : "batch_hold");
  Object.assign(state.review, { group: key, index: 0, editing: false, marks: null, painted: "" });
  if (reviewId) {
    const index = reviewQueue().findIndex((item) => item.review_id === reviewId);
    state.review.index = index >= 0 ? index : 0;
  }
  if (!currentReview()) {
    return;
  }
  state.screen = "review";
  syncAddress(true);
  render();
}

function leaveReview() {
  releaseImage();
  state.screen = "";
  state.review.painted = "";
  syncAddress(true);
  render();
}

function moveReview(delta) {
  const queue = reviewQueue();
  if (!queue.length) {
    return;
  }
  state.review.index = Math.max(0, Math.min(queue.length - 1, state.review.index + delta));
  Object.assign(state.review, { editing: false, marks: null, painted: "" });
  syncAddress(true);
  render();
}

function finishUploading() {
  state.startWhenUploaded = false;
  state.uploadDismissed = true;
  state.screen = "";
  state.following = true;
  if (uploads.lotCode) {
    state.lotCode = uploads.lotCode;
    syncAddress(true);
  }
  refreshAll();
}

function maybeFinishUploading() {
  if (!state.startWhenUploaded) {
    return false;
  }
  const staged = uploadState();
  if (staged.running || staged.awaitingLot || staged.needsName.length || uploads.pair
      || uploads.rows.some((row) => row.state === "ready")) {
    return false;
  }
  if (staged.failed.length) {
    state.startWhenUploaded = false;
    toast("Some files were not sent. Try those again before you start grading.");
    return false;
  }
  finishUploading();
  return true;
}

function startGrading() {
  const staged = uploadState();
  if (staged.needsName.length || uploads.pair) {
    toast("Some files still need an answer from you before they can be sent.");
    return;
  }
  if (staged.failed.length) {
    toast("Some files were not sent. Try those again before you start grading.");
    return;
  }
  state.startWhenUploaded = true;
  runQueue(true);
  if (!maybeFinishUploading()) {
    render();
  }
}

function screenContext(screen) {
  return {
    summary: state.summary,
    batch: screenBatch(screen),
    records: state.records,
    batchRecords: state.batchRecords,
    queries: state.queries,
    pickFiles: () => fileInput.click(),
    stageFiles: acceptFiles,
    setLot: setLotField,
    renameRow,
    answerPair,
    retryFailed,
    setQuery: (key, value) => {
      state.queries[key] = value;
      if (key === "band") {
        syncAddress(true);
      }
      render();
    },
    setGradeQuery: (value) => {
      state.queries.grades = value;
      syncAddress(false);
      render();
      window.clearTimeout(gradeSearchTimer);
      const query = value;
      gradeSearchTimer = window.setTimeout(async () => {
        await loadRecords(slugify(query), () => state.queries.grades === query);
        render();
      }, 350);
    },
    goHome: () => { state.screen = "home"; syncAddress(true); render(); },
    goGrades: () => { state.screen = "grades"; syncAddress(true); render(); },
    goGrading: startGrading,
    goReview: startReview,
    openBatch,
    openGrade,
    askRelease,
  };
}

function lastViewed() {
  if (!state.lastReview || !state.summary) {
    return null;
  }
  const open = [...state.summary.judgement.items, ...state.summary.batch_hold.items]
    .find((item) => item.review_id === state.lastReview);
  return open || null;
}

function announceWork(waiting) {
  toast(`${examCount(waiting)} ${plural(waiting, "is", "are")} waiting for you.`, {
    tag: "Needs you",
    openLabel: "Open them",
    onOpen: () => {
      state.screen = "held";
      syncAddress(true);
      render();
    },
  });
}

function renderErrorScreen() {
  screenHost.className = "screen";
  screenHost.append(
    el("h1", { class: "display is-small", text: "We could not load your page." }),
    el("p", {
      class: "lede",
      text: "Nothing was lost — grading carries on. Try again, and if it keeps failing, check the "
        + "access code.",
    }),
    el("div", { class: "button-row" }, [
      el("button", { class: "primary", type: "button", text: "Try again", onclick: refreshAll }),
      el("button", { class: "secondary", type: "button", text: "Access code", onclick: () => openGate("") }),
    ])
  );
}

function rememberDisclosures() {
  const student = document.getElementById("disclosure-student");
  const teacher = document.getElementById("disclosure-teacher");
  if (student) {
    state.open.student = student.open;
  }
  if (teacher) {
    state.open.teacher = teacher.open;
  }
}

function toggleEdit() {
  state.review.editing = !state.review.editing;
  state.review.marks = state.review.editing ? {} : null;
  render();
}

function bumpMark(criterion, delta) {
  const marks = state.review.marks || {};
  const held = marks[criterion.criterion_id];
  const current = held === undefined ? criterion.score : held;
  marks[criterion.criterion_id] = bumped(current, delta, criterion.max_score);
  state.review.marks = marks;
  render();
}

function showZoom() {
  const review = currentReview();
  if (!review || !state.review.imageUrl) {
    return;
  }
  openZoom(
    `${review.student_name} — the scanned page, enlarged`,
    state.review.imageUrl,
    `Scanned exam page from ${review.student_name}, enlarged`
  );
}

function paintReview() {
  const review = currentReview();
  const queue = reviewQueue();
  const stamp = `${review.review_id}:${state.review.editing}:${JSON.stringify(state.review.marks)}`;
  if (state.review.painted === stamp) {
    return;
  }
  rememberDisclosures();
  state.review.painted = stamp;
  state.lastReview = review.review_id;
  releaseImage();
  renderReview(screenHost, {
    review,
    position: Math.min(state.review.index + 1, queue.length),
    total: queue.length,
    editing: state.review.editing,
    marks: state.review.marks,
    open: state.open,
    readonly: review.status !== "pending",
    stillOpen: (id) => {
      const open = currentReview();
      return Boolean(open) && open.review_id === id && state.screen === "review";
    },
    onBump: bumpMark,
    onToggleEdit: toggleEdit,
    onAccept: (button) => decide("accept", [button]),
    onDismiss: (button) => decide("dismiss", [button]),
    onLeave: leaveReview,
    onPrevious: () => moveReview(-1),
    onNext: () => moveReview(1),
    onApplyRest: askRelease,
    onZoom: showZoom,
    restHeld: review.group === "batch_hold" && review.status === "pending"
      ? Math.max(0, state.summary.batch_hold.count - 1)
      : 0,
  }).then((url) => {
    if (state.review.painted === stamp) {
      state.review.imageUrl = url;
    }
  });
}

function render() {
  const mark = captureFocus();
  const screen = currentScreen();
  contextHost.textContent = contextLine(screen);
  syncAddress(false);
  if (screen === "review") {
    paintReview();
    paintDock(dockHost, openBatch);
    restoreFocus(mark);
    return;
  }
  state.review.painted = "";
  releaseImage();
  clear(screenHost);
  if (!state.summary) {
    if (state.failed) {
      renderErrorScreen();
    }
    return;
  }
  const waiting = Number(state.summary.waiting_count) || 0;
  paintRail(screen, waiting);
  paintResume(screen === "review" ? null : lastViewed());
  document.title = waiting
    ? `(${waiting}) GradeSync — ${examCount(waiting)} ${plural(waiting, "needs", "need")} you`
    : "GradeSync — Nothing needs you";
  if (waiting > lastWaitingCount) {
    if (document.hidden && "Notification" in window && Notification.permission === "granted") {
      new Notification("GradeSync needs you", {
        body: `${examCount(waiting)} ${plural(waiting, "is", "are")} waiting for your review.`,
      });
    }
    if (lastWaitingCount > 0 || screen !== "held") {
      announceWork(waiting);
    }
  }
  lastWaitingCount = waiting;
  builders[screen](screenHost, screenContext(screen));
  paintDock(dockHost, openBatch);
  restoreFocus(mark);
}

function schedulePoll() {
  window.clearTimeout(pollTimer);
  const batch = activeBatch();
  const busy = (batch && !batch.settled)
    || (state.summary && state.summary.waiting_count > 0)
    || uploads.running;
  if (!busy) {
    return;
  }
  const signature = progressSignature();
  if (signature !== state.pollSignature) {
    state.pollSignature = signature;
    state.polls = 0;
  }
  if (state.polls >= IDLE_POLLS_BEFORE_PAUSE) {
    showAlert("Nothing has changed here for three minutes, so we stopped checking. "
      + "Press Try again to resume.");
    return;
  }
  pollTimer = window.setTimeout(() => {
    state.polls += 1;
    refreshAll();
  }, POLL_MS);
}

async function refreshAll() {
  await loadSummary();
  applyRequestedReview();
  const studentId = state.screen === "grades" ? slugify(state.queries.grades) : "";
  await Promise.all([loadRecords(studentId), loadBatchRecords()]);
  render();
  schedulePoll();
}

function applyRequestedReview() {
  if (!state.requestedReview || !state.summary) {
    return;
  }
  const groups = [
    ["judgement", state.summary.judgement.items],
    ["batch_hold", state.summary.batch_hold.items],
    ["history", state.summary.history || []],
  ];
  for (const [group, items] of groups) {
    const index = items.findIndex((item) => item.review_id === state.requestedReview
      || item.student_id === state.requestedReview);
    if (index >= 0) {
      Object.assign(state.review, { group, index, editing: false, marks: null, painted: "" });
      state.screen = "review";
      if (items[index].lot_code) {
        state.lotCode = items[index].lot_code;
      }
      break;
    }
  }
  state.requestedReview = "";
}

function isTyping(target) {
  if (!target || target === document.body) {
    return false;
  }
  const tag = (target.tagName || "").toLowerCase();
  return target.isContentEditable || tag === "input" || tag === "textarea" || tag === "select";
}

function shortcut(event) {
  if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) {
    return;
  }
  const key = event.key.toLowerCase();
  if ((key !== "a" && key !== "s") || state.screen !== "review" || !currentReview()) {
    return;
  }
  const buttons = decisionButtons(screenHost);
  if (buttons.length < 2 || buttons.some((button) => button.disabled)) {
    return;
  }
  event.preventDefault();
  decide(key === "a" ? "accept" : "dismiss", buttons);
}

function wireFileInput() {
  fileInput = el("input", {
    type: "file",
    multiple: true,
    accept: ".jpg,.jpeg,.png,.pdf,.heic",
    capture: "environment",
    hidden: true,
  });
  document.body.append(fileInput);
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) {
      acceptFiles(fileInput.files);
      fileInput.value = "";
    }
  });
}

// Sending used to take the whole page, so a teacher with three sections had to
// finish one, navigate back and start over. The dock now carries the progress,
// and the page only takes over when the queue genuinely cannot continue without
// an answer from her — which is the same rule the rest of the product follows.
function uploadNeedsHer() {
  const counts = uploadState();
  // awaitingLot is deliberately not here: the drop zone already carries the
  // three fields, so a pile dropped before they are filled is answered where she
  // is standing. Progress is never a reason to move her either — only a question
  // the queue cannot answer itself is.
  return Boolean(uploads.pair)
    || counts.needsName.length > 0
    || counts.held.length > 0
    || counts.failed.length > 0;
}

function onUploadChange() {
  if (maybeFinishUploading()) {
    return;
  }
  if (uploadNeedsHer() && !state.uploadDismissed && state.screen !== "review") {
    state.screen = "uploading";
  }
  render();
  schedulePoll();
}

document.addEventListener("keydown", (event) => {
  if (!veilKeydown(event)) {
    shortcut(event);
  }
});
function goScreen(name) {
  state.screen = name;
  syncAddress(true);
  render();
}

document.getElementById("nav-home").addEventListener("click", () => goScreen("home"));
document.getElementById("nav-grades").addEventListener("click", () => goScreen("grades"));
setupRail({
  onHome: () => goScreen("home"),
  onResume: () => {
    const open = lastViewed();
    if (open) {
      startReview(open.group, open.review_id);
    }
  },
  onNeeds: async () => {
    if ("Notification" in window && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    goScreen("held");
  },
});
window.addEventListener("popstate", () => {
  window.clearTimeout(gradeSearchTimer);
  readAddress();
  refreshAll();
});
window.addEventListener("beforeunload", releaseReviewImages);

setupDialogs({
  slugify,
  onRetry: () => { state.polls = 0; refreshAll(); },
  onToken: refreshAll,
});
setupActions({ refresh: refreshAll });
setupUploads({
  toast,
  openGate,
  askCollision,
  onChange: onUploadChange,
  onBatchSent: (lot) => {
    state.lotCode = lot;
    state.following = true;
    state.polls = 0;
    refreshAll();
  },
});
wireFileInput();

if (!getToken()) {
  openGate("");
} else {
  refreshAll();
}
