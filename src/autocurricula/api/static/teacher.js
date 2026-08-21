import { ApiError, endpoints, getJson, getObjectUrl, getToken, postJson, setToken } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";
import { prettyName, setupUploads, showProgress, veils, escapeVeil } from "/teacher/assets/teacher-upload.js";

const SUMMARY_PATH = "/teacher/summary";
const POLL_MS = 6000;
const MAX_POLLS = 40;

const dom = {};
[
  "refresh-button", "access-button", "hero-note", "hero-actions", "guided-start", "guided-note",
  "review-section", "review-cards", "review-detail", "guided-panel", "guided-progress",
  "guided-flash", "guided-exit", "guided-body", "all-done", "all-done-note", "synced-tools",
  "synced-search", "synced-count", "synced-list", "access-veil", "access-form", "access-input",
  "access-error", "access-cancel", "toast",
].forEach((id) => {
  dom[id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = document.getElementById(id);
});

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const state = { reviews: [], synced: [], openId: null, imageUrl: null };
const guided = { active: false, queue: [], done: 0, total: 0, approved: 0, sentBack: 0, flash: "" };
const watch = { lotCode: "", timer: null, polls: 0 };
let toastTimer = null;

function toast(message) {
  dom.toast.textContent = message;
  dom.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { dom.toast.hidden = true; }, 4200);
}

function openGate(message) {
  dom.accessError.textContent = message || "";
  dom.accessError.hidden = !message;
  dom.accessInput.value = getToken();
  dom.accessVeil.hidden = false;
  dom.accessInput.focus();
}

async function guard(action) {
  try {
    return await action();
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      openGate("That access code didn't work. Check it and try again.");
      return null;
    }
    toast(error.message);
    return null;
  }
}

function prettySubject(subject) {
  const plain = String(subject).replace(/[-_]+/g, " ");
  return plain ? plain[0].toUpperCase() + plain.slice(1) : subject;
}

function timeAgo(value) {
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) {
    return "";
  }
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "an hour ago" : `${hours} hours ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function releaseImage() {
  if (state.imageUrl) {
    URL.revokeObjectURL(state.imageUrl);
    state.imageUrl = null;
  }
}

function heroNote(count) {
  if (!count) return "";
  const lead = count === 1 ? "One exam needs a quick human look" : `${count} exams need a quick human look`;
  return `${lead} before the grades go out. Everything else is already in the gradebook.`;
}

function renderCards() {
  clear(dom.reviewCards);
  state.reviews.forEach((review) => {
    const isOpen = review.review_id === state.openId;
    dom.reviewCards.append(
      el("button", {
        type: "button",
        class: `exam-card${isOpen ? " is-open" : ""}`,
        "aria-expanded": isOpen ? "true" : "false",
        onclick: () => toggleReview(review.review_id),
      }, [
        el("span", { class: "student", text: review.student_name }),
        el("span", { class: "context", text: `${prettySubject(review.subject)} · waiting ${timeAgo(review.waiting_since)}` }),
        el("span", { class: "peek", text: review.reasons[0] }),
      ])
    );
  });
}

function scanSide(review) {
  const frame = el("div", { class: "scan-frame" }, [
    el("div", { class: "scan-missing", text: "Loading the scanned page…" }),
  ]);
  const flags = el("ul", { class: "evidence-stack" }, review.evidence.map((span) =>
    el("li", { class: "evidence-flag" }, [
      el("span", { class: "page-tab", text: `Page ${span.page}` }),
      el("q", { text: span.quote }),
      el("span", { class: "note", text: span.note }),
    ])
  ));
  const side = el("div", { class: "scan-side" }, [
    frame,
    review.evidence.length ? flags : null,
    el("p", { class: "scan-caption", text: "The scanned page, exactly as it was uploaded. Quotes below are the grader's evidence." }),
  ]);
  return { side, frame };
}

function decisionSide(review) {
  const grades = review.criteria.length
    ? el("ul", { class: "grade-lines" }, review.criteria.map((criterion) =>
        el("li", {}, [
          el("div", { class: "grade-line-top" }, [
            el("span", { class: "title", text: criterion.title }),
            el("span", { class: "points", text: criterion.score_text }),
          ]),
          el("p", { class: "comment", text: criterion.comment }),
        ])
      ))
    : el("p", { class: "feedback", text: "The grade breakdown isn't available for this exam." });
  const approve = el("button", { class: "primary", type: "button", text: "Approve grade" });
  const sendBack = el("button", { class: "send-back", type: "button", text: "Send back" });
  approve.addEventListener("click", () => decide(review, "approve", [approve, sendBack]));
  sendBack.addEventListener("click", () => decide(review, "dismiss", [approve, sendBack]));
  return el("div", { class: "decision-side" }, [
    el("h3", { text: "Why it needs you" }),
    el("ul", { class: "reason-list" }, review.reasons.map((reason) => el("li", { text: reason }))),
    el("h3", { text: "The proposed grade" }),
    grades,
    el("div", { class: "grade-total" }, [
      el("span", { class: "points", text: review.score_text }),
      el("span", { class: "percent", text: `${Math.round(review.percentage)}%` }),
    ]),
    el("h3", { text: "Feedback for the student" }),
    el("p", { class: "feedback", text: review.feedback }),
    el("div", { class: "decision-actions" }, [approve, sendBack]),
    el("p", { class: "decision-hint", text: "Approve puts this grade in the gradebook. Send back records no grade, so you can grade this exam yourself." }),
  ]);
}

async function renderDetail(review, host) {
  releaseImage();
  clear(host);
  host.hidden = false;
  const { side, frame } = scanSide(review);
  host.append(
    el("div", { class: "detail-head" }, [
      el("h2", { text: review.student_name }),
      el("span", { class: "context", text: `${prettySubject(review.subject)} · waiting ${timeAgo(review.waiting_since)}` }),
    ]),
    el("div", { class: "detail-grid" }, [side, decisionSide(review)])
  );
  if (!guided.active) {
    host.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "nearest" });
  }
  if (!review.has_page) {
    clear(frame).append(el("div", { class: "scan-missing", text: "No scan is attached to this exam." }));
    return;
  }
  try {
    state.imageUrl = await getObjectUrl(endpoints.pageImage(review.review_id, 0));
    if (state.openId === review.review_id) {
      clear(frame).append(el("img", { src: state.imageUrl, alt: `Scanned exam page from ${review.student_name}` }));
    }
  } catch (error) {
    clear(frame).append(el("div", { class: "scan-missing", text: "The scan couldn't be loaded right now." }));
  }
}

function closeDetail() {
  releaseImage();
  state.openId = null;
  dom.reviewDetail.hidden = true;
  clear(dom.reviewDetail);
  renderCards();
}

async function toggleReview(reviewId) {
  if (state.openId === reviewId) {
    closeDetail();
    return;
  }
  const review = state.reviews.find((candidate) => candidate.review_id === reviewId);
  if (!review) {
    return;
  }
  state.openId = reviewId;
  renderCards();
  await renderDetail(review, dom.reviewDetail);
}

function nextGuidedReview() {
  const byId = new Map(state.reviews.map((review) => [review.review_id, review]));
  const queued = guided.queue.find((id) => byId.has(id));
  if (queued) {
    return byId.get(queued);
  }
  const extra = state.reviews.filter((review) => !guided.queue.includes(review.review_id));
  if (!extra.length) {
    return null;
  }
  extra.forEach((review) => guided.queue.push(review.review_id));
  guided.total = guided.queue.length;
  return extra[0];
}

function guidedDone() {
  clear(dom.guidedBody);
  dom.guidedProgress.textContent = `${guided.total} of ${guided.total} reviewed`;
  dom.guidedFlash.hidden = true;
  const clean = guided.sentBack === 0;
  dom.guidedBody.append(el("div", { class: "all-done" }, [
    el("div", { class: "all-done-mark", "aria-hidden": "true", text: "✓" }),
    el("h2", {
      text: clean
        ? `All ${guided.total} reviewed — everything is in the gradebook.`
        : `All ${guided.total} reviewed — you're done.`,
    }),
    el("p", {
      text: clean
        ? "Nothing else is waiting for you."
        : `${guided.approved} went to the gradebook, ${guided.sentBack} came back to you to grade by hand.`,
    }),
    el("button", { class: "quiet", type: "button", text: "Back to the list", onclick: exitGuided }),
  ]));
}

function guidedStale() {
  return !dom.guidedBody.childElementCount
    || !state.reviews.some((review) => review.review_id === state.openId);
}

async function renderGuided() {
  dom.guidedPanel.hidden = false;
  dom.reviewCards.hidden = true;
  dom.heroActions.hidden = true;
  dom.reviewDetail.hidden = true;
  const review = nextGuidedReview();
  dom.guidedFlash.textContent = guided.flash;
  dom.guidedFlash.hidden = !guided.flash;
  if (!review) {
    if (!dom.guidedBody.querySelector(".all-done")) {
      guidedDone();
    }
    return;
  }
  state.openId = review.review_id;
  dom.guidedProgress.textContent = `Exam ${Math.min(guided.done + 1, guided.total)} of ${guided.total}`;
  await renderDetail(review, dom.guidedBody);
}

function startGuided() {
  Object.assign(guided, {
    active: true,
    queue: state.reviews.map((review) => review.review_id),
    total: state.reviews.length,
    done: 0,
    approved: 0,
    sentBack: 0,
    flash: "",
  });
  closeDetail();
  dom.guidedPanel.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "start" });
  renderGuided();
}

function exitGuided() {
  guided.active = false;
  guided.flash = "";
  releaseImage();
  state.openId = null;
  dom.guidedPanel.hidden = true;
  clear(dom.guidedBody);
  renderQueue();
}

async function decide(review, action, buttons) {
  buttons.forEach((button) => { button.disabled = true; });
  const path = action === "approve" ? endpoints.approve(review.review_id) : endpoints.dismiss(review.review_id);
  const decided = await guard(() => postJson(path));
  buttons.forEach((button) => { button.disabled = false; });
  if (!decided) {
    return;
  }
  const message = action === "approve"
    ? `${review.student_name}'s grade is approved — it's in the gradebook.`
    : `${review.student_name}'s exam was sent back — no grade was recorded.`;
  toast(message);
  if (guided.active) {
    guided.done += 1;
    guided[action === "approve" ? "approved" : "sentBack"] += 1;
    guided.flash = message;
    releaseImage();
    await refreshAll();
    return;
  }
  closeDetail();
  await refreshAll();
}

function renderQueue() {
  const count = state.reviews.length;
  dom.heroNote.textContent = heroNote(count);
  dom.heroNote.hidden = !count;
  dom.allDone.hidden = Boolean(count) || guided.active;
  dom.reviewCards.hidden = !count || guided.active;
  dom.heroActions.hidden = count < 2 || guided.active;
  dom.guidedNote.textContent = count > 1
    ? `We walk you through the ${count} exams one at a time, or pick one from the list below.`
    : "";
  renderCards();
}

async function loadSummary() {
  const path = watch.lotCode ? `${SUMMARY_PATH}?batch=${encodeURIComponent(watch.lotCode)}` : SUMMARY_PATH;
  const summary = await guard(() => getJson(path));
  if (!summary) {
    dom.heroNote.textContent = "The review queue couldn't load. Press Refresh to try again.";
    dom.heroNote.hidden = false;
    return;
  }
  state.reviews = summary.waiting;
  if (!state.reviews.some((review) => review.review_id === state.openId) && !guided.active) {
    closeDetail();
  }
  renderQueue();
  if (guided.active && guidedStale()) {
    await renderGuided();
  }
  showProgress(summary.batch);
  if (summary.batch && !summary.batch.settled && watch.polls < MAX_POLLS) {
    scheduleWatch();
  } else {
    window.clearTimeout(watch.timer);
  }
}

function syncedRow(record) {
  return el("div", { class: "synced-row" }, [
    el("span", { class: "student", text: prettyName(record.student_id) }),
    el("span", { class: "leader" }),
    el("span", { class: "grade", text: record.total_score === null ? "graded" : `${record.total_score} points` }),
    el("span", { class: "percent", text: record.percentage === null ? "" : `${Math.round(record.percentage)}%` }),
    el("span", { class: "when", text: timeAgo(record.written_at) }),
  ]);
}

function groupTitle(record) {
  const assessment = record.term ? prettyName(record.term) : "";
  return [prettySubject(record.subject), assessment].filter(Boolean).join(" · ") || "Recent grades";
}

function groupRecords(records) {
  const groups = new Map();
  records.forEach((record) => {
    const title = groupTitle(record);
    groups.set(title, groups.get(title) || []);
    groups.get(title).push(record);
  });
  return [...groups.entries()];
}

function renderSynced() {
  const query = dom.syncedSearch.value.trim().toLowerCase();
  const matches = state.synced.filter((record) =>
    !query || prettyName(record.student_id).toLowerCase().includes(query));
  clear(dom.syncedList);
  dom.syncedTools.hidden = state.synced.length < 2;
  dom.syncedCount.textContent = query
    ? `${matches.length} of ${state.synced.length} shown`
    : `${state.synced.length} grade${state.synced.length === 1 ? "" : "s"}`;
  if (!state.synced.length) {
    dom.syncedList.append(el("p", { class: "synced-empty", text: "No grades synced yet. They appear here the moment grading finishes." }));
    return;
  }
  if (!matches.length) {
    dom.syncedList.append(el("p", { class: "synced-empty", text: `No student here matches “${dom.syncedSearch.value.trim()}”.` }));
    return;
  }
  const groups = groupRecords(matches);
  groups.forEach(([title, records]) => {
    if (groups.length > 1) {
      dom.syncedList.append(el("h3", { class: "synced-group" }, [
        el("span", { text: title }),
        el("span", { class: "synced-group-count", text: `${records.length}` }),
      ]));
    }
    records.forEach((record) => dom.syncedList.append(syncedRow(record)));
  });
}

async function loadSynced() {
  const payload = await guard(() => getJson(endpoints.sisRecords()));
  if (!payload) {
    return;
  }
  state.synced = payload.items;
  renderSynced();
  dom.allDoneNote.textContent = payload.count
    ? `${payload.count} grade${payload.count === 1 ? "" : "s"} synced recently.`
    : "Upload scans below to get started.";
}

async function refreshAll() {
  dom.refreshButton.disabled = true;
  await Promise.all([loadSummary(), loadSynced()]);
  dom.refreshButton.disabled = false;
}

function scheduleWatch() {
  window.clearTimeout(watch.timer);
  watch.timer = window.setTimeout(() => {
    watch.polls += 1;
    refreshAll();
  }, POLL_MS);
}

function startBatchWatch(lotCode) {
  watch.lotCode = lotCode;
  watch.polls = 0;
  refreshAll();
}

function goToReview() {
  dom.reviewSection.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "start" });
}

function activeVeil() {
  return [...veils(), dom.accessVeil].find((veil) => !veil.hidden) || null;
}

document.addEventListener("keydown", (event) => {
  const veil = activeVeil();
  if (!veil) {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    if (veil === dom.accessVeil) {
      dom.accessVeil.hidden = true;
    } else {
      escapeVeil(veil);
    }
    return;
  }
  if (event.key === "Tab") {
    const focusables = [...veil.querySelectorAll("button, input")]
      .filter((node) => !node.hidden && !node.disabled);
    if (!focusables.length) {
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const inside = veil.contains(document.activeElement);
    if (event.shiftKey && (document.activeElement === first || !inside)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !inside)) {
      event.preventDefault();
      first.focus();
    }
  }
});

setupUploads({ toast, openGate, onBatchSent: startBatchWatch, goToReview });

dom.guidedStart.addEventListener("click", startGuided);
dom.guidedExit.addEventListener("click", exitGuided);
dom.syncedSearch.addEventListener("input", renderSynced);
dom.refreshButton.addEventListener("click", refreshAll);
dom.accessButton.addEventListener("click", () => openGate(""));
dom.accessCancel.addEventListener("click", () => { dom.accessVeil.hidden = true; });
dom.accessForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = dom.accessInput.value.trim();
  if (!value) {
    dom.accessError.textContent = "Enter your access code to continue.";
    dom.accessError.hidden = false;
    return;
  }
  setToken(value);
  dom.accessVeil.hidden = true;
  await refreshAll();
});

if (!getToken()) {
  openGate("");
} else {
  refreshAll();
}
