import { ApiError, endpoints, getJson, getObjectUrl, getToken, postForm, postJson, setToken } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";

const SUMMARY_PATH = "/teacher/summary";
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ALLOWED_SUFFIXES = new Set([".jpg", ".jpeg", ".png", ".pdf", ".heic"]);

const dom = {};
[
  "refresh-button", "access-button", "hero-note", "review-cards", "review-detail",
  "all-done", "all-done-note", "subject-input", "class-input", "assessment-input",
  "dropzone", "upload-log", "synced-list", "collision-veil", "collision-message",
  "collision-name-input", "collision-error", "collision-cancel", "collision-different",
  "collision-replace", "pages-veil", "pages-message", "pages-groups", "pages-separate",
  "pages-combine", "access-veil", "access-form", "access-input", "access-error",
  "access-cancel", "toast",
].forEach((id) => {
  dom[id.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = document.getElementById(id);
});

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const fileInput = el("input", { type: "file", multiple: true, accept: ".jpg,.jpeg,.png,.pdf,.heic", hidden: true });
document.body.append(fileInput);

const state = { reviews: [], openId: null, imageUrl: null, uploads: [] };
let toastTimer = null;
let collisionResolver = null;
let pagesResolver = null;

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

function prettyName(studentId) {
  return String(studentId)
    .split(/[-_.]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
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

async function renderDetail(review) {
  releaseImage();
  clear(dom.reviewDetail);
  dom.reviewDetail.hidden = false;
  const { side, frame } = scanSide(review);
  dom.reviewDetail.append(
    el("div", { class: "detail-head" }, [
      el("h2", { text: review.student_name }),
      el("span", { class: "context", text: `${prettySubject(review.subject)} · waiting ${timeAgo(review.waiting_since)}` }),
    ]),
    el("div", { class: "detail-grid" }, [side, decisionSide(review)])
  );
  dom.reviewDetail.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "nearest" });
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
  await renderDetail(review);
}

async function decide(review, action, buttons) {
  buttons.forEach((button) => { button.disabled = true; });
  const path = action === "approve" ? endpoints.approve(review.review_id) : endpoints.dismiss(review.review_id);
  const decided = await guard(() => postJson(path));
  buttons.forEach((button) => { button.disabled = false; });
  if (!decided) {
    return;
  }
  toast(action === "approve"
    ? `${review.student_name}'s grade is approved — it's in the gradebook.`
    : `${review.student_name}'s exam was sent back — no grade was recorded.`);
  closeDetail();
  await refreshAll();
}

async function loadSummary() {
  const summary = await guard(() => getJson(SUMMARY_PATH));
  if (!summary) {
    dom.heroNote.textContent = "The review queue couldn't load. Press Refresh to try again.";
    dom.heroNote.hidden = false;
    return;
  }
  state.reviews = summary.waiting;
  const hasWork = summary.waiting_count > 0;
  dom.heroNote.textContent = heroNote(summary.waiting_count);
  dom.heroNote.hidden = !hasWork;
  dom.allDone.hidden = hasWork;
  dom.reviewCards.hidden = !hasWork;
  if (!hasWork || !state.reviews.some((review) => review.review_id === state.openId)) {
    closeDetail();
  }
  renderCards();
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

async function loadSynced() {
  const payload = await guard(() => getJson(endpoints.sisRecords()));
  if (!payload) {
    return;
  }
  clear(dom.syncedList);
  if (!payload.items.length) {
    dom.syncedList.append(el("p", { class: "synced-empty", text: "No grades synced yet. They appear here the moment grading finishes." }));
  } else {
    payload.items.forEach((record) => dom.syncedList.append(syncedRow(record)));
  }
  dom.allDoneNote.textContent = payload.count
    ? `${payload.count} grade${payload.count === 1 ? "" : "s"} synced recently.`
    : "Upload scans below to get started.";
}

function lotPart(value) {
  return value.trim().replace(/[^A-Za-z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}

function composeLotCode() {
  const fields = [dom.subjectInput, dom.classInput, dom.assessmentInput];
  const parts = fields.map((field) => lotPart(field.value));
  const missing = fields[parts.indexOf("")];
  if (missing) {
    toast("Fill in the subject, class and assessment name first.");
    missing.focus();
    return null;
  }
  return `${new Date().getFullYear()}_${parts.join("_")}`;
}

function fileStem(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

const PAGE_MARKER = /^(.+?)[\s._-]*(?:p|pg|page)[\s._-]*(\d{1,3})$/i;
const COPY_MARKER = /^(.+?)\s*\((\d{1,3})\)$/;
const BARE_NUMBER = /^(.+?)[\s._-]+(\d{1,3})$/;

function pageSignal(stem) {
  for (const [pattern, explicit] of [[PAGE_MARKER, true], [COPY_MARKER, false], [BARE_NUMBER, false]]) {
    const match = stem.match(pattern);
    if (match) {
      const base = match[1].replace(/[\s._-]+$/, "");
      if (base) {
        return { base, explicit };
      }
    }
  }
  return null;
}

function detectPageGroups(names) {
  const entries = names.map((name) => ({ name, stem: fileStem(name), signal: pageSignal(fileStem(name)) }));
  const byBase = new Map();
  entries.forEach((entry) => {
    if (entry.signal) {
      const key = entry.signal.base.toLowerCase();
      byBase.set(key, byBase.get(key) || []);
      byBase.get(key).push(entry);
    }
  });
  entries.forEach((entry) => {
    if (!entry.signal && byBase.has(entry.stem.toLowerCase())) {
      byBase.get(entry.stem.toLowerCase()).push(entry);
    }
  });
  const groups = [];
  byBase.forEach((members) => {
    if (members.length >= 2 || members.some((member) => member.signal.explicit)) {
      groups.push(members.map((member) => member.name));
    }
  });
  return groups;
}

function paintUploads() {
  clear(dom.uploadLog);
  state.uploads.slice().reverse().forEach((item) => {
    const name = el("div", { class: "upload-name" }, [el("span", { class: "file", text: item.label })]);
    if (item.student) {
      name.append(el("span", { class: "as" }, ["appears in the gradebook as ", el("strong", { text: item.student })]));
    } else if (item.note) {
      name.append(el("span", { class: "as", text: item.note }));
    }
    dom.uploadLog.append(el("li", { "data-tone": item.tone }, [
      name,
      el("span", { class: "status", text: item.status }),
    ]));
  });
}

function askPages(groups) {
  clear(dom.pagesGroups);
  groups.forEach((names) => {
    dom.pagesGroups.append(el("li", {}, [
      el("span", { class: "files", text: names.join("  +  ") }),
      el("span", {
        class: "becomes",
        text: `would sync as ${names.map((name) => `“${prettyName(fileStem(name))}”`).join(", ")}`,
      }),
    ]));
  });
  const single = groups.length === 1 && groups[0].length === 1;
  dom.pagesMessage.textContent = single
    ? "This file name ends in a page number, so it looks like one page of a longer exam:"
    : "These files differ only by a page number. Each file becomes its own student in the gradebook:";
  dom.pagesVeil.hidden = false;
  dom.pagesCombine.focus();
  return new Promise((resolve) => { pagesResolver = resolve; });
}

function settlePages(action) {
  if (pagesResolver) {
    dom.pagesVeil.hidden = true;
    pagesResolver(action);
    pagesResolver = null;
    dom.dropzone.focus({ preventScroll: true });
  }
}

function askCollision(fileName) {
  dom.collisionMessage.textContent =
    `There's already a scan saved for ${fileStem(fileName)} in this assessment. ` +
    "You can replace it, or save this one under a different student.";
  dom.collisionNameInput.hidden = true;
  dom.collisionNameInput.value = "";
  dom.collisionError.hidden = true;
  dom.collisionDifferent.textContent = "This is a different student";
  dom.collisionVeil.hidden = false;
  dom.collisionCancel.focus();
  return new Promise((resolve) => { collisionResolver = resolve; });
}

function settleCollision(result) {
  if (collisionResolver) {
    dom.collisionVeil.hidden = true;
    collisionResolver(result);
    collisionResolver = null;
    dom.dropzone.focus({ preventScroll: true });
  }
}

async function uploadOne(item, file, lotCode) {
  let mode = "new";
  let newName = "";
  for (;;) {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("lot_code", lotCode);
    form.append("mode", mode);
    if (newName) {
      form.append("new_student_name", newName);
    }
    const result = await postForm(endpoints.ingestExam(), form);
    if (result.status === 401 || result.status === 403) {
      item.status = "needs the access code";
      item.tone = "bad";
      openGate("That access code didn't work. Check it and try again.");
      return;
    }
    if (result.ok) {
      item.status = mode === "replace" ? "replaced" : "received";
      item.tone = "good";
      return;
    }
    if (result.status === 409 && result.body && result.body.collision) {
      item.status = "already has a scan";
      paintUploads();
      const decision = await askCollision(file.name);
      if (decision.action === "cancel") {
        item.status = "kept the existing scan";
        return;
      }
      mode = decision.action;
      newName = decision.name || "";
      if (newName) {
        item.student = prettyName(newName);
      }
      continue;
    }
    item.status = result.body && result.body.detail ? String(result.body.detail) : "couldn't upload";
    item.tone = "bad";
    return;
  }
}

async function handleFiles(fileList) {
  const lotCode = composeLotCode();
  if (!lotCode) {
    return;
  }
  const files = Array.from(fileList);
  const heldBack = new Set();
  const groups = detectPageGroups(files.map((file) => file.name));
  if (groups.length) {
    const action = await askPages(groups);
    if (action === "combine") {
      groups.flat().forEach((name) => heldBack.add(name));
    }
  }
  for (const file of files) {
    const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const item = { label: file.name, status: "sending…", tone: "", note: "", student: "" };
    state.uploads.push(item);
    if (heldBack.has(file.name)) {
      item.status = "held back";
      item.note = "Combine the pages into one PDF, then upload that single file.";
    } else if (!ALLOWED_SUFFIXES.has(suffix)) {
      item.status = "not a photo or PDF";
      item.tone = "bad";
    } else if (file.size > MAX_UPLOAD_BYTES) {
      item.status = "over the 20 MB limit";
      item.tone = "bad";
    } else {
      item.student = prettyName(fileStem(file.name));
      paintUploads();
      await uploadOne(item, file, lotCode);
    }
    paintUploads();
  }
}

async function refreshAll() {
  dom.refreshButton.disabled = true;
  await Promise.all([loadSummary(), loadSynced()]);
  dom.refreshButton.disabled = false;
}

dom.collisionCancel.addEventListener("click", () => settleCollision({ action: "cancel" }));
dom.collisionReplace.addEventListener("click", () => settleCollision({ action: "replace" }));
dom.collisionDifferent.addEventListener("click", () => {
  if (dom.collisionNameInput.hidden) {
    dom.collisionNameInput.hidden = false;
    dom.collisionDifferent.textContent = "Save under this name";
    dom.collisionNameInput.focus();
    return;
  }
  const name = dom.collisionNameInput.value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name)) {
    dom.collisionError.textContent = "Use letters, digits, dots or dashes for the student name.";
    dom.collisionError.hidden = false;
    return;
  }
  settleCollision({ action: "rename", name });
});

dom.pagesCombine.addEventListener("click", () => settlePages("combine"));
dom.pagesSeparate.addEventListener("click", () => settlePages("separate"));

function activeVeil() {
  return [dom.collisionVeil, dom.pagesVeil, dom.accessVeil].find((veil) => !veil.hidden) || null;
}

document.addEventListener("keydown", (event) => {
  const veil = activeVeil();
  if (!veil) {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    if (veil === dom.collisionVeil) {
      settleCollision({ action: "cancel" });
    } else if (veil === dom.pagesVeil) {
      settlePages("combine");
    } else {
      dom.accessVeil.hidden = true;
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

dom.dropzone.addEventListener("click", () => fileInput.click());
dom.dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) {
    handleFiles(fileInput.files);
    fileInput.value = "";
  }
});
["dragenter", "dragover"].forEach((name) =>
  dom.dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dom.dropzone.classList.add("is-dragover");
  })
);
["dragleave", "drop"].forEach((name) =>
  dom.dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dom.dropzone.classList.remove("is-dragover");
  })
);
dom.dropzone.addEventListener("drop", (event) => {
  if (event.dataTransfer && event.dataTransfer.files.length) {
    handleFiles(event.dataTransfer.files);
  }
});

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
