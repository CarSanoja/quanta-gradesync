import { ApiError, endpoints, getJson, getToken, postJson, setToken } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";
import { prettyName, setupUploads, showProgress, veils, escapeVeil } from "/teacher/assets/teacher-upload.js";
import { detailButtons, prettySubject, renderDetail, timeAgo } from "/teacher/assets/teacher-detail.js";
import { heroNote, renderCounts, renderIdle } from "/teacher/assets/teacher-stage.js";
import { releaseLabel, releaseMessage, renderGroup } from "/teacher/assets/teacher-triage.js";

const SUMMARY_PATH = "/teacher/summary";
const POLL_MS = 6000;
const MAX_POLLS = 40;

const dom = {};
[
  "refresh-button", "access-button", "hero-note", "count-strip", "count-waiting", "count-synced",
  "count-grading", "count-time", "triage", "judgement-card", "judgement-count", "judgement-note",
  "judgement-stack", "judgement-reasons", "judgement-start", "judgement-hint", "judgement-finder",
  "judgement-search", "judgement-list", "judgement-more", "judgement-empty", "hold-card",
  "hold-count", "hold-note", "hold-stack", "hold-reasons", "hold-release", "hold-hint",
  "hold-finder", "hold-search", "hold-list", "hold-more", "hold-empty", "review-section",
  "review-detail", "guided-panel", "guided-progress", "guided-flash", "guided-exit", "guided-body",
  "stage-idle", "stage-idle-line", "stage-idle-hint", "stage-brief",
  "all-done", "all-done-note", "synced-tools", "synced-search", "synced-count", "synced-list",
  "access-veil", "access-form", "access-input", "access-error", "access-cancel", "release-veil",
  "release-title", "release-message", "release-error", "release-cancel", "release-confirm", "toast",
].forEach((id) => {
  dom[id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = document.getElementById(id);
});

const counts = {
  strip: dom.countStrip, waiting: dom.countWaiting, synced: dom.countSynced,
  grading: dom.countGrading, time: dom.countTime,
};

const idle = {
  panel: dom.stageIdle, line: dom.stageIdleLine, hint: dom.stageIdleHint,
  brief: dom.stageBrief,
};

const groups = {
  judgement: {
    card: dom.judgementCard, count: dom.judgementCount, note: dom.judgementNote,
    stack: dom.judgementStack, reasons: dom.judgementReasons, action: dom.judgementStart,
    hint: dom.judgementHint, finder: dom.judgementFinder, search: dom.judgementSearch,
    list: dom.judgementList, more: dom.judgementMore, empty: dom.judgementEmpty,
  },
  batch_hold: {
    card: dom.holdCard, count: dom.holdCount, note: dom.holdNote, stack: dom.holdStack,
    reasons: dom.holdReasons, action: dom.holdRelease, hint: dom.holdHint,
    finder: dom.holdFinder, search: dom.holdSearch, list: dom.holdList, more: dom.holdMore,
    empty: dom.holdEmpty,
  },
};

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const scrollMode = () => (reducedMotion.matches ? "auto" : "smooth");

const state = { summary: null, byId: new Map(), synced: [], openId: null, imageUrl: null };
const guided = { active: false, group: "judgement", queue: [], done: 0, total: 0, approved: 0, sentBack: 0, flash: "" };
const watch = { lotCode: new URLSearchParams(window.location.search).get("batch") || "", timer: null, polls: 0 };
let toastTimer = null;
let releasing = false;

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

function releaseImage() {
  if (state.imageUrl) {
    URL.revokeObjectURL(state.imageUrl);
    state.imageUrl = null;
  }
}

function group(key) {
  const summary = state.summary;
  if (!summary) {
    return { key, count: 0, items: [], reasons: [], note: "", empty_note: "" };
  }
  return key === "judgement" ? summary.judgement : summary.batch_hold;
}

function renderCountStrip() {
  renderCounts(counts, state.summary, state.synced.length);
}

function handlers() {
  return { onOpen: toggleReview, isOpen: (id) => state.openId === id };
}

function renderStage() {
  const summary = state.summary;
  const waiting = summary ? summary.waiting_count : 0;
  renderIdle(idle, summary, !guided.active && !state.openId && waiting > 0);
}

function renderTriage() {
  const summary = state.summary;
  if (!summary) {
    return;
  }
  const nothingWaiting = summary.waiting_count === 0;
  document.body.dataset.guided = guided.active ? "on" : "off";
  dom.triage.hidden = nothingWaiting;
  dom.allDone.hidden = guided.active || !nothingWaiting;
  dom.heroNote.textContent = heroNote(summary);
  dom.heroNote.hidden = !summary.waiting_count;
  renderStage();
  if (dom.triage.hidden) {
    return;
  }
  const judged = group("judgement");
  const held = group("batch_hold");
  dom.judgementHint.textContent = judged.count > 1
    ? `We walk you through the ${judged.count} one at a time — page, quote, proposed grade.`
    : "The page, the quoted line and the proposed grade, side by side.";
  dom.holdRelease.textContent = releaseLabel(held.count);
  dom.holdHint.textContent = "One decision, one confirmation. Nothing from the other group can ride along.";
  renderGroup(groups.judgement, judged, dom.judgementSearch.value, handlers());
  renderGroup(groups.batch_hold, held, dom.holdSearch.value, handlers());
  if (guided.active) {
    groups[guided.group].action.hidden = true;
  }
}

async function openDetail(review, host, scroll) {
  releaseImage();
  state.imageUrl = await renderDetail(review, host, {
    onDecide: decide,
    isOpen: (id) => state.openId === id,
    scroll,
  });
}

function closeDetail() {
  releaseImage();
  state.openId = null;
  dom.reviewDetail.hidden = true;
  clear(dom.reviewDetail);
  renderTriage();
}

async function toggleReview(reviewId) {
  const review = state.byId.get(reviewId);
  if (!review) {
    return;
  }
  if (guided.active) {
    if (review.group === guided.group) {
      await jumpGuided(reviewId);
      return;
    }
    exitGuided();
  }
  if (state.openId === reviewId) {
    closeDetail();
    return;
  }
  state.openId = reviewId;
  renderTriage();
  await openDetail(review, dom.reviewDetail, scrollMode());
}

function groupItems(key) {
  return group(key).items;
}

function nextGuidedReview() {
  const available = new Map(groupItems(guided.group).map((item) => [item.review_id, item]));
  const queued = guided.queue.find((id) => available.has(id));
  if (queued) {
    return available.get(queued);
  }
  const extra = [...available.values()].filter((item) => !guided.queue.includes(item.review_id));
  if (!extra.length) {
    return null;
  }
  extra.forEach((item) => guided.queue.push(item.review_id));
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
        ? "Nothing else is waiting for you here."
        : `${guided.approved} went to the gradebook, ${guided.sentBack} came back to you to grade by hand.`,
    }),
    el("button", { class: "quiet", type: "button", text: "Back to the triage", onclick: exitGuided }),
  ]));
}

function guidedStale() {
  return !dom.guidedBody.childElementCount || !state.byId.has(state.openId);
}

async function jumpGuided(reviewId) {
  if (state.openId === reviewId) {
    return;
  }
  const at = guided.queue.indexOf(reviewId);
  if (at > 0) {
    guided.queue.splice(at, 1);
  }
  if (at !== 0) {
    guided.queue.unshift(reviewId);
    guided.total = Math.max(guided.total, guided.queue.length);
  }
  await renderGuided();
}

async function renderGuided() {
  dom.guidedPanel.hidden = false;
  dom.reviewDetail.hidden = true;
  dom.allDone.hidden = true;
  dom.stageIdle.hidden = true;
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
  renderTriage();
  await openDetail(review, dom.guidedBody, null);
}

function startGuided(key) {
  const items = groupItems(key);
  if (!items.length || (guided.active && guided.group === key)) {
    return;
  }
  Object.assign(guided, {
    active: true,
    group: key,
    queue: items.map((item) => item.review_id),
    total: items.length,
    done: 0,
    approved: 0,
    sentBack: 0,
    flash: "",
  });
  releaseImage();
  state.openId = null;
  dom.reviewDetail.hidden = true;
  clear(dom.reviewDetail);
  renderTriage();
  dom.guidedPanel.scrollIntoView({ behavior: scrollMode(), block: "nearest" });
  renderGuided();
}

function exitGuided() {
  guided.active = false;
  guided.flash = "";
  releaseImage();
  state.openId = null;
  dom.guidedPanel.hidden = true;
  clear(dom.guidedBody);
  renderTriage();
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
    : `${review.student_name}'s exam came back to you — no grade was recorded.`;
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

function openReleaseSheet() {
  const held = group("batch_hold");
  if (!held.count) {
    return;
  }
  dom.releaseTitle.textContent = held.count === 1
    ? "Release this grade to the gradebook?"
    : `Release ${held.count} grades to the gradebook?`;
  dom.releaseMessage.textContent = releaseMessage(held.count);
  dom.releaseConfirm.textContent = releaseLabel(held.count);
  dom.releaseError.hidden = true;
  dom.releaseError.textContent = "";
  dom.releaseVeil.hidden = false;
  dom.releaseConfirm.focus();
}

function closeReleaseSheet() {
  dom.releaseVeil.hidden = true;
}

function refusalNote(error) {
  const refused = error.body && Array.isArray(error.body.refused) ? error.body.refused : [];
  if (!refused.length) {
    return error.message;
  }
  const names = refused.map((entry) => prettyName(entry.student_id || entry.review_id));
  return `Nothing was released. ${names.join(", ")} need your judgement — review them one at a time.`;
}

async function confirmRelease() {
  if (releasing) {
    return;
  }
  const held = group("batch_hold");
  const ids = held.items.map((item) => item.review_id);
  if (!ids.length) {
    closeReleaseSheet();
    return;
  }
  releasing = true;
  dom.releaseConfirm.disabled = true;
  dom.releaseCancel.disabled = true;
  try {
    const result = await postJson(endpoints.bulkApprove(), { review_ids: ids });
    closeReleaseSheet();
    const count = result.released_count;
    const failed = (result.failed || []).length;
    const done = count === 1 ? "1 grade is in the gradebook." : `${count} grades are in the gradebook.`;
    toast(failed
      ? `${done} ${failed} could not be written and are still waiting — try again.`
      : done);
    await refreshAll();
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      closeReleaseSheet();
      openGate("That access code didn't work. Check it and try again.");
    } else {
      dom.releaseError.textContent = error instanceof ApiError ? refusalNote(error) : error.message;
      dom.releaseError.hidden = false;
    }
  } finally {
    releasing = false;
    dom.releaseConfirm.disabled = false;
    dom.releaseCancel.disabled = false;
  }
}

async function loadSummary() {
  const path = watch.lotCode ? `${SUMMARY_PATH}?batch=${encodeURIComponent(watch.lotCode)}` : SUMMARY_PATH;
  const summary = await guard(() => getJson(path));
  if (!summary) {
    dom.heroNote.textContent = "The review queue couldn't load. Press Refresh to try again.";
    dom.heroNote.hidden = false;
    return;
  }
  state.summary = summary;
  state.byId = new Map(summary.waiting.map((item) => [item.review_id, item]));
  if (state.openId && !state.byId.has(state.openId) && !guided.active) {
    closeDetail();
  }
  renderCountStrip();
  renderTriage();
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
  const collected = new Map();
  records.forEach((record) => {
    const title = groupTitle(record);
    collected.set(title, collected.get(title) || []);
    collected.get(title).push(record);
  });
  return [...collected.entries()];
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
  const collected = groupRecords(matches);
  collected.forEach(([title, records]) => {
    if (collected.length > 1) {
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
  renderCountStrip();
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
  dom.reviewSection.scrollIntoView({ behavior: scrollMode(), block: "start" });
}

function activeVeil() {
  return [...veils(), dom.accessVeil, dom.releaseVeil].find((veil) => !veil.hidden) || null;
}

function isTyping(target) {
  if (!target || target === document.body) {
    return false;
  }
  const tag = (target.tagName || "").toLowerCase();
  return target.isContentEditable || tag === "input" || tag === "textarea" || tag === "select";
}

function openDecisionHost() {
  if (guided.active && !dom.guidedPanel.hidden) {
    return dom.guidedBody;
  }
  if (state.openId && !dom.reviewDetail.hidden) {
    return dom.reviewDetail;
  }
  return null;
}

function shortcut(event) {
  if (event.metaKey || event.ctrlKey || event.altKey || activeVeil() || isTyping(event.target)) {
    return;
  }
  const key = event.key.toLowerCase();
  if (key !== "a" && key !== "s") {
    return;
  }
  const host = openDecisionHost();
  if (!host) {
    return;
  }
  const review = state.byId.get(state.openId);
  const buttons = detailButtons(host);
  if (!review || buttons.length < 2 || buttons.some((button) => button.disabled)) {
    return;
  }
  event.preventDefault();
  decide(review, key === "a" ? "approve" : "dismiss", buttons);
}

document.addEventListener("keydown", (event) => {
  const veil = activeVeil();
  if (!veil) {
    shortcut(event);
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    if (veil === dom.accessVeil) {
      dom.accessVeil.hidden = true;
    } else if (veil === dom.releaseVeil) {
      closeReleaseSheet();
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

dom.judgementStart.addEventListener("click", () => startGuided("judgement"));
dom.holdRelease.addEventListener("click", openReleaseSheet);
dom.releaseCancel.addEventListener("click", closeReleaseSheet);
dom.releaseConfirm.addEventListener("click", confirmRelease);
dom.judgementSearch.addEventListener("input", renderTriage);
dom.holdSearch.addEventListener("input", renderTriage);
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
