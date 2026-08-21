import { endpoints, postForm } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ALLOWED_SUFFIXES = new Set([".jpg", ".jpeg", ".png", ".pdf", ".heic"]);
const COLLAPSE_AFTER = 8;
const RENAME_IDLE_MS = 1200;
const STUDENT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

const CAMERA_PATTERNS = [
  /^(img|dsc|dscn|dscf|pxl|photo|image|foto|scan|mvimg)[\s._-]*\d/i,
  /^whats\s?app[\s._-]*image/i,
  /^screen\s?shot/i,
  /^\d+$/,
  /^[^a-z]+$/i,
];

const PAGE_MARKER = /^(.+?)[\s._-]*(?:p|pg|page)[\s._-]*(\d{1,3})$/i;
const COPY_MARKER = /^(.+?)\s*\((\d{1,3})\)$/;
const BARE_NUMBER = /^(.+?)[\s._-]+(\d{1,3})$/;

const ATTENTION = new Set(["needs-name", "failed", "held"]);
const LOCKED = new Set(["sending", "received", "skipped"]);
const SENT = new Set(["received", "failed", "skipped"]);

const FAILURE_COPY = [
  [/is empty/i, "this file has nothing in it"],
  [/exceeds the/i, "this file is too big"],
  [/not gradable/i, "not a photo or PDF"],
  [/already holds/i, "this assessment is full — start a new one"],
];
const NEEDS_NAME_DETAIL = /student id|student name|new_student_name/i;

const CHIPS = [
  { key: "sending", label: "sending" },
  { key: "received", label: "received" },
  { key: "needs-name", label: "needs a name" },
  { key: "held", label: "held back" },
  { key: "failed", label: "didn't go through" },
];

const dom = {};
const rows = [];
const view = { filter: "", expanded: false, running: false, lotCode: "", awaitingLot: false };

let hooks = {};
let fileInput = null;
let collisionResolver = null;
let pagesResolver = null;
let renameTimer = null;
let nextRowId = 0;

function bind(ids) {
  ids.forEach((id) => {
    dom[id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = document.getElementById(id);
  });
}

export function prettyName(studentId) {
  return String(studentId)
    .split(/[-_.]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function fileStem(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

function fileSuffix(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

function slugify(value) {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "");
}

function looksLikeCamera(stem) {
  const candidate = stem.trim();
  return CAMERA_PATTERNS.some((pattern) => pattern.test(candidate));
}

function lotPart(value) {
  return value.trim().replace(/[^A-Za-z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}

function composeLotCode(announce) {
  const fields = [dom.subjectInput, dom.classInput, dom.assessmentInput];
  const parts = fields.map((field) => lotPart(field.value));
  const missing = fields[parts.indexOf("")];
  if (missing) {
    if (announce) {
      hooks.toast("Fill in the subject, class and assessment name first.");
      missing.focus();
    }
    return null;
  }
  return `${new Date().getFullYear()}_${parts.join("_")}`;
}

function assessmentLabel() {
  const typed = dom.assessmentInput.value.trim();
  return typed || "This batch";
}

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

function counts() {
  const tally = { sending: 0, received: 0, "needs-name": 0, held: 0, failed: 0, skipped: 0, ready: 0 };
  rows.forEach((row) => { tally[row.state] = (tally[row.state] || 0) + 1; });
  return tally;
}

function sendTarget() {
  return rows.filter((row) => row.state !== "held" && row.state !== "needs-name").length;
}

function sentCount() {
  return rows.filter((row) => SENT.has(row.state)).length;
}

function releaseThumb(row) {
  if (row.thumbUrl) {
    URL.revokeObjectURL(row.thumbUrl);
    row.thumbUrl = "";
    if (row.thumbNode) {
      row.thumbNode.remove();
      row.thumbNode = null;
    }
  }
}

function failureCopy(detail) {
  const hit = FAILURE_COPY.find(([pattern]) => pattern.test(detail));
  return hit ? hit[1] : "we couldn't send this one";
}

function paintRow(row) {
  if (row.state !== "needs-name") {
    releaseThumb(row);
  }
  row.node.setAttribute("data-state", row.state);
  row.node.setAttribute("data-tone", row.tone || "");
  row.statusNode.textContent = row.status;
  clear(row.asNode);
  if (row.note) {
    row.asNode.append(row.note);
  } else if (row.state === "needs-name") {
    row.asNode.append("This looks like a camera photo name — type the student's name.");
  } else if (row.student) {
    row.asNode.append("appears in the gradebook as ", el("strong", { text: row.student }));
  }
  row.input.disabled = LOCKED.has(row.state);
}

function onRename(row, value) {
  row.name = value;
  if (row.state !== "held") {
    row.note = "";
  }
  row.studentId = slugify(value);
  row.student = row.studentId ? prettyName(row.studentId) : "";
  if (row.state === "needs-name" && row.studentId) {
    Object.assign(row, { state: "ready", status: "waiting to send", tone: "" });
  } else if (row.state === "ready" && !row.studentId) {
    Object.assign(row, { state: "needs-name", status: "needs a name" });
  } else if (row.state === "failed" && row.studentId) {
    Object.assign(row, { state: "ready", status: "waiting to send", tone: "" });
  }
  paintRow(row);
  renderBatch();
  window.clearTimeout(renameTimer);
  renameTimer = window.setTimeout(() => runQueue(false), RENAME_IDLE_MS);
}

function buildRow(row) {
  const input = el("input", {
    class: "rename-input",
    type: "text",
    autocomplete: "off",
    spellcheck: "false",
    placeholder: "Type the student's name",
    "aria-label": `Name in the gradebook for ${row.label}`,
  });
  input.value = row.name;
  input.addEventListener("input", () => onRename(row, input.value));
  input.addEventListener("blur", () => runQueue(false));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runQueue(false);
    }
  });
  const status = el("span", { class: "status" });
  const as = el("span", { class: "as" });
  if (row.state === "needs-name" && row.file.type.startsWith("image/")) {
    row.thumbUrl = URL.createObjectURL(row.file);
    row.thumbNode = el("img", {
      class: "row-thumb",
      src: row.thumbUrl,
      alt: `Photo ${row.label}`,
      loading: "lazy",
    });
  }
  const node = el("li", {}, [
    row.thumbNode || null,
    el("div", { class: "upload-name" }, [
      el("span", { class: "file", text: row.label }),
      el("label", { class: "rename" }, [
        el("span", { class: "rename-tag", text: "Name in the gradebook" }),
        input,
      ]),
      as,
    ]),
    status,
  ]);
  Object.assign(row, { node, statusNode: status, asNode: as, input });
  paintRow(row);
  return node;
}

function visibleRows() {
  if (view.filter) {
    return rows.filter((row) => row.state === view.filter);
  }
  if (rows.length <= COLLAPSE_AFTER || view.expanded) {
    return rows;
  }
  return rows.filter((row) => ATTENTION.has(row.state));
}

function renderRows() {
  const focused = rows.find((row) => row.input === document.activeElement);
  const visible = visibleRows();
  if (focused && !visible.includes(focused)) {
    visible.splice(Math.min(rows.indexOf(focused), visible.length), 0, focused);
  }
  const current = Array.from(dom.uploadLog.children);
  const wanted = visible.map((row) => row.node);
  if (current.length === wanted.length && current.every((node, index) => node === wanted[index])) {
    return;
  }
  clear(dom.uploadLog);
  wanted.forEach((node) => dom.uploadLog.append(node));
}

function chipLabel(chip, tally) {
  return `${tally[chip.key] || 0} ${chip.label}`;
}

function renderChips(tally) {
  clear(dom.batchChips);
  CHIPS.filter((chip) => tally[chip.key]).forEach((chip) => {
    dom.batchChips.append(el("button", {
      type: "button",
      class: `chip${view.filter === chip.key ? " is-on" : ""}`,
      "data-chip": chip.key,
      text: chipLabel(chip, tally),
      onclick: () => {
        view.filter = view.filter === chip.key ? "" : chip.key;
        renderBatch();
        renderRows();
      },
    }));
  });
}

function subLine(tally) {
  if (view.awaitingLot) {
    return "Add the subject, class and assessment name above, then press Start sending.";
  }
  if (view.running) {
    const left = Math.max(sendTarget() - sentCount(), 0);
    return `Sending exam ${Math.min(sentCount() + 1, sendTarget())} of ${sendTarget()} — ${left} left.`;
  }
  if (tally["needs-name"]) {
    const many = tally["needs-name"] > 1;
    return `Type a name for the ${many ? `${tally["needs-name"]} photos` : "photo"} below and ${many ? "they go" : "it goes"} on their own.`;
  }
  if (tally.failed) {
    return "Some files didn't go through. Press Retry so they try again.";
  }
  if (tally.held) {
    return "The held back pages stay here until you upload them combined.";
  }
  return "Every file was received. Grading runs on its own.";
}

function renderBatch() {
  if (!rows.length) {
    dom.batchPanel.hidden = true;
    return;
  }
  const tally = counts();
  dom.batchPanel.hidden = false;
  dom.batchTitle.textContent = `${assessmentLabel()} · ${rows.length} file${rows.length === 1 ? "" : "s"}`;
  dom.batchSub.textContent = subLine(tally);
  renderChips(tally);
  const target = sendTarget();
  const done = sentCount();
  dom.batchBar.hidden = !target || !view.running;
  dom.batchBarFill.style.width = target ? `${Math.round((done / target) * 100)}%` : "0%";
  dom.batchRetry.hidden = !tally.failed || view.running;
  dom.batchStart.hidden = !(view.awaitingLot && tally.ready);
  dom.batchToggle.hidden = rows.length <= COLLAPSE_AFTER || Boolean(view.filter);
  dom.batchToggle.textContent = view.expanded
    ? "Show only what needs me"
    : `Show all ${rows.length} files`;
}

function askPages(groups) {
  clear(dom.pagesGroups);
  groups.forEach((names) => {
    dom.pagesGroups.append(el("li", {}, [
      el("span", { class: "files", text: names.join("  +  ") }),
      el("span", {
        class: "becomes",
        text: `would sync as ${names.map((name) => `“${prettyName(slugify(fileStem(name)))}”`).join(", ")}`,
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

function askCollision(studentId) {
  dom.collisionMessage.textContent =
    `There's already a scan saved for ${studentId} in this assessment. ` +
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

function finishRow(row, state, status, tone) {
  Object.assign(row, { state, status, tone: tone || "" });
  paintRow(row);
}

async function uploadRow(row, lotCode) {
  let mode = row.studentId === fileStem(row.label) ? "new" : "rename";
  let newName = mode === "rename" ? row.studentId : "";
  for (;;) {
    const form = new FormData();
    form.append("file", row.file, row.label);
    form.append("lot_code", lotCode);
    form.append("mode", mode);
    if (newName) {
      form.append("new_student_name", newName);
    }
    let result = null;
    try {
      result = await postForm(endpoints.ingestExam(), form);
    } catch (error) {
      finishRow(row, "failed", "we couldn't reach GradeSync", "bad");
      return true;
    }
    if (result.status === 401 || result.status === 403) {
      finishRow(row, "failed", "needs the access code", "bad");
      hooks.openGate("That access code didn't work. Check it and try again.");
      return false;
    }
    if (result.ok) {
      finishRow(row, "received", mode === "replace" ? "replaced" : "received", "good");
      return true;
    }
    if (result.status === 409 && result.body && result.body.collision) {
      finishRow(row, "sending", "already has a scan");
      const decision = await askCollision(result.body.student_id || row.studentId);
      if (decision.action === "cancel") {
        finishRow(row, "skipped", "kept the existing scan");
        return true;
      }
      mode = decision.action;
      newName = decision.name || "";
      if (newName) {
        row.studentId = newName;
        row.student = prettyName(newName);
        row.name = row.student;
        row.input.value = row.student;
      }
      continue;
    }
    const detail = result.body && result.body.detail ? String(result.body.detail) : "";
    if (NEEDS_NAME_DETAIL.test(detail)) {
      row.note = "GradeSync could not use that name — type the student's name.";
      finishRow(row, "needs-name", "needs a name");
      return true;
    }
    finishRow(row, "failed", failureCopy(detail), "bad");
    return true;
  }
}

async function runQueue(announce) {
  if (view.running || !rows.some((row) => row.state === "ready")) {
    return;
  }
  const lotCode = composeLotCode(announce);
  if (!lotCode) {
    view.awaitingLot = true;
    renderBatch();
    return;
  }
  view.awaitingLot = false;
  view.running = true;
  view.lotCode = lotCode;
  renderBatch();
  for (;;) {
    const row = rows.find((candidate) => candidate.state === "ready");
    if (!row) {
      break;
    }
    finishRow(row, "sending", "sending…");
    renderRows();
    renderBatch();
    const carryOn = await uploadRow(row, lotCode);
    renderRows();
    renderBatch();
    if (!carryOn) {
      break;
    }
  }
  view.running = false;
  renderRows();
  renderBatch();
  if (rows.some((row) => row.state === "received")) {
    hooks.onBatchSent(lotCode);
  }
}

function stageFile(file, held) {
  const stem = fileStem(file.name);
  const camera = looksLikeCamera(stem);
  const studentId = camera ? "" : slugify(stem);
  const row = {
    id: (nextRowId += 1),
    file,
    label: file.name,
    name: studentId ? prettyName(studentId) : "",
    studentId,
    student: studentId ? prettyName(studentId) : "",
    state: "ready",
    status: "waiting to send",
    tone: "",
    note: "",
  };
  if (held) {
    Object.assign(row, {
      state: "held",
      status: "held back",
      note: "Combine the pages into one PDF, then upload that single file.",
    });
  } else if (!ALLOWED_SUFFIXES.has(fileSuffix(file.name))) {
    Object.assign(row, { state: "failed", status: "not a photo or PDF", tone: "bad", local: true });
  } else if (file.size > MAX_UPLOAD_BYTES) {
    Object.assign(row, { state: "failed", status: "over the 20 MB limit", tone: "bad", local: true });
  } else if (camera) {
    Object.assign(row, { state: "needs-name", status: "needs a name" });
  }
  rows.push(row);
  buildRow(row);
}

async function handleFiles(fileList) {
  const files = Array.from(fileList);
  const pending = rows.some((row) => row.state === "ready" || row.state === "needs-name");
  const lotCode = composeLotCode(false);
  const newAssessment = Boolean(lotCode) && Boolean(view.lotCode) && lotCode !== view.lotCode;
  if (!view.running && (newAssessment || !pending)) {
    if (newAssessment && pending) {
      hooks.toast("The files still waiting for a name belonged to the previous assessment.");
    }
    rows.forEach(releaseThumb);
    rows.length = 0;
    view.filter = "";
    view.expanded = false;
    clear(dom.uploadLog);
  }
  const candidates = files.filter((file) => !looksLikeCamera(fileStem(file.name)));
  const groups = detectPageGroups(candidates.map((file) => file.name));
  const held = new Set();
  if (groups.length) {
    const action = await askPages(groups);
    if (action === "combine") {
      groups.flat().forEach((name) => held.add(name));
    }
  }
  files.forEach((file) => stageFile(file, held.has(file.name)));
  renderBatch();
  renderRows();
  runQueue(true);
}

export function showProgress(progress) {
  if (!progress) {
    dom.batchStatus.hidden = true;
    return;
  }
  dom.batchStatusLine.textContent = progress.headline;
  clear(dom.batchStatusCounts);
  [
    ["in the gradebook", progress.in_gradebook],
    ["waiting for you", progress.waiting_for_you],
    ["still being graded", progress.still_grading],
    ["couldn't be graded", progress.could_not_grade],
  ].filter(([, value]) => value > 0).forEach(([label, value]) => {
    dom.batchStatusCounts.append(el("span", { class: "count" }, [
      el("strong", { text: String(value) }),
      ` ${label}`,
    ]));
  });
  dom.batchStatusReview.hidden = !progress.waiting_for_you;
  dom.batchStatus.hidden = false;
}

export function veils() {
  return [dom.collisionVeil, dom.pagesVeil];
}

export function escapeVeil(veil) {
  if (veil === dom.collisionVeil) {
    settleCollision({ action: "cancel" });
  } else if (veil === dom.pagesVeil) {
    settlePages("combine");
  }
}

function wireDialogs() {
  dom.collisionCancel.addEventListener("click", () => settleCollision({ action: "cancel" }));
  dom.collisionReplace.addEventListener("click", () => settleCollision({ action: "replace" }));
  dom.collisionDifferent.addEventListener("click", () => {
    if (dom.collisionNameInput.hidden) {
      dom.collisionNameInput.hidden = false;
      dom.collisionDifferent.textContent = "Save under this name";
      dom.collisionNameInput.focus();
      return;
    }
    const name = slugify(dom.collisionNameInput.value);
    if (!STUDENT_ID.test(name)) {
      dom.collisionError.textContent = "Type the student's name, like Ana Torres.";
      dom.collisionError.hidden = false;
      return;
    }
    settleCollision({ action: "rename", name });
  });
  dom.pagesCombine.addEventListener("click", () => settlePages("combine"));
  dom.pagesSeparate.addEventListener("click", () => settlePages("separate"));
}

function wireDropzone() {
  fileInput = el("input", {
    type: "file",
    multiple: true,
    accept: ".jpg,.jpeg,.png,.pdf,.heic",
    hidden: true,
  });
  document.body.append(fileInput);
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) {
      handleFiles(fileInput.files);
      fileInput.value = "";
    }
  });
  dom.dropzone.addEventListener("click", () => fileInput.click());
  dom.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
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
}

function wireBatchTools() {
  dom.batchToggle.addEventListener("click", () => {
    view.expanded = !view.expanded;
    renderBatch();
    renderRows();
  });
  dom.batchRetry.addEventListener("click", () => {
    rows.filter((row) => row.state === "failed" && !row.local)
      .forEach((row) => finishRow(row, "ready", "waiting to send"));
    renderBatch();
    renderRows();
    runQueue(true);
  });
  dom.batchStart.addEventListener("click", () => runQueue(true));
  dom.batchStatusReview.addEventListener("click", () => hooks.goToReview());
  [dom.subjectInput, dom.classInput, dom.assessmentInput].forEach((field) =>
    field.addEventListener("input", () => { if (rows.length) { renderBatch(); } })
  );
}

export function setupUploads(options) {
  hooks = options;
  bind([
    "subject-input", "class-input", "assessment-input", "dropzone", "upload-log",
    "batch-panel", "batch-title", "batch-sub", "batch-chips", "batch-bar", "batch-bar-fill",
    "batch-retry", "batch-start", "batch-toggle", "batch-status", "batch-status-line",
    "batch-status-counts", "batch-status-review", "collision-veil", "collision-message",
    "collision-name-input", "collision-error", "collision-cancel", "collision-different",
    "collision-replace", "pages-veil", "pages-message", "pages-groups", "pages-separate",
    "pages-combine",
  ]);
  wireDialogs();
  wireDropzone();
  wireBatchTools();
}
