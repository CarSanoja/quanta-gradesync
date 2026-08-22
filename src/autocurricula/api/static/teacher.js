import { getToken } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";
import {
  askRelease, decide, loadBatchRecords, loadRecords, loadSummary, setupActions,
} from "/teacher/assets/teacher-actions.js";
import {
  askCollision, openGate, openZoom, setupDialogs, toast, veilKeydown,
} from "/teacher/assets/teacher-dialogs.js";
import { slugify } from "/teacher/assets/teacher-filenames.js";
import { bumped, decisionButtons, renderReview } from "/teacher/assets/teacher-review.js";
import { screenBuilders } from "/teacher/assets/teacher-screens.js";
import {
  activeBatch, contextLine, currentReview, currentScreen, releaseImage, reviewQueue, screenBatch,
  state,
} from "/teacher/assets/teacher-state.js";
import {
  answerPair, renameRow, retryFailed, runQueue, setLotField, setupUploads, stageFiles,
  uploadState, uploads,
} from "/teacher/assets/teacher-upload.js";

const POLL_MS = 6000;
const MAX_POLLS = 60;
const builders = screenBuilders();
const screenHost = document.getElementById("screen");
const contextHost = document.getElementById("context-line");

let pollTimer = null;
let fileInput = null;

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

function startReview(group) {
  const key = group || (state.summary && state.summary.judgement.count ? "judgement" : "batch_hold");
  Object.assign(state.review, { group: key, index: 0, editing: false, marks: null, painted: "" });
  if (!currentReview()) {
    return;
  }
  state.screen = "review";
  render();
}

function leaveReview() {
  releaseImage();
  state.screen = "";
  state.review.painted = "";
  render();
}

function startGrading() {
  const staged = uploadState();
  if (staged.needsName.length || uploads.pair) {
    toast("Some files still need an answer from you before they can be sent.");
    return;
  }
  state.uploadDismissed = true;
  state.screen = "";
  state.following = true;
  if (uploads.lotCode) {
    state.lotCode = uploads.lotCode;
  }
  runQueue(true);
  refreshAll();
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
    setQuery: (key, value) => { state.queries[key] = value; render(); },
    goHome: () => { state.screen = "home"; render(); },
    goGrades: () => { state.screen = "grades"; render(); },
    goGrading: startGrading,
    goReview: startReview,
    askRelease,
  };
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
  releaseImage();
  renderReview(screenHost, {
    review,
    position: Math.min(state.review.index + 1, queue.length),
    total: queue.length,
    editing: state.review.editing,
    marks: state.review.marks,
    open: state.open,
    stillOpen: (id) => {
      const open = currentReview();
      return Boolean(open) && open.review_id === id && state.screen === "review";
    },
    onBump: bumpMark,
    onToggleEdit: toggleEdit,
    onAccept: (button) => decide("accept", [button]),
    onDismiss: (button) => decide("dismiss", [button]),
    onLeave: leaveReview,
    onZoom: showZoom,
  }).then((url) => {
    if (state.review.painted === stamp) {
      state.review.imageUrl = url;
    } else if (url) {
      URL.revokeObjectURL(url);
    }
  });
}

function render() {
  const mark = captureFocus();
  const screen = currentScreen();
  contextHost.textContent = contextLine(screen);
  if (screen === "review") {
    paintReview();
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
  builders[screen](screenHost, screenContext(screen));
  restoreFocus(mark);
}

function schedulePoll() {
  window.clearTimeout(pollTimer);
  const batch = activeBatch();
  const busy = (batch && !batch.settled) || uploads.running;
  if (!busy || state.polls >= MAX_POLLS) {
    return;
  }
  pollTimer = window.setTimeout(() => {
    state.polls += 1;
    refreshAll();
  }, POLL_MS);
}

async function refreshAll() {
  await loadSummary();
  await Promise.all([loadRecords(), loadBatchRecords()]);
  render();
  schedulePoll();
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

function onUploadChange() {
  if (uploadState().total && !state.uploadDismissed && state.screen !== "review") {
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
document.getElementById("nav-home").addEventListener("click", () => {
  state.screen = "home";
  render();
});
document.getElementById("nav-grades").addEventListener("click", () => {
  state.screen = "grades";
  render();
});

setupDialogs({ slugify, onRetry: refreshAll, onToken: refreshAll });
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
